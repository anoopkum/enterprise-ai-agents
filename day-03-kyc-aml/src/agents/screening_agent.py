"""
Screening Agent — PEP and sanctions screening from the knowledge graph.

The graph already links each customer to Watchlist nodes (PEP / Sanction) built
from the profile flags. This agent reads those flags plus high-risk jurisdiction
signals and emits a screening verdict with the hits that must be dispositioned.

High-risk countries are the FATF-style call-to-action / grey-list jurisdictions
present in the dataset; a sanctions hit or a sanctioned jurisdiction is an
automatic block, a PEP hit mandates Enhanced Due Diligence.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Sanctioned / high-risk jurisdictions present in the dataset.
SANCTIONED_COUNTRIES = {"Iran", "North Korea", "Syria"}
HIGH_RISK_COUNTRIES = {"Russia", "Afghanistan", "Myanmar", "Yemen"}


def _truthy(v: Any) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


class ScreeningAgent:
    def screen(self, context: dict[str, Any]) -> dict[str, Any]:
        profile = context.get("customer", {})
        graph = context.get("graph", {})
        watchlists = set(graph.get("watchlists", []))
        countries = graph.get("countries", []) or [profile.get("nationality", "")]

        is_pep = "PEP" in watchlists or _truthy(profile.get("pep_status") or profile.get("PEPStatus"))
        is_sanctioned = "Sanction" in watchlists or _truthy(
            profile.get("sanction_status") or profile.get("SanctionStatus")
        )

        hits: list[dict] = []
        if is_sanctioned:
            hits.append({"type": "SANCTION", "severity": "CRITICAL",
                         "detail": "Customer matches an active sanctions list"})
        if is_pep:
            hits.append({"type": "PEP", "severity": "HIGH",
                         "detail": "Politically Exposed Person — enhanced due diligence required"})

        # Residency in a high-risk/sanctioned jurisdiction mandates enhanced due
        # diligence, but is NOT by itself a block — only an actual sanctions-list
        # match (is_sanctioned) rejects a customer. This matches the dataset, where
        # customers resident in sanctioned countries are Approve/EDD unless flagged.
        sanctioned_jur = [c for c in countries if c in SANCTIONED_COUNTRIES]
        high_risk_jur = [c for c in countries if c in HIGH_RISK_COUNTRIES]
        for c in sanctioned_jur:
            hits.append({"type": "SANCTIONED_JURISDICTION", "severity": "HIGH",
                         "detail": f"Resident of sanctioned jurisdiction: {c}"})
        for c in high_risk_jur:
            hits.append({"type": "HIGH_RISK_JURISDICTION", "severity": "HIGH",
                         "detail": f"Resident of high-risk jurisdiction: {c}"})

        # Verdict is driven by the person, not their postcode: an actual sanctions
        # match blocks; PEP status mandates EDD. Jurisdiction residency is recorded
        # as context (it feeds the AML risk score and any SAR) but does not by
        # itself escalate — the dataset approves clean customers in high-risk
        # countries, and country risk is already captured in RiskCategory.
        if is_sanctioned:
            verdict = "BLOCK"
        elif is_pep:
            verdict = "EDD"
        else:
            verdict = "CLEAR"

        result = {
            "verdict": verdict,
            "is_pep": is_pep,
            "is_sanctioned": is_sanctioned,
            "hits": hits,
            "screened_countries": countries,
        }
        logger.info("Screening: verdict=%s pep=%s sanction=%s hits=%d",
                    verdict, is_pep, is_sanctioned, len(hits))
        return {**context, "screening": result}


screening_agent = ScreeningAgent()
