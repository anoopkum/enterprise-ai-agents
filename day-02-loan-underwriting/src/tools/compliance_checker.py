"""Tool: Standalone compliance rule lookup — used for direct rule retrieval outside the agent."""
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def load_regulatory_kb(kb_path: str | None = None) -> list[dict]:
    """Load the regulatory knowledge base from disk."""
    resolved = kb_path or os.environ.get("REGULATORY_KB_PATH", "data/regulatory_kb.json")
    assert resolved is not None
    with open(resolved) as f:
        return json.load(f)


def check_rule_applicability(decision: str, application: dict[str, Any], rules: list[dict]) -> list[dict]:
    """
    Filter the rule list to those applicable for a given decision and application profile.
    Returns rules tagged with their applicability reason.
    """
    applicable = []
    decision_upper = decision.upper()

    for rule in rules:
        triggers = rule.get("triggers", [])
        applies = False
        reason = ""

        if "automated_decision" in triggers and decision_upper in {"APPROVE", "DECLINE", "REFER"}:
            applies = True
            reason = "automated credit decision"

        if "decline" in triggers and decision_upper == "DECLINE":
            applies = True
            reason = "decline decision requires disclosure"

        if "high_dti" in triggers and application.get("dti_ratio", 0) > 0.45:
            applies = True
            reason = f"DTI {application['dti_ratio']:.0%} exceeds affordability threshold"

        if "high_lti" in triggers and application.get("loan_to_income_ratio", 0) > 4.5:
            applies = True
            reason = f"LTI {application['loan_to_income_ratio']:.1f}x exceeds Basel III guidance"

        if applies:
            applicable.append({**rule, "applicability_reason": reason})

    return applicable
