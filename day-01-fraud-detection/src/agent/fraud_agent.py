"""
Fraud Detection Agent using Azure AI Foundry Agents SDK.
Orchestrates multi-tool reasoning over real-time transaction events.
"""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentThread,
    MessageRole,
    RunStatus,
    FunctionTool,
    ToolSet,
)
from azure.identity import DefaultAzureCredential

from .tools.transaction_history import get_transaction_history
from .tools.velocity_check import check_velocity
from .tools.geolocation_risk import assess_geolocation_risk
from .tools.blacklist_check import check_blacklist

logger = logging.getLogger(__name__)


FRAUD_AGENT_INSTRUCTIONS = """
You are an enterprise fraud detection specialist for a banking system.

When given a transaction, you MUST:
1. Call get_transaction_history to retrieve the customer's last 30 transactions
2. Call check_velocity to detect unusual spend frequency or amount spikes
3. Call assess_geolocation_risk to flag impossible travel or high-risk regions
4. Call check_blacklist to verify merchant/device/IP against known fraud lists

Then produce a JSON decision in this exact format:
{
  "transaction_id": "<id>",
  "fraud_score": <0-100>,
  "risk_level": "<LOW|MEDIUM|HIGH|CRITICAL>",
  "decision": "<APPROVE|REVIEW|BLOCK>",
  "signals": ["<list of triggered signals>"],
  "reasoning": "<concise explanation>",
  "recommended_action": "<what the ops team should do>"
}

Risk level thresholds:
- fraud_score 0-29  → LOW    → APPROVE
- fraud_score 30-59 → MEDIUM → REVIEW (escalate to analyst)
- fraud_score 60-79 → HIGH   → REVIEW (urgent escalation)
- fraud_score 80+   → CRITICAL → BLOCK (auto-block card)

Always err on the side of customer safety. Be explainable and concise.
"""


class FraudDetectionAgent:
    def __init__(self):
        self._client: AIProjectClient | None = None
        self._agent_id: str | None = None
        self._toolset = self._build_toolset()

    def _build_toolset(self) -> ToolSet:
        functions = FunctionTool(
            functions=[
                get_transaction_history,
                check_velocity,
                assess_geolocation_risk,
                check_blacklist,
            ]
        )
        toolset = ToolSet()
        toolset.add(functions)
        return toolset

    @property
    def client(self) -> AIProjectClient:
        if self._client is None:
            self._client = AIProjectClient.from_connection_string(
                credential=DefaultAzureCredential(),
                conn_str=os.environ["AI_FOUNDRY_CONNECTION_STRING"],
            )
        return self._client

    def _ensure_agent(self) -> str:
        if self._agent_id:
            return self._agent_id

        agent = self.client.agents.create_agent(
            model=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            name="fraud-detection-agent",
            instructions=FRAUD_AGENT_INSTRUCTIONS,
            toolset=self._toolset,
        )
        self._agent_id = agent.id
        logger.info("Created fraud detection agent: %s", agent.id)
        return agent.id

    def analyze_transaction(self, transaction: dict[str, Any]) -> dict[str, Any]:
        agent_id = self._ensure_agent()

        thread: AgentThread = self.client.agents.create_thread()

        self.client.agents.create_message(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=json.dumps(transaction),
        )

        run = self.client.agents.create_and_process_run(
            thread_id=thread.id,
            agent_id=agent_id,
            toolset=self._toolset,
        )

        if run.status != RunStatus.COMPLETED:
            logger.error("Agent run failed: %s — %s", run.status, run.last_error)
            return self._fallback_decision(transaction, str(run.last_error))

        messages = self.client.agents.list_messages(thread_id=thread.id)
        last_message = next(
            (m for m in messages.data if m.role == MessageRole.ASSISTANT), None
        )

        if not last_message:
            return self._fallback_decision(transaction, "No agent response")

        raw = last_message.content[0].text.value if last_message.content else ""

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            decision = json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            logger.warning("Could not parse agent JSON, raw: %s", raw[:200])
            decision = self._fallback_decision(transaction, "JSON parse error")

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
