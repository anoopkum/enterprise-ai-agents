"""
Input and output guardrails around the KYC pipeline.

Input:
  - prompt-injection screening on any free-text that reaches the LLM
  - PII redaction for logs / audit (Aadhaar, PAN, passport, cards, emails, phones)

Output:
  - the decision must be one of the allowed verdicts
  - a REJECT/EDD must carry at least one reason (explainability requirement)
  - if the hallucination detector flagged findings, the output is marked
    unsafe_to_auto_action so a human reviews before anything is actioned
"""
import logging
import re

from src.config import config

logger = logging.getLogger(__name__)

# PII patterns present in the dataset's Indian + generic identity documents.
_PII_PATTERNS = {
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "passport": re.compile(r"\b[A-PR-WY][0-9]{7}\b"),
    "card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[-\s]?)?\d{10}\b"),
}

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.I),
    re.compile(r"disregard\s+(?:the\s+)?(?:above|system)", re.I),
    re.compile(r"you\s+are\s+now\s+", re.I),
    re.compile(r"reveal\s+(?:your\s+)?(?:system\s+)?prompt", re.I),
    re.compile(r"</?(?:system|assistant|user)>", re.I),
]

_ALLOWED_DECISIONS = {"APPROVE", "EDD", "REJECT"}


def redact_pii(text: str) -> str:
    if not config.enable_pii_redaction or not text:
        return text
    out = text
    for kind, pattern in _PII_PATTERNS.items():
        out = pattern.sub(f"[REDACTED_{kind.upper()}]", out)
    return out


def screen_input(text: str) -> dict:
    """Flag prompt-injection attempts in free text before it reaches the LLM."""
    hits = [p.pattern for p in _INJECTION_PATTERNS if p.search(text or "")]
    return {"safe": not hits, "injection_patterns": hits}


def validate_output(decision_result: dict, hallucination_report: dict | None) -> dict:
    """Post-decision safety checks. Returns the decision annotated with a verdict."""
    violations: list[str] = []

    decision = decision_result.get("decision")
    if decision not in _ALLOWED_DECISIONS:
        violations.append(f"Decision '{decision}' not in {sorted(_ALLOWED_DECISIONS)}")

    if decision in {"REJECT", "EDD"} and not decision_result.get("reasons"):
        violations.append("Non-approval decision must include at least one reason")

    hallucinated = bool(hallucination_report and hallucination_report.get("any_hallucination"))
    if hallucinated:
        violations.append(
            f"{hallucination_report['flagged_count']} finding(s) not grounded in sources"
        )

    # Auto-action only when there are no violations and nothing was hallucinated.
    safe_to_auto_action = not violations

    return {
        **decision_result,
        "guardrail_violations": violations,
        "unsafe_to_auto_action": not safe_to_auto_action,
        "requires_human_review": hallucinated or decision in {"REJECT", "EDD"},
    }
