import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

# pandas 3.x registers pyarrow extension types lazily, from
# pandas.core.arrays.arrow.extension_types. That module calls
# pyarrow.register_extension_type() at import time and raises
# "ArrowKeyError: A type extension with name pandas.period already defined"
# if it is ever imported a second time in one process. `uvicorn --reload`
# re-imports the app module on every file change, which triggers exactly
# that, and the first parquet read then fails with a 500 that looks like a
# data problem rather than an import problem.
#
# Import it once here so it is cached before anything else can pull it in.
try:  # pragma: no cover - depends on pandas internals
    import pandas.core.arrays.arrow.extension_types  # noqa: F401
except Exception:  # pandas layout changed; the guard is best-effort
    pass

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from api import db
from api import auth as auth_api
from api.auth import get_current_user
from api.chat import router as chat_router
from api.upload import router as upload_router
from api.live_feed import router as live_feed_router
from risk_engine.investment_optimizer import optimize_investments
from risk_engine.frontier import compute_frontier
from risk_engine.framework_mapper import get_compliance_posture, get_compliance_gaps

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Cyber Risk Quantification API",
    description="API for accessing computed financial cyber risk metrics.",
    version="1.0.0",
)

@app.middleware("http")
async def resolve_session(request: Request, call_next):
    """Resolve the caller's active dataset into the request-scoped session.

    Runs in the event loop, before FastAPI dispatches the endpoint to a
    threadpool thread, so the ContextVar is inherited by every handler in
    this request. Best-effort: authentication/401s stay the dependency's job.
    """
    try:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            user = auth_api.user_from_token(auth_header[7:].strip())
            if user is not None:
                dataset = db.get_active_dataset(user["id"])
                if dataset:
                    db.set_session_paths(dataset["data_dir"], dataset["output_dir"])
    except Exception:
        logger.exception("Session resolution middleware failed; falling back to seed data")
    return await call_next(request)


app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(live_feed_router)
app.include_router(auth_api.router)

# --- CORS: required so the frontend dashboard (running on a different
# port, e.g. localhost:3000 or localhost:5173) can call this API.
# For the hackathon demo, allow_origins=["*"] is simplest. If you want to
# be stricter, replace "*" with your actual frontend dev server URL(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Output directory relative to this file
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def active_asset_controls_path() -> Path:
    """
    Path to the asset_controls.csv of the dataset currently active for the
    caller. Every upload/demo registers its own session in the database
    (api/db.py) and marks it active, so compliance posture follows the
    uploader's dataset instead of always reading the seed CSVs. Falls back
    to the seed data when no session is active (e.g. pipeline run via CLI).
    """
    return db.current_paths()[0] / "asset_controls.csv"


def deployed_control_ids() -> set:
    """Control IDs currently deployed, from the active dataset."""
    ac_path = active_asset_controls_path()
    if not ac_path.exists():
        return set()
    ac_df = pd.read_csv(ac_path)
    if "control_id" not in ac_df.columns:
        return set()
    # Only count rows actually marked deployed, if the column exists.
    if "status" in ac_df.columns:
        ac_df = ac_df[ac_df["status"].astype(str).str.lower() == "deployed"]
    return set(ac_df["control_id"].unique())


def load_parquet(filename: str) -> pd.DataFrame:
    if not db.has_session():
        raise FileNotFoundError(
            "No dataset session is active for this user. Upload a dataset or load the demo dataset first."
        )
    file_path = db.current_paths()[1] / filename
    if not file_path.exists():
        raise FileNotFoundError(
            f"Output file not found: {file_path}. Have you run `python -m risk_engine.pipeline` (or uploaded a dataset)?"
        )
    return pd.read_parquet(file_path)


def _handle_load_error(e: Exception):
    """Distinguish 'pipeline not run yet' from real server errors."""
    if isinstance(e, FileNotFoundError):
        raise HTTPException(status_code=503, detail=str(e))
    logger.exception("Unexpected error while serving request")
    raise HTTPException(status_code=500, detail=str(e))


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check():
    """Returns the API status."""
    return {"status": "ok"}


@app.get("/risk/assets", dependencies=[Depends(get_current_user)])
def get_asset_risk_summary():
    """Returns risk metrics for all assets."""
    try:
        df = load_parquet("asset_risk_summary.parquet")
        summary_df = df[
            ["asset_id", "business_unit", "criticality", "EAL_usd", "VaR95_usd", "VaR99_usd", "priority_score"]
        ]
        return summary_df.to_dict(orient="records")
    except Exception as e:
        _handle_load_error(e)


