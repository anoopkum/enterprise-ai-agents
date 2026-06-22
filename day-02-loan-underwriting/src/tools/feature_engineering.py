"""Tool: Feature engineering — computes DTI ratio, credit utilisation, payment history score."""
from typing import Any


def engineer_features(normalised: dict[str, Any]) -> dict[str, Any]:
    """
    Derive financial risk features from normalised application fields.
    These features directly feed the ML model and SHAP explanations.
    """
    annual_income = normalised["annual_income"]
    existing_debt = normalised["existing_debt"]
    loan_amount = normalised["loan_amount"]
    loan_term_months = normalised.get("loan_term_months", 60)
    interest_rate = normalised.get("interest_rate", 0.05)
    credit_limit = normalised.get("credit_limit", 0.0)
    current_balance = normalised.get("current_balance", 0.0)
    payment_history = normalised["payment_history"]

    # Monthly income for affordability calculations
    monthly_income = annual_income / 12 if annual_income > 0 else 1.0

    # Estimated monthly instalment using amortisation formula
    if interest_rate > 0 and loan_term_months > 0:
        monthly_rate = interest_rate / 12
        monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate) ** loan_term_months) / (
            (1 + monthly_rate) ** loan_term_months - 1
        )
    else:
        monthly_payment = loan_amount / max(loan_term_months, 1)

    # DTI = (existing monthly debt obligations + new instalment) / monthly income
    # Existing debt approximated as 3% of outstanding balance per month
    existing_monthly_debt = existing_debt * 0.03
    total_monthly_obligations = existing_monthly_debt + monthly_payment
    dti_ratio = total_monthly_obligations / monthly_income if monthly_income > 0 else 1.0

    # Credit utilisation = current balance / credit limit
    credit_utilisation_rate = current_balance / credit_limit if credit_limit > 0 else 0.0
    credit_utilisation_rate = min(credit_utilisation_rate, 1.0)

    # Payment history score: 100 for all ON_TIME, −20 per LATE, −40 per MISSED
    score = 100
    for status in payment_history:
        if status == "LATE":
            score -= 20
        elif status == "MISSED":
            score -= 40
    payment_history_score = max(score, 0)

    missed_payments = sum(1 for p in payment_history if p == "MISSED")
    late_payments = sum(1 for p in payment_history if p == "LATE")

    # Loan-to-income ratio — separate from DTI, used by Basel III stress test
    loan_to_income_ratio = loan_amount / annual_income if annual_income > 0 else 99.0

    enriched = {
        **normalised,
        "monthly_income": round(monthly_income, 2),
        "estimated_monthly_payment": round(monthly_payment, 2),
        "dti_ratio": round(min(dti_ratio, 5.0), 4),
        "credit_utilisation_rate": round(credit_utilisation_rate, 4),
        "payment_history_score": payment_history_score,
        "missed_payments_count": missed_payments,
        "late_payments_count": late_payments,
        "loan_to_income_ratio": round(loan_to_income_ratio, 4),
        "employment_stability_score": _employment_score(normalised["employment_status"]),
    }

    return enriched


def _employment_score(status: str) -> int:
    """Higher score = more stable employment = lower credit risk."""
    mapping = {
        "employed": 100,
        "self_employed": 70,
        "part_time": 50,
        "retired": 80,
        "unemployed": 10,
    }
    return mapping.get(status, 50)
