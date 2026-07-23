"""
Shared LLM client for the KYC agents — Azure AI Foundry Agents SDK with GPT-4.1.

complete_json() returns a parsed dict on success, or None when the LLM is
unavailable / errors — the caller then uses its deterministic rule-based path.
This is the same progressive-fallback contract used across Day 01/02, extracted
here so the four KYC agents don't each re-implement the SDK boilerplate.

GPT-4.1 is vision-enabled, so the same client handles both text reasoning and
(future) direct image analysis of scanned IDs.
"""
import json
import logging

from src.config import config

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self._client = None
        self._agents: dict[str, str] = {}
        self._available = config.use_azure_openai

    @property
    def available(self) -> bool:
        return self._available

    def _agents_client(self):
        if self._client is None:
            from azure.ai.agents import AgentsClient
            from azure.identity import DefaultAzureCredential

            self._client = AgentsClient(
                endpoint=config.ai_foundry_endpoint,
                credential=DefaultAzureCredential(),
            )
        return self._client

    def _ensure_agent(self, name: str, instructions: str) -> str:
        if name in self._agents:
            return self._agents[name]
        from azure.ai.agents.models import AgentsResponseFormat

        agent = self._agents_client().create_agent(
            model=config.openai_deployment,
            name=name,
            instructions=instructions,
            response_format=AgentsResponseFormat(type="json_object"),
        )
        self._agents[name] = agent.id
        logger.info("Created agent %s (%s)", name, agent.id)
        return agent.id

    def complete_json(self, agent_name: str, system_prompt: str, payload: dict) -> dict | None:
        """Run one prompt→JSON turn. Returns None if the LLM is unavailable/failed."""
        if not self._available:
            return None
        try:
            from azure.ai.agents.models import MessageRole, RunStatus

            client = self._agents_client()
            agent_id = self._ensure_agent(agent_name, system_prompt)
            thread = client.threads.create()
            client.messages.create(
                thread_id=thread.id, role=MessageRole.USER,
                content=json.dumps(payload, default=str),
            )
            run = client.runs.create_and_process(thread_id=thread.id, agent_id=agent_id)
            if run.status != RunStatus.COMPLETED:
                detail = run.last_error.message if run.last_error else str(run.status)
                logger.error("Agent %s run failed: %s", agent_name, detail)
                return None

            msg = client.messages.get_last_message_by_role(
                thread_id=thread.id, role=MessageRole.AGENT
            )
            raw = ""
            if msg:
                for block in msg.content:
                    if hasattr(block, "text") and hasattr(block.text, "value"):
                        raw = block.text.value
                        break
            return self._extract_json(raw)
        except Exception as exc:
            logger.warning("LLM call failed for %s (%s) — falling back", agent_name, exc)
            self._available = False
            return None

    @staticmethod
    def _extract_json(raw: str) -> dict | None:
        try:
            start, end = raw.find("{"), raw.rfind("}") + 1
            return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            logger.warning("Could not parse LLM JSON, raw: %.200s", raw)
            return None


llm = LLMClient()
