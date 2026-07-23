"""
Lightweight document-type classifier. Uses filename + extracted text keywords to
label a document (passport, aadhaar, voter_id, bank_statement, regulation, ...).
This label drives which KYC checks apply and which graph node type is created.
"""
import re

# Ordered: first match wins. Patterns matched against lowercased filename + text head.
_RULES: list[tuple[str, list[str]]] = [
    ("aadhaar", [r"\baadhaar\b", r"\baadhar\b", r"\buidai\b", r"\b\d{4}\s?\d{4}\s?\d{4}\b"]),
    ("passport", [r"\bpassport\b", r"republic of", r"\bp<"]),
    ("voter_id", [r"voter\s?id", r"voter card", r"election commission", r"epic no"]),
    ("birth_certificate", [r"birth certificate", r"date of birth", r"registration of birth"]),
    ("bank_statement", [r"transaction history", r"account statement", r"opening balance", r"withdrawal.*deposit"]),
    ("pan_card", [r"\bpan\b", r"permanent account number", r"income tax department"]),
    ("driving_licence", [r"driving licence", r"driving license", r"\bdl no\b"]),
    ("utility_bill", [r"utility bill", r"electricity bill", r"gas bill"]),
    ("school_form", [r"udise", r"student information", r"school report"]),
    ("regulation", [r"\baml\b", r"due diligence", r"\bkyc\b", r"beneficial ownership", r"sanctions"]),
]


def classify(filename: str, text: str = "") -> str:
    """Return a doc_type label. Filename hints are weighted first, then content."""
    haystack = f"{filename}\n{text[:2000]}".lower()
    for label, patterns in _RULES:
        for pat in patterns:
            if re.search(pat, haystack):
                return label
    return "unknown"
