import pytest
import pandas as pd
from pathlib import Path
from risk_engine.threat_forecaster import ThreatSequenceForecaster

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def test_threat_forecaster_execution():
    forecaster = ThreatSequenceForecaster(window_size=7, forecast_horizon=14)
    df = pd.read_csv(DATA_DIR / "threat_events.csv")
    result = forecaster.train_and_forecast(df)
    
    assert "summary" in result
    assert "forecast_series" in result
    assert "historical_series" in result
    assert "mitre_transitions" in result
    
    summary = result["summary"]
    assert summary["forecast_horizon_days"] == 14
    assert len(result["forecast_series"]) == 14
    assert len(result["mitre_transitions"]) > 0
    assert "predicted_events" in result["forecast_series"][0]
