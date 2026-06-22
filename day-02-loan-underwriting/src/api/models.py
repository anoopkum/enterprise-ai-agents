"""Pydantic models for loan application request/response validation."""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


VALID_EMPLOYMENT_STATUSES = {"employed", "self_employed", "part_time", "unemployed", "retired"}
VALID_LOAN_PURPOSES = {
    "home_improvement", "debt_consolidation", "vehicle",
    "education", "business", "personal", "medical", "other",
}
VALID_PAYMENT_STATUSES = {"ON_TIME", "LATE", "MISSED"}


class LoanApplication(BaseModel):
    application_id: Optional[str] = Field(None, description="Auto-generated if omitted")
    applicant_name: str = Field(..., min_length=1, max_length=200)
    age: int = Field(..., ge=18, le=100)
    annual_income: float = Field(..., ge=0)
    employment_status: str = Field(..., description="employed|self_employed|part_time|unemployed|retired")
    credit_score: int = Field(..., ge=300, le=850)
    existing_debt: float = Field(..., ge=0)
    loan_amount: float = Field(..., gt=0)
    loan_purpose: str = Field(..., description="home_improvement|debt_consolidation|vehicle|education|business|personal|medical|other")
    payment_history: list[str] = Field(..., min_length=1, max_length=24, description="Last N months: ON_TIME|LATE|MISSED")
    loan_term_months: int = Field(60, ge=6, le=360)
    interest_rate: float = Field(0.05, ge=0.0, le=0.5, description="Annual rate as decimal (e.g. 0.065 = 6.5%)")
    credit_limit: float = Field(0.0, ge=0)
    current_balance: float = Field(0.0, ge=0)

    @field_validator("employment_status")
    @classmethod
    def validate_employment(cls, v: str) -> str:
        normalised = v.lower().replace(" ", "_")
        if normalised not in VALID_EMPLOYMENT_STATUSES:
            raise ValueError(f"employment_status must be one of {VALID_EMPLOYMENT_STATUSES}")
        return normalised

    @field_validator("loan_purpose")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        normalised = v.lower().replace(" ", "_")
        return normalised if normalised in VALID_LOAN_PURPOSES else "other"

    @field_validator("payment_history")
    @classmethod
    def validate_payment_history(cls, v: list[str]) -> list[str]:
        invalid = [e for e in v if e not in VALID_PAYMENT_STATUSES]
        if invalid:
            raise ValueError(f"payment_history contains invalid entries: {invalid}. Must be ON_TIME|LATE|MISSED")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "applicant_name": "Sarah Thompson",
                "age": 34,
                "annual_income": 52000,
                "employment_status": "employed",
                "credit_score": 680,
                "existing_debt": 8500,
                "loan_amount": 15000,
                "loan_purpose": "home_improvement",
                "payment_history": ["ON_TIME", "ON_TIME", "ON_TIME", "LATE", "ON_TIME", "ON_TIME"],
                "loan_term_months": 60,
                "interest_rate": 0.065,
                "credit_limit": 10000,
                "current_balance": 3200,
            }
        }


class ComplianceFlag(BaseModel):
    rule_ref: str
    severity: str = Field(..., description="LOW|MEDIUM|HIGH|CRITICAL")
    description: str
    required_action: str


class ExplanationDetail(BaseModel):
    decision: str
    plain_english_explanation: str
    primary_risk_factors: list[str]
    mitigating_factors: list[str]
    customer_message: str
    analyst_notes: str
    explained_at: Optional[str] = None
    agent_run_id: Optional[str] = None


class LoanDecision(BaseModel):
    application_id: str
    final_decision: str = Field(..., description="APPROVE|DECLINE|REFER")
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_band: str = Field(..., description="LOW|MEDIUM|HIGH|CRITICAL")
    explanation: ExplanationDetail
    compliance_flags: list[ComplianceFlag]
    gdpr_disclosure_required: bool
    fca_consumer_duty_met: bool
    mlflow_run_id: Optional[str] = None
    audit_run_id: Optional[str] = None
    audited_at: str
