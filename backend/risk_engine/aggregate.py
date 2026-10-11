import pandas as pd
from typing import Dict, Any

from .config import EngineConfig, DEFAULT_CONFIG

class RiskAggregator:
    """Aggregates simulated risk metrics to Asset, Business Unit, and Organizational levels."""
    
    def __init__(self, config: EngineConfig = DEFAULT_CONFIG):
        self.config = config
        
    def aggregate(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Takes the fully simulated DataFrame and returns aggregated datasets.
        """
        # 1. Asset Level Summary
        # priority_score = EAL * (criticality / 5) -> for ranking, not for dollar total
        asset_summary = df[[
            "asset_id", "business_unit", "criticality", 
            "EAL_usd", "VaR95_usd", "VaR99_usd", "LEC_points"
        ]].copy()
        
        asset_summary["priority_score"] = asset_summary["EAL_usd"] * (asset_summary["criticality"] / 5.0)
        
        # Sort by priority
        asset_summary = asset_summary.sort_values(by="priority_score", ascending=False).reset_index(drop=True)
        
        # 2. Business Unit Level Summary
        # Documented assumption: Summing VaR95 across assets assumes perfect correlation or uses an upper bound.
        # Summing EAL assumes independence, which is valid for expected values.
        bu_summary = df.groupby("business_unit").agg(
            total_EAL_usd=("EAL_usd", "sum"),
            total_VaR95_usd_upper_bound=("VaR95_usd", "sum")
        ).reset_index()
        
        # Get top risk contributors per BU
        def get_top_contributors(bu_name):
            bu_assets = asset_summary[asset_summary["business_unit"] == bu_name]
            top = bu_assets.head(5)[["asset_id", "EAL_usd"]].to_dict(orient="records")
            return top
            
        bu_summary["top_contributors"] = bu_summary["business_unit"].apply(get_top_contributors)
        
        # 3. Organization Level Summary
        org_eal = df["EAL_usd"].sum()
        org_var95_upper = df["VaR95_usd"].sum()
        
        org_summary = pd.DataFrame([{
            "organization_name": "Enterprise",
            "total_EAL_usd": org_eal,
            "total_VaR95_usd_upper_bound": org_var95_upper,
            "note": "Aggregation assumes independence for EAL. VaR summation is an upper bound."
        }])
        
        return {
            "asset_risk_summary": asset_summary,
            "business_unit_risk_summary": bu_summary,
            "org_risk_summary": org_summary
        }