@app.get("/risk/assets/{asset_id}", dependencies=[Depends(get_current_user)])
def get_asset_risk_detail(asset_id: str):
    """Returns detailed risk metrics for a single asset, including the Loss Exceedance Curve (if present)."""
    try:
        df = load_parquet("asset_risk_summary.parquet")
        asset_data = df[df["asset_id"] == asset_id]
        if asset_data.empty:
            raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")

        record = asset_data.iloc[0].to_dict()

        # Defensively convert any numpy/array-like fields to plain lists so
        # they serialize cleanly to JSON for the frontend.
        for key, value in record.items():
            if isinstance(value, np.ndarray):
                record[key] = value.tolist()
            elif isinstance(value, (np.integer,)):
                record[key] = int(value)
            elif isinstance(value, (np.floating,)):
                record[key] = float(value)

        # The Monte Carlo LEC curve is stored under LEC_points. Expose it
        # under loss_exceedance_curve too so the drilldown panel reads the real
        # simulated distribution rather than synthesising points from EAL.
        record["loss_exceedance_curve"] = record.pop("LEC_points", [])

        return record
    except HTTPException:
        raise
    except Exception as e:
        _handle_load_error(e)


@app.get("/risk/business-units", dependencies=[Depends(get_current_user)])
def get_business_unit_risk():
    """Returns aggregated risk metrics per Business Unit."""
    try:
        df = load_parquet("business_unit_risk_summary.parquet")
        return df.to_dict(orient="records")
    except Exception as e:
        _handle_load_error(e)


@app.get("/risk/organization", dependencies=[Depends(get_current_user)])
def get_organization_risk():
    """Returns top-level enterprise risk metrics."""
    try:
        df = load_parquet("org_risk_summary.parquet")
        return df.to_dict(orient="records")
    except Exception as e:
        _handle_load_error(e)


@app.get("/controls/scenarios", dependencies=[Depends(get_current_user)])
def get_all_scenarios():
    """Returns all control what-if scenarios."""
    try:
        df = load_parquet("control_scenario_results.parquet")
        return df.to_dict(orient="records")
    except Exception as e:
        _handle_load_error(e)


@app.get("/controls/roi", dependencies=[Depends(get_current_user)])
def get_controls_roi():
    """Returns controls ranked by overall Return on Security Investment (ROSI)."""
    try:
        df = load_parquet("control_scenario_results.parquet")
        grouped = df.groupby(["control_id", "control_name"]).agg(
            total_cost_usd=("cost_usd", "sum"),
            total_risk_reduction_usd=("Risk_Reduction_usd", "sum"),
            applicable_assets=("asset_id", "count"),
        ).reset_index()

        grouped["overall_ROSI"] = grouped["total_risk_reduction_usd"] / grouped["total_cost_usd"]
        grouped = grouped.sort_values(by="overall_ROSI", ascending=False)
        return grouped.to_dict(orient="records")
    except Exception as e:
        _handle_load_error(e)


@app.get("/controls/optimize", dependencies=[Depends(get_current_user)])
def get_optimal_investment_plan(
    budget: float = Query(..., gt=0, description="Available security budget in USD"),
    one_control_per_asset: bool = Query(
        True, description="Restrict to at most one control per asset (recommended default)"
    ),
):
    """
    Runs the budget-constrained investment optimizer and returns the
    recommended set of (asset, control) actions for the given budget,
    along with a comparison against a naive greedy-by-ROSI baseline.

    This is the endpoint the dashboard's "what-if budget" slider should call.
    """
    try:
        scenarios = load_parquet("control_scenario_results.parquet")
        result = optimize_investments(scenarios, budget_usd=budget, one_control_per_asset=one_control_per_asset)

        return {
            "budget_usd": budget,
            "total_cost_usd": result["total_cost_usd"],
            "total_risk_reduction_usd": result["total_risk_reduction_usd"],
            "budget_utilization_pct": result["budget_utilization_pct"],
            "n_actions_selected": result["n_actions_selected"],
            "residual_eal_usd": result["residual_eal_usd"],
            "greedy_comparison": result["greedy_comparison"],
            "selected_actions": result["selected"].to_dict(orient="records"),
        }
    except Exception as e:
        _handle_load_error(e)


# ---------------------------------------------------------------------------
# Compliance Framework Mapping Endpoints
# ---------------------------------------------------------------------------

@app.get("/compliance/posture", dependencies=[Depends(get_current_user)])
def get_compliance_posture_endpoint():
    """Returns compliance coverage posture across all mapped frameworks."""
    try:
        posture = get_compliance_posture(deployed_control_ids())
        posture["source_dataset"] = str(active_asset_controls_path().parent.name)
        return posture
    except Exception as e:
        logger.exception("Error computing compliance posture")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/compliance/gaps", dependencies=[Depends(get_current_user)])
