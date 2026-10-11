import io
import json
import logging
import os
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from risk_engine.config import EngineConfig
from risk_engine.ingest import DataIngestor, IngestionError
from risk_engine.pipeline import RiskPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

BASE_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
UPLOADS_DIR = BASE_DATA_DIR / "uploads"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

REQUIRED_TABLES = [
    "assets",
    "vulnerabilities",
    "threat_events",
    "controls",
    "asset_controls"
]

REQUIRED_COLUMNS = {
    "assets": [
        "asset_id", "business_unit", "criticality",
        "data_sensitivity_tier", "financial_value_usd", "downtime_cost_per_hour_usd"
    ],
    "controls": [
        "control_id", "name", "risk_reduction_pct", "cost_usd"
    ],
    "asset_controls": [
        "asset_id", "control_id"
    ],
    "threat_events": [
        "event_id", "asset_id", "downtime_hours_caused", "records_compromised"
    ],
    "vulnerabilities": [
        "asset_id", "cve_id", "cvss_score", "epss_score"
    ]
}


def _validate_dataframes(data: Dict[str, pd.DataFrame]) -> None:
    """Performs strict schema and domain validation across all 5 datasets."""
    # 1. Ensure all 5 datasets are present
    missing_tables = [table for table in REQUIRED_TABLES if table not in data or data[table] is None]
    if missing_tables:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required datasets: {', '.join(missing_tables)}. All 5 datasets are required."
        )

    # 2. Validate columns for each table
    for table_name, req_cols in REQUIRED_COLUMNS.items():
        df = data[table_name]
        if df.empty and table_name in ("assets", "controls"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dataset '{table_name}.csv' cannot be empty."
            )
        
        missing_cols = [col for col in req_cols if col not in df.columns]
        if missing_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required columns in '{table_name}.csv': {', '.join(missing_cols)}"
            )

    # 3. Domain value validation: Assets
    assets_df = data["assets"]
    try:
        if (pd.to_numeric(assets_df["financial_value_usd"], errors="coerce") < 0).any():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Negative financial_value_usd values found in assets.csv"
            )
        if (pd.to_numeric(assets_df["downtime_cost_per_hour_usd"], errors="coerce") < 0).any():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Negative downtime_cost_per_hour_usd values found in assets.csv"
            )
    except TypeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Non-numeric values found in financial columns of assets.csv"
        )

    # 4. Domain value validation: Controls
    controls_df = data["controls"]
    try:
        rr_pct = pd.to_numeric(controls_df["risk_reduction_pct"], errors="coerce")
        if (rr_pct > 1.0).any() or (rr_pct < 0.0).any() or rr_pct.isna().any():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="risk_reduction_pct in controls.csv must be fractional numbers between 0.0 and 1.0 (e.g. 0.75 for 75%)"
            )
        cost = pd.to_numeric(controls_df["cost_usd"], errors="coerce")
        if (cost < 0).any() or cost.isna().any():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cost_usd in controls.csv must be non-negative numeric values"
            )
    except TypeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid numeric types in controls.csv"
        )

    # 5. Ingestion validation
    try:
        ingestor = DataIngestor()
        ingestor._validate_schemas(data)
    except IngestionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schema validation error: {str(e)}"
        )


def _process_and_save_data(data: Dict[str, pd.DataFrame], session_id: str) -> dict:
    """Saves raw dataframes to a session folder and executes the risk pipeline."""
    session_dir = UPLOADS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Save CSVs to session upload directory
    for name, df in data.items():
        csv_filename = f"{name}.csv" if not name.endswith(".csv") else name
        df.to_csv(session_dir / csv_filename, index=False)

    # Execute risk pipeline
    try:
        config = EngineConfig(data_dir=session_dir, output_dir=OUTPUT_DIR)
        pipeline = RiskPipeline(config=config)
        pipeline.run_all()
    except Exception as e:
        logger.exception("Risk engine pipeline execution failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Risk engine execution failed: {str(e)}"
        )

    return {
        "status": "success",
        "session_id": session_id,
        "asset_count": int(len(data["assets"])),
        "controls_count": int(len(data["controls"])),
        "events_count": int(len(data["threat_events"])),
        "vulnerabilities_count": int(len(data["vulnerabilities"])),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "message": "Dataset successfully processed and risk quantification pipeline completed."
    }


