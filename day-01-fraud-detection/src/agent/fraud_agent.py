"""
Fraud Detection Agent using Azure AI Foundry Agents SDK.
Orchestrates multi-tool reasoning over real-time transaction events.
"""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Any

from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    FunctionTool,
    ToolSet,
    MessageRole,
    RunStatus,
    AgentsResponseFormat,
)
from azure.identity import DefaultAzureCredential

from .tools.transaction_history import get_transaction_history
from .tools.velocity_check import check_velocity
from .tools.geolocation_risk import assess_geolocation_risk
from .tools.blacklist_check import check_blacklist

logger = logging.getLogger(__name__)


FRAUD_AGENT_INSTRUCTIONS = """
You are an enterprise fraud detection specialist for a banking system.
Your ONLY output must be a single JSON object — no prose, no explanations, no markdown.

STEP 1: Call all four tools (call them even if a previous one fails):
- get_transaction_history(customer_id, limit=30)
- check_velocity(customer_id, current_amount, current_timestamp)
- assess_geolocation_risk(customer_id, current_country, current_lat, current_lon, current_timestamp, previous_country, previous_lat, previous_lon, previous_timestamp) — use "US" and 0.0/0.0 as previous values if unknown
- check_blacklist(merchant_id, ip_address, device_fingerprint, card_number_hash)

STEP 2: Regardless of whether any tool call succeeded or returned an error, output ONLY this JSON:
{
  "transaction_id": "<id from input>",
  "fraud_score": <integer 0-100>,
  "risk_level": "<LOW|MEDIUM|HIGH|CRITICAL>",
  "decision": "<APPROVE|REVIEW|BLOCK>",
  "signals": ["<list of triggered signals or DATA_UNAVAILABLE if tools failed>"],
  "reasoning": "<concise explanation based on available data>",
  "recommended_action": "<what the ops team should do>"
}

Risk level thresholds:
- fraud_score 0-29  → LOW    → APPROVE
- fraud_score 30-59 → MEDIUM → REVIEW
- fraud_score 60-79 → HIGH   → REVIEW (urgent)
- fraud_score 80+   → CRITICAL → BLOCK

If tools return errors, use fraud_score 40, risk_level MEDIUM, decision REVIEW, signals ["DATA_UNAVAILABLE"].
NEVER output anything except the JSON object. Do not explain. Do not apologise. Output JSON only.
"""


class FraudDetectionAgent:
    def __init__(self):
        self._client: AgentsClient | None = None
        self._agent_id: str | None = None
        self._toolset = self._build_toolset()

    def _build_toolset(self) -> ToolSet:
        toolset = ToolSet()
        toolset.add(FunctionTool(functions={
            get_transaction_history,
            check_velocity,
            assess_geolocation_risk,
            check_blacklist,
        }))
        return toolset

    @property
    def client(self) -> AgentsClient:
        if self._client is None:
            # AgentsClient connects directly to the Azure OpenAI endpoint
            # (no AI Foundry Hub routing — avoids ResourceNotFoundError on Hub connections)
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
            name="fraud-detection-agent",
            instructions=FRAUD_AGENT_INSTRUCTIONS,
            toolset=self._toolset,
            response_format=AgentsResponseFormat(type="json_object"),
        )
        self._agent_id = agent.id
        logger.info("Created fraud detection agent: %s", agent.id)
        return agent.id

    def analyze_transaction(self, transaction: dict[str, Any]) -> dict[str, Any]:
        agent_id = self._ensure_agent()

        # Create thread
        thread = self.client.threads.create()

        # Post the transaction as a user message
        self.client.messages.create(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=json.dumps(transaction),
        )

        # Run the agent — blocks until terminal state, auto-executes tool calls
        run = self.client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent_id,
            toolset=self._toolset,
        )

        if run.status != RunStatus.COMPLETED:
            error_detail = run.last_error.message if run.last_error else str(run.status)
            logger.error("Agent run failed: %s — %s", run.status, error_detail)
            return self._fallback_decision(transaction, error_detail)

        # Retrieve the last assistant message
        last_message = self.client.messages.get_last_message_by_role(
            thread_id=thread.id,
            role=MessageRole.AGENT,
        )

        if not last_message:
            return self._fallback_decision(transaction, "No agent response")

        raw = ""
        for block in last_message.content:
            if hasattr(block, "text") and hasattr(block.text, "value"):
                raw = block.text.value
                break

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            decision = json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            logger.warning("Could not parse agent JSON, raw: %s", raw[:200])
            return self._fallback_decision(transaction, "JSON parse error")

        decision["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        decision["agent_run_id"] = run.id
        decision["thread_id"] = thread.id

        logger.info(
            "Transaction %s → %s (score: %s)",
            transaction.get("transaction_id"),
            decision.get("decision"),
            decision.get("fraud_score"),
        )
        return decision

    def _fallback_decision(self, transaction: dict, reason: str) -> dict:
        return {
            "transaction_id": transaction.get("transaction_id", "unknown"),
            "fraud_score": 50,
            "risk_level": "MEDIUM",
            "decision": "REVIEW",
            "signals": ["agent_error"],
            "reasoning": f"Agent unavailable — manual review required. Error: {reason}",
            "recommended_action": "Escalate to fraud analyst immediately",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "agent_run_id": None,
            "thread_id": None,
        }