def get_compliance_gaps_endpoint():
    """Returns compliance gaps — framework requirements not covered by deployed controls."""
    try:
        return get_compliance_gaps(deployed_control_ids())
    except Exception as e:
        logger.exception("Error computing compliance gaps")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Investment Efficient Frontier Endpoint
# ---------------------------------------------------------------------------

# Frontier is expensive; cache per dataset output dir keyed by path so
# different sessions (users) never see each other's cached curve.
_frontier_cache: dict = {}

@app.get("/controls/frontier", dependencies=[Depends(get_current_user)])
def get_investment_frontier():
    """Returns the efficient frontier data — optimizer results at multiple budget levels (cached)."""
    out_dir = db.current_paths()[1]
    key = str(out_dir)
    if key in _frontier_cache:
        return _frontier_cache[key]

    cache_file = out_dir / "frontier_cache.json"
    if cache_file.exists():
        try:
            import json
            with open(cache_file, "r") as f:
                _frontier_cache[key] = json.load(f)
            return _frontier_cache[key]
        except Exception as e:
            logger.warning(f"Error reading frontier cache: {e}")

    try:
        scenarios = load_parquet("control_scenario_results.parquet")
        frontier = compute_frontier(scenarios)
        _frontier_cache[key] = frontier
        try:
            import json
            out_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w") as f:
                json.dump(frontier, f)
        except Exception:
            pass
        return frontier
    except Exception as e:
        _handle_load_error(e)


# ---------------------------------------------------------------------------
# Risk Trend Endpoint
# ---------------------------------------------------------------------------

@app.get("/risk/trend", dependencies=[Depends(get_current_user)])
def get_risk_trend():
    """Returns historical risk trend data for visualization."""
    try:
        df = load_parquet("risk_trend.parquet")
        return df.to_dict(orient="records")
    except Exception as e:
        _handle_load_error(e)


# ---------------------------------------------------------------------------
# ML Predictions Endpoint
# ---------------------------------------------------------------------------

@app.get("/predictions/vulnerabilities", dependencies=[Depends(get_current_user)])
def get_vuln_predictions():
    """Returns ML vulnerability exploitation predictions."""
    try:
        df = load_parquet("vuln_predictions.parquet")
        return df.to_dict(orient="records")
    except Exception as e:
        _handle_load_error(e)


@app.get("/predictions/threat-forecast", dependencies=[Depends(get_current_user)])
def get_threat_forecast(horizon_days: int = 14):
    """
    Returns sequential time neural network (LSTM) Threat Event Frequency (TEF) forecasts,
    forward attack surge trajectories, and MITRE ATT&CK technique transition probabilities.
    """
    import json
    data_dir, out_dir = db.current_paths()
    forecast_file = out_dir / "threat_forecast.json"
    
    # If cached file exists, return it
    if forecast_file.exists():
        try:
            with open(forecast_file, "r") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.warning(f"Error reading cached threat_forecast.json: {e}")

    # Otherwise compute on-the-fly from threat_events data
    try:
        from risk_engine.threat_forecaster import ThreatSequenceForecaster
        threat_events_path = data_dir / "threat_events.csv"
        
        if not threat_events_path.exists():
            raise HTTPException(status_code=404, detail="Threat events telemetry not found.")
            
        df = pd.read_csv(threat_events_path)
        forecaster = ThreatSequenceForecaster(window_size=7, forecast_horizon=horizon_days)
        result = forecaster.train_and_forecast(df)
        
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(forecast_file, "w") as f:
            json.dump(result, f, indent=2)
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error computing LSTM threat forecast")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Asset Dependency & Systemic Risk (Active Directory Graph) Endpoints
# ---------------------------------------------------------------------------

# One engine per (data_dir, output_dir): the graph is derived purely from the
# dataset, so it can be shared across requests against the same session.
# Replaces the old single process-global engine that leaked the first
# requester's topology to every other client.
_dependency_engines: dict = {}


def _get_graph_engine():
    data_dir, out_dir = db.current_paths()
    key = (str(data_dir), str(out_dir))
    engine = _dependency_engines.get(key)
    if engine is None:
        from risk_engine.dependency_graph import DependencyGraphEngine
        engine = DependencyGraphEngine()
        engine.build_graph(data_dir=str(data_dir), output_dir=str(out_dir))
        if len(_dependency_engines) > 8:  # ponytail: small cache, sessions are few
            _dependency_engines.clear()
        _dependency_engines[key] = engine
    return engine


