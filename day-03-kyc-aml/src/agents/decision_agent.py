"""
Decision Agent — fuses the upstream agents into a final KYC/AML disposition.

Combines identity confidence, screening verdict, and the AML risk assessment into
one of APPROVE / EDD / REJECT, and generates a Suspicious Activity Report (SAR)
draft when the case warrants regulatory filing.

Decision policy (most-conservative wins):
  screening BLOCK or aml risk ≥ reject_threshold           → REJECT
  screening EDD, aml risk ≥ edd_threshold, or identity gaps → EDD
  otherwise                                                 → APPROVE
A SAR draft is produced for any REJECT and for any case with a sanctions/PEP hit.
"""
import logging
from typing import Any

from src.config import config

logger = logging.getLogger(__name__)


class DecisionAgent:
    def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        identity = context.get("identity", {})
        screening = context.get("screening", {})
        aml = context.get("aml", {})

        risk_score = float(aml.get("risk_score", 0.0) or 0.0)
        screening_verdict = screening.get("verdict", "CLEAR")
        identity_conf = float(identity.get("identity_confidence", 0.0) or 0.0)
        reasons: list[str] = []

        if screening_verdict == "BLOCK" or risk_score >= config.reject_threshold:
            decision = "REJECT"
            if screening_verdict == "BLOCK":
                reasons.append("Screening returned a blocking (sanctions) hit")
            if risk_score >= config.reject_threshold:
                reasons.append(f"AML risk score {risk_score:.2f} ≥ reject threshold {config.reject_threshold}")
        elif (screening_verdict == "EDD" or risk_score >= config.edd_threshold
              or identity.get("gaps")):
            decision = "EDD"
            if screening_verdict == "EDD":
                reasons.append("Screening flagged PEP / high-risk jurisdiction")
            if risk_score >= config.edd_threshold:
                reasons.append(f"AML risk score {risk_score:.2f} ≥ EDD threshold {config.edd_threshold}")
            if identity.get("gaps"):
                reasons.append(f"{len(identity['gaps'])} unresolved identity gap(s)")
        else:
            decision = "APPROVE"
            reasons.append(f"Low AML risk ({risk_score:.2f}), identity confidence {identity_conf:.2f}")

        sar = self._maybe_sar(context, decision)

        result = {
            "decision": decision,
            "risk_score": round(risk_score, 3),
            "risk_level": aml.get("risk_level", "UNKNOWN"),
            "reasons": reasons,
            "identity_confidence": round(identity_conf, 3),
            "screening_verdict": screening_verdict,
            "sar": sar,
            "citations": [f.get("citation") for f in aml.get("findings", []) if f.get("citation")],
        }
        logger.info("Decision: %s (risk=%.2f, SAR=%s)", decision, risk_score, bool(sar))
        return {**context, "decision": result}

    @staticmethod
    def _maybe_sar(context: dict, decision: str) -> dict | None:
        screening = context.get("screening", {})
        profile = context.get("customer", {})
        needs_sar = (
            decision == "REJECT"
            or screening.get("is_sanctioned")
            or screening.get("is_pep")
        )
        if not needs_sar:
            return None
        return {
            "subject": profile.get("full_name") or profile.get("FullName", "Unknown"),
            "customer_id": (profile.get("customer_id") or profile.get("CustomerID", "")),
            "reason": "; ".join(h["detail"] for h in screening.get("hits", [])) or "High AML risk",
            "risk_indicators": [h["type"] for h in screening.get("hits", [])],
            "recommended_action": "File SAR with FIU and freeze onboarding pending review",
        }


decision_agent = DecisionAgent()