@router.post("/upload")
async def upload_datasets(
    files: List[UploadFile] = File(...),
):
    """
    Accepts dataset uploads in one of three formats:
    1. Multiple individual CSV files (assets.csv, controls.csv, asset_controls.csv, threat_events.csv, vulnerabilities.csv)
    2. A single .zip archive containing the 5 CSVs
    3. A single compiled_risk_dataset.json file
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided for upload."
        )

    data: Dict[str, pd.DataFrame] = {}
    session_id = f"upload_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # Check if single file is ZIP or JSON
    if len(files) == 1:
        single_file = files[0]
        filename = (single_file.filename or "").lower()

        if filename.endswith(".zip"):
            content = await single_file.read()
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        base_name = Path(name).name.lower()
                        for target in REQUIRED_TABLES:
                            if base_name == f"{target}.csv":
                                with z.open(name) as f:
                                    data[target] = pd.read_csv(f)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not read uploaded zip archive: {str(e)}"
                )

        elif filename.endswith(".json"):
            content = await single_file.read()
            try:
                json_data = json.loads(content.decode("utf-8"))
                for target in REQUIRED_TABLES:
                    if target in json_data and isinstance(json_data[target], list):
                        data[target] = pd.DataFrame(json_data[target])
                    elif f"{target}s" in json_data and isinstance(json_data[f"{target}s"], list):
                        data[target] = pd.DataFrame(json_data[f"{target}s"])
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not parse uploaded JSON dataset: {str(e)}"
                )

    # Multi-file or individual CSVs
    if not data:
        for file in files:
            fname = (file.filename or "").lower()
            content = await file.read()
            
            clean_name = Path(fname).name.lower()
            for target in REQUIRED_TABLES:
                if clean_name == f"{target}.csv":
                    try:
                        data[target] = pd.read_csv(io.BytesIO(content))
                    except Exception as e:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Could not parse CSV file '{file.filename}': {str(e)}"
                        )
                    break

    # Validate all loaded DataFrames
    _validate_dataframes(data)

    # Process and run pipeline
    return _process_and_save_data(data, session_id)


class JsonDatasetPayload(BaseModel):
    assets: List[dict]
    controls: List[dict]
    asset_controls: List[dict]
    threat_events: List[dict]
    vulnerabilities: List[dict]


@router.post("/upload-json")
async def upload_json_dataset(payload: JsonDatasetPayload):
    """Direct JSON payload upload endpoint."""
    data = {
        "assets": pd.DataFrame(payload.assets),
        "controls": pd.DataFrame(payload.controls),
        "asset_controls": pd.DataFrame(payload.asset_controls),
        "threat_events": pd.DataFrame(payload.threat_events),
        "vulnerabilities": pd.DataFrame(payload.vulnerabilities),
    }

    _validate_dataframes(data)
    session_id = f"upload_json_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    return _process_and_save_data(data, session_id)


@router.post("/demo")
def load_demo_dataset():
    """Loads the authoritative built-in sample dataset from backend/data and runs the pipeline."""
    if not BASE_DATA_DIR.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Built-in demo data directory not found."
        )

    try:
        ingestor = DataIngestor(config=EngineConfig(data_dir=BASE_DATA_DIR))
        raw_data = ingestor.load_data()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load built-in demo dataset: {str(e)}"
        )

    session_id = f"demo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    return _process_and_save_data(raw_data, session_id)


@router.get("/status")
def get_dataset_status():
    """Returns the current dataset and pipeline output readiness status."""
    required_outputs = [
        "asset_risk_summary.parquet",
        "business_unit_risk_summary.parquet",
        "org_risk_summary.parquet",
        "control_scenario_results.parquet"
    ]

    all_exist = all((OUTPUT_DIR / f).exists() for f in required_outputs)

    asset_count = 0
    last_updated = None

    if all_exist:
        try:
            asset_file = OUTPUT_DIR / "asset_risk_summary.parquet"
            mtime = os.path.getmtime(asset_file)
            last_updated = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            df = pd.read_parquet(asset_file)
            asset_count = len(df)
        except Exception:
            pass

    return {
        "outputs_ready": all_exist,
        "asset_count": asset_count,
        "last_updated": last_updated,
    }