@app.get("/risk/dependency-graph", dependencies=[Depends(get_current_user)])
def get_dependency_graph():
    """Returns the Active Directory trust & lateral movement dependency graph."""
    try:
        data_dir, out_dir = db.current_paths()
        engine = _get_graph_engine()
        return engine.build_graph(data_dir=str(data_dir), output_dir=str(out_dir))
    except Exception as e:
        logger.exception("Error building dependency graph")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/risk/dependency-graph/propagate", dependencies=[Depends(get_current_user)])
def get_risk_propagation(
    breached_asset_id: str = Query(..., description="Initial breached asset ID, e.g. AST-1000")
):
    """
    Computes lateral movement compromise probabilities and cascading financial
    loss exposure across the dependency graph starting from breached_asset_id.
    """
    try:
        engine = _get_graph_engine()
        return engine.propagate_risk(breached_asset_id)
    except Exception as e:
        logger.exception("Error calculating risk propagation")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Portfolio-Wide Loss Exceedance Curve (LEC) Endpoint
# ---------------------------------------------------------------------------

def _portfolio_lec_curve(df: pd.DataFrame) -> list:
    """
    Aggregate per-asset loss curves into an enterprise curve by summing
    asset-level loss quantiles at each exceedance probability.

    Summing quantiles is the perfect-correlation case: every asset is assumed
    to suffer its worst year simultaneously. It is therefore an UPPER BOUND on
    portfolio tail risk, matching the summation assumption already documented
    for VaR in risk_engine/aggregate.py. No separate enterprise simulation is
    run -- this reuses the per-asset Monte Carlo curves rather than inventing
    points by scaling EAL.
    """
    # `if pts` is not a valid truth test here: parquet hands back numpy
    # arrays, and bool() on a multi-element array raises. Test the length.
    curves = [pts for pts in df["LEC_points"] if pts is not None and len(pts) > 0]
    if not curves:
        return []

    # Common probability axis from the first curve, ascending (np.interp needs
    # an increasing x-axis; LEC points come in descending exceedance order).
    probs = np.array([p["probability"] for p in curves[0]], dtype=float)
    order = np.argsort(probs)
    probs = probs[order]

    total = np.zeros_like(probs)
    for pts in curves:
        p = np.array([q["probability"] for q in pts], dtype=float)
        loss = np.array([q["loss"] for q in pts], dtype=float)
        # Drop duplicate x values; np.interp requires strictly increasing x.
        _, keep = np.unique(p, return_index=True)
        total += np.interp(probs, p[keep], loss[keep])

    return [
        {"prob_num": round(float(pr) * 100, 4), "probability": f"{pr * 100:g}%", "loss_usd": round(float(l), 2)}
        for pr, l in zip(probs, total)
    ]


@app.get("/risk/portfolio-lec", dependencies=[Depends(get_current_user)])
def get_portfolio_lec():
    """
    Returns the enterprise-wide Loss Exceedance Curve (LEC), aggregated from the
    per-asset Monte Carlo loss distributions.

    Quantile-summed across assets, so it is a perfect-correlation upper bound.
    """
    try:
        df = load_parquet("asset_risk_summary.parquet")
        total_eal = float(df["EAL_usd"].sum())
        total_var95 = float(df["VaR95_usd"].sum())
        total_var99 = float(df["VaR99_usd"].sum())

        curve = _portfolio_lec_curve(df)

        def at(prob_pct: float) -> float:
            """Loss at a given exceedance probability, from the real curve."""
            if not curve:
                return 0.0
            xs = np.array([c["prob_num"] for c in curve])
            ys = np.array([c["loss_usd"] for c in curve])
            return round(float(np.interp(prob_pct, xs, ys)), 2)

        lec_points = [
            {"probability": "50%", "prob_num": 50, "loss_usd": at(50)},
            {"probability": "30%", "prob_num": 30, "loss_usd": at(30)},
            {"probability": "20%", "prob_num": 20, "loss_usd": at(20)},
            {"probability": "10%", "prob_num": 10, "loss_usd": at(10)},
            {"probability": "5% (VaR 95)", "prob_num": 5, "loss_usd": total_var95},
            {"probability": "2%", "prob_num": 2, "loss_usd": at(2)},
            {"probability": "1% (VaR 99)", "prob_num": 1, "loss_usd": total_var99},
            {"probability": "0.1% (Extreme)", "prob_num": 0.1, "loss_usd": at(0.1)},
        ]

        return {
            "organization_name": "Enterprise Portfolio",
            "total_eal_usd": total_eal,
            "total_var95_usd": total_var95,
            "total_var99_usd": total_var99,
            "max_probable_loss_usd": lec_points[-1]["loss_usd"],
            "total_assets_modeled": len(df),
            "aggregation_method": "quantile_sum_perfect_correlation_upper_bound",
            "lec_points": lec_points,
            "lec_curve": curve,
        }
    except Exception as e:
        _handle_load_error(e)