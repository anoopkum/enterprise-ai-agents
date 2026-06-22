"""Tool: Application field validation and normalisation."""
from typing import Any


REQUIRED_FIELDS = {
    "applicant_name",
    "age",
    "annual_income",
    "employment_status",
    "credit_score",
    "existing_debt",
    "loan_amount",
    "loan_purpose",
    "payment_history",
}

VALID_EMPLOYMENT_STATUSES = {"employed", "self_employed", "part_time", "unemployed", "retired"}
VALID_LOAN_PURPOSES = {"home_improvement", "debt_consolidation", "vehicle", "education", "business", "personal", "medical", "other"}
VALID_PAYMENT_STATUSES = {"ON_TIME", "LATE", "MISSED"}


def validate_and_normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Validate required fields, apply range constraints, and normalise string fields.
    Raises ValueError with a descriptive message on any validation failure.
    """
    missing = REQUIRED_FIELDS - set(raw.keys())
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")

    age = int(raw["age"])
    if not (18 <= age <= 100):
        raise ValueError(f"Age must be between 18 and 100, got {age}")

    annual_income = float(raw["annual_income"])
    if annual_income < 0:
        raise ValueError(f"annual_income must be non-negative, got {annual_income}")

    credit_score = int(raw["credit_score"])
    if not (300 <= credit_score <= 850):
        raise ValueError(f"credit_score must be 300–850, got {credit_score}")

    existing_debt = float(raw["existing_debt"])
    if existing_debt < 0:
        raise ValueError(f"existing_debt must be non-negative, got {existing_debt}")

    loan_amount = float(raw["loan_amount"])
    if loan_amount <= 0:
        raise ValueError(f"loan_amount must be positive, got {loan_amount}")

    employment_status = raw["employment_status"].lower().replace(" ", "_")
    if employment_status not in VALID_EMPLOYMENT_STATUSES:
        raise ValueError(f"employment_status must be one of {VALID_EMPLOYMENT_STATUSES}, got '{employment_status}'")

    loan_purpose = raw["loan_purpose"].lower().replace(" ", "_")
    if loan_purpose not in VALID_LOAN_PURPOSES:
        loan_purpose = "other"

    payment_history = raw["payment_history"]
    if not isinstance(payment_history, list) or len(payment_history) == 0:
        raise ValueError("payment_history must be a non-empty list")
    for entry in payment_history:
        if entry not in VALID_PAYMENT_STATUSES:
            raise ValueError(f"payment_history entries must be one of {VALID_PAYMENT_STATUSES}, got '{entry}'")

    normalised = {
        "applicant_name": str(raw["applicant_name"]).strip(),
        "age": age,
        "annual_income": annual_income,
        "employment_status": employment_status,
        "credit_score": credit_score,
        "existing_debt": existing_debt,
        "loan_amount": loan_amount,
        "loan_purpose": loan_purpose,
        "payment_history": payment_history,
        # Pass through optional fields
        "loan_term_months": int(raw.get("loan_term_months", 60)),
        "interest_rate": float(raw.get("interest_rate", 0.0)),
        "credit_limit": float(raw.get("credit_limit", 0.0)),
        "current_balance": float(raw.get("current_balance", 0.0)),
    }

    return normalised
