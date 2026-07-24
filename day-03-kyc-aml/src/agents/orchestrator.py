"""
LCEL orchestrator — wires the KYC/AML agents into one composable chain:

    load_context → Identity → Screening → AML-RAG → Decision

Each step receives and returns a context dict, accumulating results without
mutating upstream outputs (the Day 02 pattern). load_context pulls the customer's
subgraph (documents, case, watchlist flags, country, applicable rules) so every
downstream agent shares the same GraphRAG view.
"""
import logging
from typing import Any

from langchain_core.runnables import RunnableLambda

from src.agents.identity_agent import identity_agent
from src.agents.screening_agent import screening_agent
from src.agents.aml_agent import aml_agent
from src.agents.decision_agent import decision_agent
from src.graph.store import graph_store
from src.pipeline.vector_store import vector_store
from src.guardrails.hallucination import hallucination_detector
from src.guardrails import guardrails

logger = logging.getLogger(__name__)


class KYCOrchestrator:
    def __init__(self) -> None:
        self._chain = (
            RunnableLambda(self._load_context)
            | RunnableLambda(identity_agent.verify)
            | RunnableLambda(screening_agent.screen)
            | RunnableLambda(aml_agent.assess)
            | RunnableLambda(decision_agent.decide)
            | RunnableLambda(self._apply_guardrails)
        )

    def _apply_guardrails(self, context: dict[str, Any]) -> dict[str, Any]:
        """Ground the AML findings against sources, then validate the decision."""
        aml = context.get("aml", {})
        report = hallucination_detector.check_findings(
            aml.get("findings", []), context.get("retrieved_context", [])
        )
        guarded = guardrails.validate_output(context.get("decision", {}), report)
        return {**context, "decision": guarded, "hallucination_report": report}

    def _load_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Seed the pipeline with the customer profile + graph subgraph."""
        customer_id = context.get("customer_id") or context.get("customer", {}).get("customer_id")
        subgraph = graph_store.customer_subgraph(customer_id) if customer_id else {}

        # Prefer an explicitly supplied profile; else use the graph's customer node.
        profile = context.get("customer") or subgraph.get("customer", {})
        if customer_id and "customer_id" not in profile:
            profile = {**profile, "customer_id": customer_id}

        return {
            **context,
            "customer_id": customer_id,
            "customer": profile,
            "graph": subgraph,
            "ingested_chunks": context.get("ingested_chunks", []),
        }

    def run(self, customer_id: str | None = None, customer: dict | None = None,
            ingested_chunks: list[dict] | None = None) -> dict[str, Any]:
        initial: dict[str, Any] = {}
        if customer_id:
            initial["customer_id"] = customer_id
        if customer:
            initial["customer"] = customer
        if ingested_chunks:
            initial["ingested_chunks"] = ingested_chunks

        logger.info("Starting KYC pipeline for customer=%s", customer_id or "inline")
        result = self._chain.invoke(initial)
        decision = result.get("decision", {})
        logger.info("KYC pipeline complete → decision=%s risk=%s",
                    decision.get("decision"), decision.get("risk_score"))
        return result

    def health_check(self) -> dict[str, Any]:
        return {
            "vector_store": vector_store.backend,
            "graph_store": graph_store.backend,
            "graph_stats": graph_store.stats(),
        }


orchestrator = KYCOrchestrator()
