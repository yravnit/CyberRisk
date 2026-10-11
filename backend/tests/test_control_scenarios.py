import pytest
import pandas as pd
import numpy as np

from risk_engine.control_scenarios import ControlScenarios
from risk_engine.config import EngineConfig

@pytest.fixture
def scenarios():
    config = EngineConfig(n_simulations=1000, random_seed=42)
    return ControlScenarios(config)

def test_evaluate_scenarios(scenarios):
    # Setup base DataFrame with one asset that has 1 active control
    base_df = pd.DataFrame([
        {
            "asset_id": "A1",
            "active_controls": ["CTRL-01"],
            "total_risk_reduction_pct": 0.5,
            "vuln_list": [{"epss_score": 0.5, "cvss_score": 10.0}],
            "TEF_min": 5.0, "TEF_mostlikely": 10.0, "TEF_max": 20.0,
            "Vuln_asset": 0.5, # Assume already calculated
            "LM_lognormal_mu": 10.0,
            "LM_lognormal_sigma": 0.5,
            "EAL_usd": 100000.0 # Baseline EAL
        },
        {
            "asset_id": "A2",
            "active_controls": [],
            "total_risk_reduction_pct": 0.0,
            "vuln_list": [],
            "TEF_min": 0.0, "TEF_mostlikely": 0.0, "TEF_max": 0.0,
            "Vuln_asset": 0.0,
            "LM_lognormal_mu": 0.0,
            "LM_lognormal_sigma": 0.0,
            "EAL_usd": 0.0 # Asset with 0 risk
        }
    ])
    
    # Setup candidate controls
    controls_df = pd.DataFrame([
        {"control_id": "CTRL-01", "name": "Control 1", "risk_reduction_pct": 0.5, "cost_usd": 10000.0},
        {"control_id": "CTRL-02", "name": "Control 2", "risk_reduction_pct": 0.4, "cost_usd": 20000.0},
    ])
    
    res = scenarios.evaluate_scenarios(base_df, controls_df)
    
    # Asset A2 has 0 baseline EAL, should be skipped entirely
    assert len(res[res["asset_id"] == "A2"]) == 0
    
    # Asset A1 already has CTRL-01, so it should only evaluate CTRL-02
    a1_res = res[res["asset_id"] == "A1"]
    assert len(a1_res) == 1
    
    scenario = a1_res.iloc[0]
    assert scenario["control_id"] == "CTRL-02"
    assert scenario["EAL_before"] == 100000.0
    
    # EAL after should be less than EAL before because risk reduction increased
    assert scenario["EAL_after"] < scenario["EAL_before"]
    
    # Risk reduction = EAL_before - EAL_after
    expected_reduction = scenario["EAL_before"] - scenario["EAL_after"]
    assert np.isclose(scenario["Risk_Reduction_usd"], expected_reduction)
    
    # ROSI = Risk reduction / cost
    expected_rosi = expected_reduction / 20000.0
    assert np.isclose(scenario["ROSI"], expected_rosi)

def test_multiplicative_aggregation_scenario(test_data_dir=None):
    # Optional test if we want to ensure multiplicative config works correctly
    pass
