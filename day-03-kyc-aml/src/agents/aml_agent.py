"""
AML/Compliance RAG Agent — the core retrieval-augmented reasoning step.

Pipeline per customer:
  1. Build a compliance query from the customer profile + screening hits.
  2. Retrieve regulatory chunks from the vector store (hybrid BM25+vector).
  3. Rerank (Azure semantic | cross-encoder | lexical) → top_k_rerank.
  4. Fuse in the AML rules that GraphRAG says apply to this customer's country
     (relationships the vector search alone would miss).
  5. GPT-4o reasons over the fused context and returns a JSON compliance
     assessment; a deterministic rule-based path covers the no-LLM case.

Every citation the LLM is allowed to use is passed in retrieved_context, so the
guardrail layer can later check each claim against a real source.
"""
import logging
from typing import Any

from src.config import config
from src.agents.llm import llm
from src.pipeline.vector_store import vector_store
from src.pipeline.reranker import reranker
from src.graph.store import graph_store

logger = logging.getLogger(__name__)

AML_SYSTEM_PROMPT = """
You are a senior AML/KYC compliance officer at a regulated bank. You assess a
customer against the retrieved regulatory context and screening results.

You receive JSON with: customer (profile), screening (PEP/sanction hits),
identity (verification state), and retrieved_context (a numbered list of
regulatory rules and guidelines — these are your ONLY permitted sources).

Rules:
- Ground every finding in retrieved_context. Cite the rule/guideline by its id.
- Do NOT invent rules, thresholds, or facts not present in the context.
- If the context is insufficient to conclude, say so and recommend EDD.

Output ONLY this JSON object:
{
  "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "risk_score": <float 0.0-1.0>,
  "findings": [{"finding": "<text>", "citation": "<rule/guideline id>", "severity": "LOW|MEDIUM|HIGH|CRITICAL"}],
  "rationale": "<2-4 sentences grounded in the cited rules>",
  "recommended_decision": "APPROVE" | "EDD" | "REJECT"
}
NEVER output anything except the JSON object.
"""


