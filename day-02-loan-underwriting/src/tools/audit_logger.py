"""Tool: Audit logging — records the complete decision trail to MLflow as params, metrics, and artifacts."""
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AuditLogger:
    def log_decision(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Persist the full decision audit trail as an MLflow run.
        The run ID links the decision back to the risk scoring run for traceability.
        """
        import mlflow

        application_id = context.get("application_id", "unknown")
        application = context.get("application", {})
        explanation = context.get("explanation", {})
        compliance = context.get("compliance", {})

        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlruns/mlflow.db"))

        with mlflow.start_run(run_name=f"audit-{application_id}") as run:
            mlflow.log_param("application_id", application_id)
            mlflow.log_param("final_decision", context.get("final_decision", "unknown"))
            mlflow.log_param("risk_band", context.get("risk_band", "unknown"))
            mlflow.log_param("scoring_run_id", context.get("mlflow_run_id", ""))
            mlflow.log_param("explanation_source", context.get("explanation_source", "unknown"))
            mlflow.log_param("gdpr_disclosure_required", compliance.get("gdpr_article_22_disclosure_required", False))
            mlflow.log_param("fca_consumer_duty_met", compliance.get("fca_consumer_duty_met", True))

            mlflow.log_metric("risk_score", round(context.get("risk_score", 0), 4))
            mlflow.log_metric("dti_ratio", round(application.get("dti_ratio", 0), 4))
            mlflow.log_metric("credit_score", application.get("credit_score", 0))
            mlflow.log_metric("compliance_flags_count", len(compliance.get("compliance_flags", [])))
            mlflow.log_metric("applicable_rules_count", len(compliance.get("applicable_rules", [])))

            # Full decision artifact for regulatory audit trail
            full_record = {
                "application_id": application_id,
                "decision": context.get("final_decision"),
                "risk_score": context.get("risk_score"),
                "risk_band": context.get("risk_band"),
                "explanation": explanation,
                "compliance": compliance,
                "shap_values": context.get("shap_values"),
                "audited_at": datetime.now(timezone.utc).isoformat(),
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix=f"audit_{application_id}_", delete=False
            ) as f:
                json.dump(full_record, f, indent=2)
                tmp_path = f.name

            mlflow.log_artifact(tmp_path, artifact_path="audit_trail")
            audit_run_id = run.info.run_id

        logger.info(
            "Audit logged for %s → decision=%s audit_run=%s",
            application_id,
            context.get("final_decision"),
            audit_run_id,
        )

        return {
            **context,
            "audit_run_id": audit_run_id,
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }
