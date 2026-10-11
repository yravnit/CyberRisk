import pandas as pd
import numpy as np

from .config import EngineConfig, DEFAULT_CONFIG

class LossMagnitudeModel:
    """Calculates Primary and Secondary Loss Magnitude parameters per asset."""
    
    def __init__(self, config: EngineConfig = DEFAULT_CONFIG):
        self.config = config
        
    def apply_to_dataframe(self, base_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates loss magnitude parameters for each asset in the asset_risk_base.
        Adds columns: LM_primary_usd, LM_secondary_usd, LM_total_mostlikely_usd,
        LM_lognormal_mu, LM_lognormal_sigma.
        """
        df = base_df.copy()
        
        # Calculate BU averages to use as fallbacks for assets with no historical impact data
        bu_impacts = df.groupby("business_unit").agg(
            bu_avg_downtime=("avg_downtime_hours", "mean"),
            bu_avg_records=("avg_records_compromised", "mean")
        ).reset_index()
        
        df = df.merge(bu_impacts, on="business_unit", how="left")
        
        def calculate_loss(row):
            # 1. Primary Loss
            dt_cost = row.get("downtime_cost_per_hour_usd", 0.0)
            avg_dt = row.get("avg_downtime_hours", 0.0)
            bu_dt = row.get("bu_avg_downtime", 0.0)
            
            # Fallback logic: if asset has no historical downtime, use BU average, else 4.0 hours
            effective_dt = avg_dt if avg_dt > 0 else (bu_dt if bu_dt > 0 else 4.0)
            
            primary_loss = (dt_cost * effective_dt) + self.config.ir_flat_cost_usd
            
            # 2. Secondary Loss
            sensitivity = row.get("data_sensitivity_tier", "Internal")
            record_cost = self.config.per_record_cost_usd.get(sensitivity, 100.0)
            
            avg_rec = row.get("avg_records_compromised", 0.0)
            bu_rec = row.get("bu_avg_records", 0.0)
            reg_penalty = row.get("regulatory_penalty_potential_usd", 0.0)
            
            # Fallback logic: if asset has no historical record loss, use BU average, else default
            effective_rec = avg_rec if avg_rec > 0 else (bu_rec if bu_rec > 0 else self.config.default_records_at_risk)
            
            secondary_loss = (effective_rec * record_cost) + reg_penalty
            
            # 3. Total Most Likely and Lognormal Parameters
            total_ml = primary_loss + secondary_loss
            
            # For a lognormal distribution, if we want the median (P50) to be total_ml:
            # P50 = exp(mu) => mu = ln(P50)
            mu = np.log(total_ml) if total_ml > 0 else 0.0
            sigma = self.config.loss_lognormal_sigma
            
            return pd.Series({
                "LM_primary_usd": primary_loss,
                "LM_secondary_usd": secondary_loss,
                "LM_total_mostlikely_usd": total_ml,
                "LM_lognormal_mu": mu,
                "LM_lognormal_sigma": sigma,
                "LM_downtime_assumption": effective_dt,
                "LM_records_assumption": effective_rec
            })
            
        lm_cols = df.apply(calculate_loss, axis=1)
        df = pd.concat([df, lm_cols], axis=1)
        
        # Clean up temporary BU columns
        df = df.drop(columns=["bu_avg_downtime", "bu_avg_records"])
        return df
