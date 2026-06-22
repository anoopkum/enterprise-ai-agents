"""
Risk Scoring Agent — loads the trained RandomForest model, scores a loan application,
returns probability + risk band, and tracks each scoring run with MLflow.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

RISK_BANDS = [
    (0.0, 0.25, "LOW"),
    (0.25, 0.50, "MEDIUM"),
    (0.50, 0.75, "HIGH"),
    (0.75, 1.01, "CRITICAL"),
]


def _band(probability: float) -> str:
    for low, high, label in RISK_BANDS:
        if low <= probability < high:
            return label
    return "CRITICAL"


class RiskScoringAgent:
    def __init__(self) -> None:
        self._model = None
        self._feature_names: list[str] | None = None

    @property
    def model(self):
        if self._model is None:
            self._model, self._feature_names = self._load_model()
        return self._model

    def _load_model(self):
        import pickle
        model_path = os.environ.get("MODEL_PATH", "models/credit_risk_model.pkl")
        features_path = os.environ.get("FEATURE_NAMES_PATH", "models/feature_names.json")

        with open(model_path, "rb") as f:
            model = pickle.load(f)

        with open(features_path) as f:
            feature_names = json.load(f)

        logger.info("Loaded credit risk model from %s (%d features)", model_path, len(feature_names))
        return model, feature_names

    def score(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Score the enriched application from ETLAgent context.
        Logs params, metrics, and SHAP values as an MLflow run artifact.
        """
        import mlflow
        from src.tools.model_inference import build_feature_vector, compute_shap_values

        application = context["application"]
        application_id = context["application_id"]

        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlruns/mlflow.db"))

        with mlflow.start_run(run_name=f"score-{application_id}") as run:
            mlflow.log_param("application_id", application_id)
            mlflow.log_param("model_version", os.environ.get("MODEL_VERSION", "1.0.0"))
            mlflow.log_param("model_path", os.environ.get("MODEL_PATH", "models/credit_risk_model.pkl"))

            model = self.model  # triggers lazy load, sets self._feature_names
            feature_vector = build_feature_vector(application, self._feature_names)
            probability = float(model.predict_proba([feature_vector])[0][1])
            risk_band = _band(probability)

            mlflow.log_metric("risk_score", round(probability, 4))
            mlflow.log_metric("credit_score", application.get("credit_score", 0))
            mlflow.log_metric("dti_ratio", round(application.get("dti_ratio", 0), 4))
            mlflow.log_metric("credit_utilisation_rate", round(application.get("credit_utilisation_rate", 0), 4))

            shap_values = compute_shap_values(self.model, feature_vector, self._feature_names)

            shap_path = f"/tmp/shap_{application_id}.json"
            with open(shap_path, "w") as f:
                json.dump(shap_values, f)
            mlflow.log_artifact(shap_path, artifact_path="shap")

            run_id = run.info.run_id

        logger.info(
            "Scored %s → probability=%.4f risk_band=%s mlflow_run=%s",
            application_id,
            probability,
            risk_band,
            run_id,
        )

        return {
            **context,
            "risk_score": probability,
            "risk_band": risk_band,
            "shap_values": shap_values,
            "mlflow_run_id": run_id,
        }
