"""Pydantic models for the KYC/AML API request/response validation."""
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ScreenRequest(BaseModel):
    """Screen an existing customer (already in the knowledge graph) by ID, or pass
    an inline profile for an ad-hoc customer not yet loaded."""
    model_config = ConfigDict(json_schema_extra={"example": {"customer_id": "C000003"}})

    customer_id: Optional[str] = Field(None, description="CustomerID in the graph, e.g. C000003")
    customer: Optional[dict] = Field(None, description="Inline profile if not in the graph")


class SARModel(BaseModel):
    subject: str
    customer_id: str
    reason: str
    risk_indicators: list[str] = []
    recommended_action: str


class KYCDecision(BaseModel):
    customer_id: Optional[str]
    decision: str = Field(..., description="APPROVE | EDD | REJECT")
    risk_level: str
    risk_score: float
    reasons: list[str]
    identity_confidence: float
    screening_verdict: str
    citations: list[str] = []
    requires_human_review: bool
    unsafe_to_auto_action: bool
    guardrail_violations: list[str] = []
    hallucination_flagged: int = 0
    sar: Optional[SARModel] = None
    assessment_source: str = Field("fallback", description="llm | fallback")
