"""
Risk Trend Engine.

Rebuilds EAL / VaR95 at successive historical cutoffs by re-running the real
quantification pipeline against progressively truncated threat-event telemetry.

Every point is an actual Monte Carlo result for the data available at that
moment -- not a scaled copy of the present. Because the telemetry window is
short, the snapshots span the observed period rather than a fabricated
multi-quarter history.
"""

from datetime import datetime

import numpy as np
import pandas as pd

from .aggregate import RiskAggregator
from .config import EngineConfig, DEFAULT_CONFIG
from .frequency import FrequencyModel
from .likelihood import LikelihoodModel
from .loss_magnitude import LossMagnitudeModel
from .simulate import MonteCarloSimulator


def _snapshot(
    events: pd.DataFrame,
    assets: pd.DataFrame,
    vulns: pd.DataFrame,
    controls: pd.DataFrame,
    asset_controls: pd.DataFrame,
    config: EngineConfig,
) -> dict:
    """Runs likelihood -> frequency -> loss -> Monte Carlo on one event slice."""
    base = DataIngestorProxy(assets, vulns, events, controls, asset_controls).build()
    df = LikelihoodModel(config).apply_to_dataframe(base)
    df = FrequencyModel(config).apply_to_dataframe(df)
    df = LossMagnitudeModel(config).apply_to_dataframe(df)
    df = MonteCarloSimulator(config).apply_to_dataframe(df)
    agg = RiskAggregator(config).aggregate(df)
    org = agg["org_risk_summary"]
    return {
        "total_EAL_usd": float(org["total_EAL_usd"].sum()),
        "total_VaR95_usd": float(org["total_VaR95_usd_upper_bound"].sum()),
        "n_controls_deployed": int(asset_controls.shape[0]),
        "n_open_vulns": int(vulns.shape[0]),
        "n_events_in_window": int(events.shape[0]),
    }


class DataIngestorProxy:
    """
    Minimal stand-in for DataIngestor that assembles the risk base from
    already-loaded frames.

    The pipeline's own ingest step requires all five CSVs on disk under a
    data_dir. Trending needs the same join over an in-memory slice of one of
    them, so this reuses DataIngestor's build_asset_risk_base rather than
    writing temp CSVs per cutoff.
    """

    def __init__(self, assets, vulns, events, controls, asset_controls):
        self._frames = {
            "assets": assets,
            "vulnerabilities": vulns,
            "threat_events": events,
            "controls": controls,
            "asset_controls": asset_controls,
        }

    def build(self) -> pd.DataFrame:
        from .ingest import DataIngestor

        return DataIngestor(DEFAULT_CONFIG).build_asset_risk_base(self._frames)


def generate_risk_trend(
    base_df: pd.DataFrame,
    raw_data: dict,
    config: EngineConfig = DEFAULT_CONFIG,
    n_snapshots: int = 6,
) -> pd.DataFrame:
    """
    Historical risk trajectory from re-simulated telemetry windows.

    Parameters
    ----------
    base_df : the already-computed org-level summary (used for the final
        "current" row so the series ends exactly on the pipeline's own EAL).
    raw_data : the five ingested frames.
    n_snapshots : number of historical cutoffs to reconstruct, newest included.

    Returns
    -------
    DataFrame with one row per cutoff, oldest first.
    """
    events = raw_data.get("threat_events")
    if not isinstance(events, pd.DataFrame):
        events = pd.DataFrame(events)

    assets = raw_data["assets"]
    vulns = raw_data["vulnerabilities"]
    controls = raw_data["controls"]
    asset_controls = raw_data["asset_controls"]

    if events.empty or "timestamp" not in events.columns:
        # No telemetry to reconstruct from -- return the current state alone.
        return pd.DataFrame([{
            "date": datetime.now().strftime("%Y-%m-%d"),
            "label": "Current",
            "month_offset": 0,
            "total_EAL_usd": round(float(base_df["total_EAL_usd"].sum()), 2),
            "total_VaR95_usd": round(float(base_df["total_VaR95_usd_upper_bound"].sum()), 2),
            "n_controls_deployed": int(asset_controls.shape[0]),
            "n_open_vulns": int(vulns.shape[0]),
            "n_events_in_window": 0,
            "risk_delta_pct": 0.0,
            "is_reconstructed": False,
        }])

    ev = events.copy()
    ev["dt"] = pd.to_datetime(ev["timestamp"], errors="coerce")
    ev = ev.dropna(subset=["dt"]).sort_values("dt")
    end = ev["dt"].max()
    span_days = max((end - ev["dt"].min()).days, 1)

    # Cutoffs evenly spaced inside the observed window, newest excluded (the
    # final row comes from the pipeline's own current-state aggregate).
    step = max(1, span_days // n_snapshots)
    offsets = list(range(step, span_days + 1, step))[: n_snapshots - 1]

    # Fewer iterations than the main run: the trend only needs the shape of the
    # curve, and this runs several times per pipeline invocation.
    sim_config = EngineConfig(
        data_dir=config.data_dir,
        output_dir=config.output_dir,
        n_simulations=min(config.n_simulations, 4000),
    )

    current_eal = float(base_df["total_EAL_usd"].sum())
    current_var95 = float(base_df["total_VaR95_usd_upper_bound"].sum())
    snapshots = []

    for off in offsets:
        cut = end - pd.Timedelta(days=off)
        window = ev[ev["dt"] <= cut].drop(columns=["dt"])
        if window.empty:
            continue
        snap = _snapshot(
            window, assets, vulns, controls, asset_controls, sim_config
        )
        snap["date"] = cut.strftime("%Y-%m-%d")
        snap["label"] = f"-{off}d"
        snap["month_offset"] = -off
        snap["is_reconstructed"] = True
        snapshots.append(snap)

    snapshots.sort(key=lambda s: s["month_offset"])

    for s in snapshots:
        s["risk_delta_pct"] = round((s["total_EAL_usd"] / current_eal - 1) * 100, 1) if current_eal else 0.0
        s["total_EAL_usd"] = round(s["total_EAL_usd"], 2)
        s["total_VaR95_usd"] = round(s["total_VaR95_usd"], 2)

    snapshots.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "label": "Current",
        "month_offset": 0,
        "total_EAL_usd": round(current_eal, 2),
        "total_VaR95_usd": round(current_var95, 2),
        "n_controls_deployed": int(asset_controls.shape[0]),
        "n_open_vulns": int(vulns.shape[0]),
        "n_events_in_window": int(ev.shape[0]),
        "risk_delta_pct": 0.0,
        "is_reconstructed": False,
    })

    return pd.DataFrame(snapshots)