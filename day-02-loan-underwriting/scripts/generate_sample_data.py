"""
Generate 100 realistic synthetic loan applications matching the UCI Credit Card dataset schema.
Saves to data/sample_applications.json.

UCI dataset: https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients
Original features: LIMIT_BAL, SEX, EDUCATION, MARRIAGE, AGE, PAY_0–PAY_6, BILL_AMT1–6, PAY_AMT1–6
We map these to our enriched loan application schema.
"""
import json
import random
import uuid
from pathlib import Path

random.seed(42)

FIRST_NAMES = [
    "James", "Sarah", "Mohammed", "Emma", "David", "Priya", "Thomas", "Amelia",
    "Daniel", "Olivia", "Ahmed", "Charlotte", "Ryan", "Jessica", "Samuel",
    "Sophia", "Nathan", "Isabella", "Oliver", "Mia", "Lucas", "Grace",
    "Ethan", "Lily", "Noah", "Ava", "Liam", "Emily", "Mason", "Ella",
    "Aisha", "Kwame", "Yuki", "Fatima", "Carlos", "Ana", "Ivan", "Ingrid",
    "Ravi", "Mei", "Patrick", "Niamh", "Sven", "Astrid", "Chen", "Lin",
    "Adebayo", "Chioma", "Andrei", "Natalia",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Thompson", "Anderson", "Taylor",
    "Thomas", "Hernandez", "Moore", "Martin", "Jackson", "Lee", "Perez",
    "White", "Harris", "Sanchez", "Clark", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen",
    "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall",
    "Rivera", "Campbell", "Mitchell", "Carter", "Roberts", "Patel",
    "Ahmed", "Chen", "Kim",
]

LOAN_PURPOSES = [
    "home_improvement", "debt_consolidation", "vehicle",
    "education", "business", "personal", "medical", "other",
]
PURPOSE_WEIGHTS = [0.20, 0.25, 0.15, 0.10, 0.10, 0.12, 0.05, 0.03]

EMPLOYMENT_STATUSES = ["employed", "self_employed", "part_time", "unemployed", "retired"]
EMPLOYMENT_WEIGHTS = [0.62, 0.15, 0.09, 0.06, 0.08]


def _payment_history(profile: str) -> list[str]:
    if profile == "excellent":
        return ["ON_TIME"] * 6
    elif profile == "good":
        lates = random.randint(0, 1)
        history = ["ON_TIME"] * 6
        for i in random.sample(range(6), lates):
            history[i] = "LATE"
        return history
    elif profile == "fair":
        history = []
        for _ in range(6):
            history.append(random.choices(["ON_TIME", "LATE", "MISSED"], weights=[0.6, 0.3, 0.1])[0])
        return history
    else:
        history = []
        for _ in range(6):
            history.append(random.choices(["ON_TIME", "LATE", "MISSED"], weights=[0.3, 0.35, 0.35])[0])
        return history


def _generate_application(i: int) -> dict:
    employment = random.choices(EMPLOYMENT_STATUSES, EMPLOYMENT_WEIGHTS)[0]

    if employment == "employed":
        annual_income = random.randint(24000, 120000)
    elif employment == "self_employed":
        annual_income = random.randint(20000, 95000)
    elif employment == "part_time":
        annual_income = random.randint(10000, 32000)
    elif employment == "unemployed":
        annual_income = random.randint(8000, 18000)
    else:
        annual_income = random.randint(18000, 55000)

    age = random.randint(21, 68)

    credit_profile = random.choices(
        ["excellent", "good", "fair", "poor"],
        weights=[0.25, 0.35, 0.25, 0.15],
    )[0]

    if credit_profile == "excellent":
        credit_score = random.randint(740, 850)
        existing_debt_ratio = random.uniform(0.02, 0.15)
        dti_target = random.uniform(0.08, 0.30)
    elif credit_profile == "good":
        credit_score = random.randint(650, 739)
        existing_debt_ratio = random.uniform(0.10, 0.30)
        dti_target = random.uniform(0.20, 0.42)
    elif credit_profile == "fair":
        credit_score = random.randint(550, 649)
        existing_debt_ratio = random.uniform(0.25, 0.55)
        dti_target = random.uniform(0.35, 0.58)
    else:
        credit_score = random.randint(300, 549)
        existing_debt_ratio = random.uniform(0.40, 0.90)
        dti_target = random.uniform(0.50, 0.85)

    existing_debt = round(annual_income * existing_debt_ratio, 2)

    # Loan amount chosen so monthly payment creates the target DTI
    monthly_income = annual_income / 12
    existing_monthly_service = existing_debt * 0.03
    target_new_payment = max(0, monthly_income * dti_target - existing_monthly_service)
    loan_term = random.choice([24, 36, 48, 60, 72, 84])
    interest_rate = round(random.uniform(0.03, 0.25), 3)
    monthly_rate = interest_rate / 12
    if monthly_rate > 0 and loan_term > 0:
        loan_amount = target_new_payment * ((1 + monthly_rate) ** loan_term - 1) / (monthly_rate * (1 + monthly_rate) ** loan_term)
    else:
        loan_amount = target_new_payment * loan_term
    loan_amount = max(1000, min(round(loan_amount, -2), 150000))

    credit_limit = round(annual_income * random.uniform(0.05, 0.4), -2)
    utilisation = random.uniform(0.01, 0.99) if credit_profile != "excellent" else random.uniform(0.01, 0.25)
    current_balance = round(credit_limit * utilisation, 2)

    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)

    return {
        "application_id": f"APP-SYNTH-{i:04d}",
        "applicant_name": f"{first} {last}",
        "age": age,
        "annual_income": annual_income,
        "employment_status": employment,
        "credit_score": credit_score,
        "existing_debt": existing_debt,
        "loan_amount": loan_amount,
        "loan_purpose": random.choices(LOAN_PURPOSES, PURPOSE_WEIGHTS)[0],
        "payment_history": _payment_history(credit_profile),
        "loan_term_months": loan_term,
        "interest_rate": interest_rate,
        "credit_limit": credit_limit,
        "current_balance": current_balance,
    }


if __name__ == "__main__":
    output_path = Path("data/sample_applications.json")
    output_path.parent.mkdir(exist_ok=True)

    applications = [_generate_application(i) for i in range(1, 101)]
    output_path.write_text(json.dumps(applications, indent=2))
    print(f"Generated {len(applications)} synthetic applications → {output_path}")
