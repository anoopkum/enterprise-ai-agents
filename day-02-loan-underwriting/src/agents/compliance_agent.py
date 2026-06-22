"""
Compliance Agent — RAG over a regulatory knowledge base (FCA, GDPR, Basel III)
stored in ChromaDB. Checks the decision against applicable rules and flags concerns.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import chromadb

logger = logging.getLogger(__name__)

# Number of regulatory rules to retrieve per query
TOP_K_RULES = 5


class ComplianceAgent:
    def __init__(self) -> None:
        self._chroma_client: chromadb.ClientAPI | None = None
        self._kb_collection: chromadb.Collection | None = None

    @property
    def kb_collection(self) -> chromadb.Collection:
        if self._kb_collection is None:
            persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "/tmp/chroma/applications")
            self._chroma_client = chromadb.PersistentClient(path=persist_dir)
            collection = self._chroma_client.get_or_create_collection(
                name="regulatory_kb",
                metadata={"hnsw:space": "cosine"},
            )
            if collection.count() == 0:
                self._seed_kb(collection)
            self._kb_collection = collection
        return self._kb_collection

    def _seed_kb(self, collection: chromadb.Collection) -> None:
        kb_path = os.environ.get("REGULATORY_KB_PATH", "data/regulatory_kb.json")
        try:
            with open(kb_path) as f:
                rules = json.load(f)
            collection.upsert(
                ids=[r["rule_id"] for r in rules],
                documents=[r["text"] for r in rules],
                metadatas=[{k: v for k, v in r.items() if k != "text"} for r in rules],
            )
            logger.info("Seeded regulatory KB with %d rules from %s", len(rules), kb_path)
        except FileNotFoundError:
            logger.warning("Regulatory KB file not found at %s — compliance checks will be limited", kb_path)

    def check(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Retrieve relevant regulatory rules for the decision and flag any compliance concerns.
        """
        application_id = context["application_id"]
        decision = context.get("final_decision", "REFER")
        risk_band = context.get("risk_band", "MEDIUM")
        application = context.get("application", {})

        query = self._build_query(decision, risk_band, application)

        try:
            results = self.kb_collection.query(
                query_texts=[query],
                n_results=min(TOP_K_RULES, self.kb_collection.count() or 1),
                include=["documents", "metadatas", "distances"],
            )
            applicable_rules = self._parse_results(results)
        except Exception as exc:
            logger.error("Compliance RAG query failed for %s: %s", application_id, exc)
            applicable_rules = []

        flags = self._evaluate_flags(decision, application, applicable_rules)

        compliance_result = {
            "applicable_rules": applicable_rules,
            "compliance_flags": flags,
            "gdpr_article_22_disclosure_required": decision in {"DECLINE", "REFER"},
            "fca_consumer_duty_met": len([f for f in flags if f["severity"] == "CRITICAL"]) == 0,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Compliance check for %s → %d rules, %d flags, GDPR disclosure=%s",
            application_id,
            len(applicable_rules),
            len(flags),
            compliance_result["gdpr_article_22_disclosure_required"],
        )

        return {**context, "compliance": compliance_result}

    def _build_query(self, decision: str, risk_band: str, application: dict) -> str:
        dti = application.get("dti_ratio", 0)
        return (
            f"loan {decision.lower()} decision {risk_band.lower()} risk "
            f"creditworthiness assessment automated decision GDPR FCA Basel "
            f"debt-to-income {dti:.0%} consumer credit"
        )

    def _parse_results(self, results: Any) -> list[dict]:
        rules = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            rules.append({
                "rule_id": meta.get("rule_id", "unknown"),
                "framework": meta.get("framework", "unknown"),
                "reference": meta.get("reference", ""),
                "description": meta.get("description", doc[:120]),
                "relevance_score": round(1 - dist, 4),
            })
        return rules

    def _evaluate_flags(self, decision: str, application: dict, rules: list[dict]) -> list[dict]:
        flags = []

        # GDPR Article 22 — right to human review for automated decisions affecting credit
        if decision in {"DECLINE", "REFER"}:
            flags.append({
                "rule_ref": "GDPR Art. 22",
                "severity": "HIGH",
                "description": "Automated credit decision — applicant has right to request human review.",
                "required_action": "Include GDPR Art. 22 disclosure in customer communication.",
            })

        dti = application.get("dti_ratio", 0)
        if dti > 0.55:
            flags.append({
                "rule_ref": "FCA CONC 5.2A.4",
                "severity": "HIGH",
                "description": f"DTI ratio {dti:.0%} significantly exceeds affordability guideline of 45%.",
                "required_action": "Affordability assessment must be documented before any approval.",
            })

        credit_score = application.get("credit_score", 999)
        if decision == "APPROVE" and credit_score < 550:
            flags.append({
                "rule_ref": "FCA Consumer Duty — PRIN 2A.3",
                "severity": "CRITICAL",
                "description": f"Approving applicant with credit score {credit_score} may not deliver good outcomes.",
                "required_action": "Escalate to senior underwriter for sign-off.",
            })

        loan_amount = application.get("loan_amount", 0)
        annual_income = application.get("annual_income", 1)
        ltv_income = loan_amount / annual_income if annual_income > 0 else 0
        if ltv_income > 5:
            flags.append({
                "rule_ref": "Basel III — LTI guidance",
                "severity": "MEDIUM",
                "description": f"Loan-to-income ratio of {ltv_income:.1f}x exceeds Basel III stress-test guidance of 4.5x.",
                "required_action": "Document basis for high LTI lending in credit file.",
            })

        return flags
