"""
LangChain LCEL orchestrator — wires ETL → Risk Scoring → Explainability → Compliance → Audit
into a single composable chain with structured context passing between agents.
"""
import logging
from typing import Any

from langchain_core.runnables import RunnableLambda

from src.agents.etl_agent import ETLAgent
from src.agents.risk_scoring_agent import RiskScoringAgent
from src.agents.explainability_agent import ExplainabilityAgent
from src.agents.compliance_agent import ComplianceAgent
from src.tools.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class LoanIntelligenceOrchestrator:
    def __init__(self) -> None:
        self.etl_agent = ETLAgent()
        self.risk_scoring_agent = RiskScoringAgent()
        self.explainability_agent = ExplainabilityAgent()
        self.compliance_agent = ComplianceAgent()
        self.audit_logger = AuditLogger()
        self._chain = self._build_chain()

    def _build_chain(self):
        chain = (
            RunnableLambda(self.etl_agent.process)
            | RunnableLambda(self.risk_scoring_agent.score)
            | RunnableLambda(self.explainability_agent.explain)
            | RunnableLambda(self.compliance_agent.check)
            | RunnableLambda(self.audit_logger.log_decision)
        )
        return chain

    def process_application(self, application: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the full loan intelligence pipeline for a single application.
        The LCEL chain passes a context dict through each agent,
        accumulating results without mutating upstream outputs.
        """
        initial_context = {"application": application}
        logger.info(
            "Starting loan intelligence pipeline for application: %s",
            application.get("application_id", "new"),
        )
        result = self._chain.invoke(initial_context)
        logger.info(
            "Pipeline complete for %s → decision=%s risk_band=%s",
            result.get("application_id"),
            result.get("final_decision"),
            result.get("risk_band"),
        )
        return result

    def health_check(self) -> dict[str, Any]:
        """Report which pipeline components are reachable."""
        import os

        status = {
            "etl_agent": "ok",
            "risk_model": "unknown",
            "explainability_agent": "unknown",
            "compliance_kb": "unknown",
            "mlflow": "unknown",
        }

        model_path = os.environ.get("MODEL_PATH", "models/credit_risk_model.pkl")
        import pathlib
        status["risk_model"] = "ok" if pathlib.Path(model_path).exists() else "model_file_missing"

        try:
            kb_count = self.compliance_agent.kb_collection.count()
            status["compliance_kb"] = f"ok ({kb_count} rules)"
        except Exception as exc:
            status["compliance_kb"] = f"error: {exc}"

        try:
            import mlflow
            import os as _os
            mlflow.set_tracking_uri(_os.environ.get("MLFLOW_TRACKING_URI", "mlruns"))
            status["mlflow"] = "ok"
        except Exception as exc:
            status["mlflow"] = f"error: {exc}"

        ai_endpoint = os.environ.get("AI_FOUNDRY_ENDPOINT", "")
        status["explainability_agent"] = "ok" if ai_endpoint else "AI_FOUNDRY_ENDPOINT not set"

        return status