class AMLAgent:
    def assess(self, context: dict[str, Any]) -> dict[str, Any]:
        profile = context.get("customer", {})
        screening = context.get("screening", {})
        query = self._build_query(profile, screening)

        # 1-3: retrieve + rerank
        hits = vector_store.search(query, top_k=config.top_k_retrieve)
        ranked = reranker.rerank(query, hits, top_k=config.top_k_rerank)

        # 4: fuse GraphRAG rules for the customer's country
        graph_rules = self._graph_rules(context)
        retrieved_context = self._format_context(ranked, graph_rules)

        # 5: LLM reasoning, else deterministic
        payload = {
            "customer": profile,
            "screening": screening,
            "identity": context.get("identity", {}),
            "retrieved_context": retrieved_context,
        }
        assessment = llm.complete_json("kyc-aml-agent", AML_SYSTEM_PROMPT, payload)
        source = "llm"
        if assessment is None:
            assessment = self._rule_based(context, retrieved_context)
            source = "fallback"

        assessment["assessment_source"] = source
        result = {
            **context,
            "aml": assessment,
            "retrieved_context": retrieved_context,
            "retrieval_query": query,
        }
        logger.info("AML: risk=%s decision=%s (%s), %d context items",
                    assessment.get("risk_level"), assessment.get("recommended_decision"),
                    source, len(retrieved_context))
        return result

    @staticmethod
    def _build_query(profile: dict, screening: dict) -> str:
        parts = [
            "AML KYC compliance requirements for",
            profile.get("occupation", ""),
            "customer in", profile.get("nationality", ""),
            f"risk category {profile.get('risk_category', '')}",
        ]
        if screening.get("is_pep"):
            parts.append("politically exposed person enhanced due diligence")
        if screening.get("is_sanctioned"):
            parts.append("sanctions screening prohibited")
        return " ".join(p for p in parts if p).strip()

    @staticmethod
    def _graph_rules(context: dict) -> list[dict]:
        graph = context.get("graph", {})
        rules = graph.get("rules", [])
        if rules:
            return rules[:config.top_k_rerank]
        countries = graph.get("countries", [])
        if countries:
            return graph_store.applicable_rules(countries[0], limit=config.top_k_rerank)
        return []

    @staticmethod
    def _format_context(ranked: list[dict], graph_rules: list[dict]) -> list[dict]:
        ctx: list[dict] = []
        for h in ranked:
            meta = h.get("metadata", {}) or {}
            ctx.append({
                "id": h.get("chunk_id") or meta.get("reference") or "vector-hit",
                "source": "vector_search",
                "framework": meta.get("framework", ""),
                "text": h.get("text", "")[:800],
                "score": round(float(h.get("rerank_score", h.get("score", 0.0)) or 0.0), 4),
            })
        for r in graph_rules:
            ctx.append({
                "id": r.get("rule_id", "aml-rule"),
                "source": "graph",
                "framework": "AML",
                "text": f"{r.get('title', '')} ({r.get('category', '')}): {r.get('text', '')}"[:800],
                "score": None,
            })
        return ctx

    @staticmethod
    def _rule_based(context: dict, retrieved_context: list[dict]) -> dict:
        """Deterministic assessment when no LLM. Risk mapping is derived from the
        dataset's own ExpectedDecision policy:
          sanctions match                       → REJECT
          PEP | high-risk profile | doc gaps    → EDD
          AML flag WITHOUT high risk            → monitored, still APPROVE
          clean                                 → APPROVE
        Jurisdiction residency is a soft signal (contributes, never decides)."""
        screening = context.get("screening", {})
        profile = context.get("customer", {})
        identity = context.get("identity", {})
        findings: list[dict] = []
        score = 0.1

        risk_cat = str(profile.get("risk_category", "")).lower()
        aml_flag = str(profile.get("aml_flag", "")).strip().lower() in {"1", "true", "yes", "y"}

        if screening.get("is_sanctioned"):
            score = max(score, 0.95)
            findings.append({"finding": "Active sanctions list match", "citation": "screening",
                             "severity": "CRITICAL"})
        if screening.get("is_pep"):
            score = max(score, 0.65)
            findings.append({"finding": "PEP requires enhanced due diligence",
                             "citation": "screening", "severity": "HIGH"})
        if risk_cat == "high":
            score = max(score, 0.65)
            findings.append({"finding": "High-risk customer profile"
                             + (" with AML monitoring flag" if aml_flag else ""),
                             "citation": "profile", "severity": "HIGH"})
        elif aml_flag:
            # AML flag on a medium/low-risk profile → monitor, but the dataset
            # still approves these, so keep it below the EDD threshold.
            score = max(score, 0.45)
        if identity.get("gaps"):
            score = max(score, 0.6)
            findings.append({"finding": "; ".join(identity["gaps"]),
                             "citation": "identity", "severity": "MEDIUM"})
        for hit in screening.get("hits", []):
            if hit["type"] in ("SANCTIONED_JURISDICTION", "HIGH_RISK_JURISDICTION"):
                score = max(score, 0.45)
                findings.append({"finding": hit["detail"], "citation": "jurisdiction",
                                 "severity": "MEDIUM"})

        level = ("CRITICAL" if score >= config.reject_threshold else
                 "HIGH" if score >= config.edd_threshold else
                 "MEDIUM" if score >= 0.4 else "LOW")
        decision = ("REJECT" if score >= config.reject_threshold else
                    "EDD" if score >= config.edd_threshold else "APPROVE")
        top_citation = retrieved_context[0]["id"] if retrieved_context else "none"
        return {
            "risk_level": level,
            "risk_score": round(score, 3),
            "findings": findings,
            "rationale": (f"Rule-based assessment: risk score {score:.2f} from screening, "
                          f"identity, and profile signals. Top regulatory reference: {top_citation}."),
            "recommended_decision": decision,
        }


aml_agent = AMLAgent()
