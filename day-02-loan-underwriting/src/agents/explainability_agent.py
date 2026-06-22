"""
Explainability Agent — uses Azure AI Foundry Agents SDK with GPT-4o to generate
plain-English decision explanations grounded in SHAP feature importances.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    AgentsResponseFormat,
    MessageRole,
    RunStatus,
)
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

EXPLAINABILITY_SYSTEM_PROMPT = """
You are a senior credit risk analyst at a regulated UK financial institution.
Your role is to translate machine-learning credit decisions into clear, human-readable explanations
that satisfy FCA Consumer Duty transparency obligations.

You will receive a JSON object containing:
- application: the loan application fields (income, debt, credit score, payment history, etc.)
- risk_score: ML model probability of default (0.0 = very safe, 1.0 = very likely to default)
- risk_band: LOW | MEDIUM | HIGH | CRITICAL
- shap_values: dictionary mapping feature name → SHAP value (positive = increases default risk)

Your ONLY output must be a single JSON object — no prose, no markdown, no apologies.

Output this exact structure:
{
  "decision": "APPROVE" | "DECLINE" | "REFER",
  "plain_english_explanation": "<2-4 sentence explanation a customer can understand — mention specific figures>",
  "primary_risk_factors": ["<top 3 factors driving the decision, each with a specific value>"],
  "mitigating_factors": ["<positive factors that reduced risk, or empty list>"],
  "customer_message": "<what the customer should be told — warm, compliant, actionable>",
  "analyst_notes": "<internal notes for underwriter review — mention threshold breaches>"
}

Decision thresholds:
- risk_score < 0.25 → APPROVE
- 0.25 ≤ risk_score < 0.50 → REFER (manual review)
- risk_score ≥ 0.50 → DECLINE

GDPR Article 22 requirement: always include at least one actionable suggestion the applicant
can take to improve their credit profile in customer_message.

NEVER output anything except the JSON object.
"""


class ExplainabilityAgent:
    def __init__(self) -> None:
        self._client: AgentsClient | None = None
        self._agent_id: str | None = None

    @property
    def client(self) -> AgentsClient:
        if self._client is None:
            self._client = AgentsClient(
                endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
                credential=DefaultAzureCredential(),
            )
        return self._client

    def _ensure_agent(self) -> str:
        if self._agent_id:
            return self._agent_id

        agent = self.client.create_agent(
            model=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            name="loan-explainability-agent",
            instructions=EXPLAINABILITY_SYSTEM_PROMPT,
            response_format=AgentsResponseFormat(type="json_object"),
        )
        self._agent_id = agent.id
        logger.info("Created explainability agent: %s", agent.id)
        return agent.id

    def explain(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Generate a plain-English explanation of the risk scoring decision.
        Falls back to a rule-based explanation if Azure AI Foundry is unavailable.
        """
        application_id = context["application_id"]

        if not os.environ.get("AI_FOUNDRY_ENDPOINT"):
            logger.info("AI_FOUNDRY_ENDPOINT not set — using rule-based fallback for %s", application_id)
            explanation = self._rule_based_fallback(context)
            return {
                **context,
                "explanation": explanation,
                "final_decision": explanation["decision"],
                "explanation_source": "fallback",
            }

        try:
            agent_id = self._ensure_agent()
        except Exception as exc:
            logger.warning("Could not initialise Azure agent (%s) — falling back for %s", exc, application_id)
            explanation = self._rule_based_fallback(context)
            return {
                **context,
                "explanation": explanation,
                "final_decision": explanation["decision"],
                "explanation_source": "fallback",
            }

        payload = {
            "application": context["application"],
            "risk_score": context["risk_score"],
            "risk_band": context["risk_band"],
            "shap_values": context["shap_values"],
        }

        thread = self.client.threads.create()
        self.client.messages.create(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=json.dumps(payload),
        )

        run = self.client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent_id,
        )

        if run.status != RunStatus.COMPLETED:
            error_detail = run.last_error.message if run.last_error else str(run.status)
            logger.error("Explainability agent run failed for %s: %s", application_id, error_detail)
            explanation = self._rule_based_fallback(context)
            return {**context, "explanation": explanation, "final_decision": explanation["decision"], "explanation_source": "fallback"}

        last_message = self.client.messages.get_last_message_by_role(
            thread_id=thread.id,
            role=MessageRole.AGENT,
        )

        raw = ""
        if last_message:
            for block in last_message.content:
                if hasattr(block, "text") and hasattr(block.text, "value"):
                    raw = block.text.value
                    break

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            explanation = json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            logger.warning("Could not parse explainability JSON for %s, raw: %.200s", application_id, raw)
            explanation = self._rule_based_fallback(context)

        explanation["explained_at"] = datetime.now(timezone.utc).isoformat()
        explanation["agent_run_id"] = run.id

        logger.info(
            "Explanation generated for %s → decision=%s source=llm",
            application_id,
            explanation.get("decision"),
        )

        return {
            **context,
            "explanation": explanation,
            "final_decision": explanation.get("decision", "REFER"),
            "explanation_source": "llm",
        }

    def _rule_based_fallback(self, context: dict) -> dict:
        """Deterministic fallback when Azure AI Foundry is unreachable."""
        risk_score = context.get("risk_score", 0.5)
        risk_band = context.get("risk_band", "MEDIUM")
        app = context.get("application", {})

        dti = app.get("dti_ratio", 0)
        credit_score = app.get("credit_score", 0)
        payment_score = app.get("payment_history_score", 100)

        if risk_score < 0.25:
            decision = "APPROVE"
        elif risk_score < 0.50:
            decision = "REFER"
        else:
            decision = "DECLINE"

        factors = []
        if dti > 0.45:
            factors.append(f"Debt-to-income ratio of {dti:.0%} exceeds 45% threshold")
        if credit_score < 600:
            factors.append(f"Credit score of {credit_score} is below minimum threshold of 600")
        if payment_score < 50:
            factors.append(f"Payment history score of {payment_score}/100 indicates recent missed payments")

        return {
            "decision": decision,
            "plain_english_explanation": (
                f"Based on automated assessment, this application has been assessed as {risk_band} risk "
                f"(probability of default: {risk_score:.1%}). "
                f"The primary concerns are: {'; '.join(factors) if factors else 'overall credit profile'}."
            ),
            "primary_risk_factors": factors or [f"Overall risk score {risk_score:.1%}"],
            "mitigating_factors": [],
            "customer_message": (
                "Thank you for your application. To improve your creditworthiness, consider reducing existing "
                "debt balances and ensuring all payments are made on time over the next 6 months."
            ),
            "analyst_notes": f"Fallback decision — agent unavailable. risk_band={risk_band}, dti={dti:.3f}",
        }
