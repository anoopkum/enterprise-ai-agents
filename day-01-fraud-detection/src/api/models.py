"""Pydantic models for request/response validation."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


class TransactionEvent(BaseModel):
    transaction_id: str = Field(..., min_length=1, max_length=100)
    customer_id: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0, le=1_000_000)
    currency: str = Field(..., min_length=3, max_length=3)
    merchant_id: str = Field(..., min_length=1, max_length=100)
    merchant_name: str = Field(..., min_length=1, max_length=200)
    merchant_category: str = Field(..., min_length=1, max_length=50)
    timestamp: str = Field(...)
    location_country: str = Field(..., min_length=2, max_length=2)
    location_city: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    channel: str = Field(..., description="online|pos|atm|mobile")
    ip_address: Optional[str] = None
    device_fingerprint: Optional[str] = None
    card_number_hash: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()

    @field_validator("location_country")
    @classmethod
    def country_uppercase(cls, v: str) -> str:
        return v.upper()

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid ISO8601 timestamp: {v}") from exc
        return v

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        ipv4 = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
        if not ipv4.match(v):
            raise ValueError(f"Invalid IP address format: {v}")
        return v

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        allowed = {"online", "pos", "atm", "mobile"}
        if v.lower() not in allowed:
            raise ValueError(f"Channel must be one of {allowed}")
        return v.lower()

    class Config:
        json_schema_extra = {
            "example": {
                "transaction_id": "TXN-20240601-001",
                "customer_id": "CUST-12345",
                "amount": 2500.00,
                "currency": "GBP",
                "merchant_id": "MERCH-789",
                "merchant_name": "Electronics Store",
                "merchant_category": "5065",
                "timestamp": "2024-06-01T14:30:00Z",
                "location_country": "GB",
                "location_city": "London",
                "location_lat": 51.5074,
                "location_lon": -0.1278,
                "channel": "online",
                "ip_address": "192.168.1.1",
            }
        }


class FraudDecision(BaseModel):
    transaction_id: str
    fraud_score: int = Field(..., ge=0, le=100)
    risk_level: str = Field(..., description="LOW|MEDIUM|HIGH|CRITICAL")
    decision: str = Field(..., description="APPROVE|REVIEW|BLOCK")
    signals: list[str]
    reasoning: str
    recommended_action: str
    analyzed_at: str
    agent_run_id: Optional[str] = None
    thread_id: Optional[str] = None
