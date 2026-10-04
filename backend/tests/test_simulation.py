import pytest
import pandas as pd
import numpy as np

from risk_engine.simulate import MonteCarloSimulator
from risk_engine.config import EngineConfig

@pytest.fixture
def simulator():
    # Use a small number of simulations for fast testing, but enough for percentiles
    config = EngineConfig(n_simulations=1000, random_seed=42)
    return MonteCarloSimulator(config)

def test_simulation_zero_risk(simulator):
    row = pd.Series({
        "TEF_min": 0.0,
        "TEF_mostlikely": 0.0,
        "TEF_max": 0.0,
        "Vuln_asset": 0.0,
        "LM_lognormal_mu": 0.0,
        "LM_lognormal_sigma": 0.75
    })
    
    result = simulator.run_simulation(row)
    assert result["EAL_usd"] == 0.0
    assert result["VaR95_usd"] == 0.0
    assert result["VaR99_usd"] == 0.0

def test_simulation_positive_risk(simulator):
    row = pd.Series({
        "TEF_min": 5.0,
        "TEF_mostlikely": 10.0,
        "TEF_max": 20.0,
        "Vuln_asset": 0.5,
        "LM_lognormal_mu": np.log(100000), # Median loss = 100k
        "LM_lognormal_sigma": 0.75
    })
    
    result = simulator.run_simulation(row)
    
    eal = result["EAL_usd"]
    var95 = result["VaR95_usd"]
    var99 = result["VaR99_usd"]
    
    assert eal > 0.0
    assert var95 >= eal # Since distribution is heavily right-skewed and long-tailed, VaR95 is usually >> mean
    assert var99 >= var95
    
    lec = result["LEC_points"]
    assert len(lec) > 0
    assert "loss" in lec[0]
    assert "probability" in lec[0]

def test_apply_to_dataframe(simulator):
    df = pd.DataFrame([
        {
            "asset_id": "A1",
            "TEF_min": 1.0, "TEF_mostlikely": 2.0, "TEF_max": 3.0,
            "Vuln_asset": 0.1,
            "LM_lognormal_mu": 10.0, "LM_lognormal_sigma": 0.5
        },
        {
            "asset_id": "A2",
            "TEF_min": 0.0, "TEF_mostlikely": 0.0, "TEF_max": 0.0,
            "Vuln_asset": 0.0,
            "LM_lognormal_mu": 0.0, "LM_lognormal_sigma": 0.0
        }
    ])
    
    res = simulator.apply_to_dataframe(df)
    
    assert "EAL_usd" in res.columns
    assert "VaR95_usd" in res.columns
    assert "VaR99_usd" in res.columns
    assert "LEC_points" in res.columns
    
    assert res.iloc[0]["EAL_usd"] > 0
    assert res.iloc[1]["EAL_usd"] == 0.0
