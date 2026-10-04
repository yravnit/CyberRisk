import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_validate
from typing import Tuple, Dict, Any, List

class VulnerabilityPredictor:
    def __init__(self):
        self._label_source = "none"
        self._label_source_detail = ""
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            xgb_fallback = GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, random_state=42)
        except Exception:
            xgb_fallback = RandomForestClassifier(n_estimators=100, random_state=42)
        self.models = {
            "random_forest": self.model,
            "xgboost": xgb_fallback
        }
        self.feature_names = []
        self.is_trained = False
        self.metrics = {}
        
    def prepare_features(self, raw_data: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.Series]:
        """Extract features and target labels from raw data."""
        # Convert inputs to DataFrames if they aren't already
        vulns = raw_data.get("vulnerabilities", [])
        if not isinstance(vulns, pd.DataFrame):
            vulns = pd.DataFrame(vulns)
            
        assets = raw_data.get("assets", [])
        if not isinstance(assets, pd.DataFrame):
            assets = pd.DataFrame(assets)
            
        threat_events = raw_data.get("threat_events", [])
        if not isinstance(threat_events, pd.DataFrame):
            threat_events = pd.DataFrame(threat_events)
            
        controls = raw_data.get("asset_controls", [])
        if not isinstance(controls, pd.DataFrame):
            controls = pd.DataFrame(controls)
            
        if vulns.empty:
            return pd.DataFrame(), pd.Series()
            
        # Merge vulnerability with asset info
        df = vulns.merge(assets, on="asset_id", suffixes=("", "_asset"))
        
        # Calculate epss_annual
        df["epss_score"] = df["epss_score"].fillna(0.01).astype(float)
        df["epss_annual"] = 1 - (1 - df["epss_score"])**(365/30)
        
        # Calculate asset_criticality
        df["asset_criticality"] = df["criticality"].fillna(3).astype(float)
        
        # Calculate data_sensitivity_numeric
        sensitivity_map = {"Public": 1, "Internal": 2, "Confidential": 3, "Restricted": 4}
        df["data_sensitivity_numeric"] = df["data_sensitivity_tier"].map(sensitivity_map).fillna(2.0).astype(float)
        
        # Calculate control_coverage
        control_coverage = {}
        if not controls.empty:
            control_defs = raw_data.get("controls", [])
            if not isinstance(control_defs, pd.DataFrame):
                control_defs = pd.DataFrame(control_defs)
            
            if not control_defs.empty and "control_id" in controls.columns:
                merged_ctrls = controls.merge(control_defs, on="control_id", how="left")
                if "risk_reduction_pct" in merged_ctrls.columns:
                    grouped = merged_ctrls.groupby("asset_id")["risk_reduction_pct"].sum()
                    control_coverage = grouped.to_dict()
        df["control_coverage"] = df["asset_id"].map(control_coverage).fillna(0.0)
        df["control_coverage"] = df["control_coverage"].clip(0, 1.0)
        
        # Calculate vuln_age_days
        now = pd.Timestamp.now(tz='UTC').tz_localize(None)
        if "discovery_date" in df.columns:
            disc_date = pd.to_datetime(df["discovery_date"]).dt.tz_localize(None)
            df["vuln_age_days"] = (now - disc_date).dt.days.fillna(0.0).astype(float)
        else:
            df["vuln_age_days"] = 30.0
            
        # Calculate asset_event_count
        event_counts = {}
        if not threat_events.empty and "asset_id" in threat_events.columns:
            event_counts = threat_events.groupby("asset_id").size().to_dict()
        df["asset_event_count"] = df["asset_id"].map(event_counts).fillna(0).astype(float)
        
        # Calculate asset_financial_value_log
        df["asset_financial_value_log"] = np.log1p(df["financial_value_usd"].fillna(0).astype(float))
        
        # Calculate has_open_critical
        if "severity" in vulns.columns:
            critical_vulns = vulns[vulns["severity"].astype(str).str.lower() == "critical"]
        elif "cvss_score" in vulns.columns:
            critical_vulns = vulns[vulns["cvss_score"].astype(float) >= 9.0]
        else:
            critical_vulns = pd.DataFrame()

        critical_counts = critical_vulns.groupby("asset_id").size().to_dict() if not critical_vulns.empty and "asset_id" in critical_vulns.columns else {}
        df["has_open_critical"] = df["asset_id"].map(lambda aid: 1.0 if critical_counts.get(aid, 0) > 0 else 0.0)
        
        # ------------------------------------------------------------------
        # Target label: OBSERVED non-blocked exploitation, not a formula.
        #
        # threat_events.action_taken == "Allowed" is the only direct evidence in
        # the dataset that an attack was NOT stopped. A vulnerability is
        # labelled exploited (1) when its asset produced at least one Allowed
        # event in the observation window.
        #
        # The previous label was epss_annual * (cvss/10) thresholded at its own
        # 70th percentile -- computed from epss_annual and cvss_score, which
        # are themselves input features. The model was learning its own label
        # definition, which inflated F1 to ~0.88 and made EPSS the dominant
        # "importance" for no real reason.
        #
        # Granularity limit: labels are observable at ASSET level (events carry
        # no cve_id), so every vulnerability on a hit asset inherits that
        # asset's outcome. Reported metrics reflect that, not per-CVE accuracy.
        # ------------------------------------------------------------------
        df["has_allowed_events"] = 0
        self._label_source = "none"

        if not threat_events.empty and "asset_id" in threat_events.columns:
            status_col = ("action_taken" if "action_taken" in threat_events.columns
                          else ("status" if "status" in threat_events.columns else None))
            if status_col:
                non_blocked = threat_events[
                    threat_events[status_col].astype(str).str.lower().isin(["allowed"])
                ]
                exploited_assets = set(non_blocked["asset_id"])
                if exploited_assets:
                    df["has_allowed_events"] = df["asset_id"].isin(exploited_assets).astype(int)
                    self._label_source = "observed_allowed_events"
                else:
                    self._label_source = "no_allowed_events_fallback"
            else:
                self._label_source = "no_action_column_fallback"
        else:
            self._label_source = "no_threat_events_fallback"

        if self._label_source != "observed_allowed_events":
            # No usable exploitation evidence in this dataset. Emit no labels
            # rather than fabricate a target from the feature space.
            self._label_source_detail = (
                "Dataset contains no non-blocked threat events, so there is no "
                "observed exploitation outcome to learn from. Predictor skipped."
            )
            return pd.DataFrame(), pd.Series(dtype=int)

        y = df["has_allowed_events"]

        features = [
            "cvss_score", "epss_score", "epss_annual", "asset_criticality",
            "data_sensitivity_numeric", "control_coverage", "vuln_age_days",
            "asset_event_count", "asset_financial_value_log", "has_open_critical"
        ]
        
        X = df[features].fillna(0.0)
        self.feature_names = features
        return X, y
        
    def train(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, Any]:
        if len(X) < 5 or len(y.unique()) < 2:
            try:
                self.models["random_forest"].fit(X, y)
                self.models["xgboost"].fit(X, y)
            except Exception:
                pass
            self.is_trained = True
            return {"error": "Not enough data for cross-validation"}
            
        try:
            import xgboost as xgb
            xgb_model = xgb.XGBClassifier(n_estimators=100, learning_rate=0.1, random_state=42, eval_metric="logloss")
        except (ImportError, Exception):
            from sklearn.ensemble import GradientBoostingClassifier
            xgb_model = GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, random_state=42)

        self.models = {
            "random_forest": self.model,
            "xgboost": xgb_model
        }
        
        # The exploitation label is imbalanced (most assets show at least one
        # non-blocked event), so plain F1 flatters a model that just predicts
        # the majority class. Report balanced metrics and the majority-class
        # baseline alongside, so the headline number can be read honestly.
        pos_rate = float(y.mean()) if len(y) else 0.0
        majority_f1 = round(2 * pos_rate / (1 + pos_rate), 3) if pos_rate else 0.0

        self.metrics = {}
        for name, model in self.models.items():
            cv_results = cross_validate(
                model, X, y, cv=5,
                scoring=['f1', 'precision', 'recall', 'f1_macro', 'accuracy'],
            )
            model.fit(X, y)

            importances = model.feature_importances_
            sorted_indices = np.argsort(importances)[::-1]
            feat_imp = [(self.feature_names[i], float(importances[i])) for i in sorted_indices]

            self.metrics[name] = {
                "cv_f1_scores": cv_results['test_f1'].tolist(),
                "mean_f1": float(np.mean(cv_results['test_f1'])),
                "precision": float(np.mean(cv_results['test_precision'])),
                "recall": float(np.mean(cv_results['test_recall'])),
                "mean_f1_macro": float(np.mean(cv_results['test_f1_macro'])),
                "accuracy": float(np.mean(cv_results['test_accuracy'])),
                "feature_importance": feat_imp,
            }

        self.metrics["_meta"] = {
            "label_source": self._label_source,
            "label_detail": (
                "Positive label = the vulnerability's asset recorded at least one "
                "threat event with action_taken='Allowed' (not blocked) in the "
                "observation window. Events carry no cve_id, so the label is "
                "observed at asset level and shared by every vulnerability on "
                "that asset."
            ),
            "n_samples": int(len(X)),
            "positive_rate": round(pos_rate, 3),
            "majority_class_f1": majority_f1,
            "label_granularity": "asset",
        }

        self.is_trained = True
        return self.metrics
        
    def predict(self, X: pd.DataFrame) -> dict:
        if not self.is_trained:
            raise ValueError("Model not trained")
        # Ensure features are in order
        X_aligned = X[self.feature_names].fillna(0.0) if self.feature_names else X.fillna(0.0)
        n_samples = len(X_aligned)
        
        preds = {}
        for name, model in self.models.items():
            try:
                probs = model.predict_proba(X_aligned)
                if probs.shape[1] > 1:
                    preds[name] = probs[:, 1]
                else:
                    preds[name] = probs[:, 0]
            except Exception:
                preds[name] = np.full(n_samples, 0.5)
        return preds
        
    def get_feature_importance(self) -> List[Tuple[str, float]]:
        # For backwards compatibility, return RF
        return self.metrics.get("random_forest", {}).get("feature_importance", [])
