"""Unit tests for Pydantic request/response models."""
import pytest
from pydantic import ValidationError

from src.api.models import TransactionEvent, FraudDecision


VALID_TRANSACTION = {
    "transaction_id": "TXN-001",
    "customer_id": "CUST-001",
    "amount": 150.00,
    "currency": "USD",
    "merchant_id": "MERCH-001",
    "merchant_name": "Coffee Shop",
    "merchant_category": "5812",
    "timestamp": "2024-06-01T10:00:00Z",
    "location_country": "US",
    "channel": "pos",
}


class TestTransactionEvent:

    def test_valid_transaction(self):
        txn = TransactionEvent(**VALID_TRANSACTION)
        assert txn.currency == "USD"
        assert txn.location_country == "US"

    def test_currency_uppercased(self):
        txn = TransactionEvent(**{**VALID_TRANSACTION, "currency": "gbp"})
        assert txn.currency == "GBP"

    def test_country_uppercased(self):
        txn = TransactionEvent(**{**VALID_TRANSACTION, "location_country": "gb"})
        assert txn.location_country == "GB"

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            TransactionEvent(**{**VALID_TRANSACTION, "amount": -10.0})
        assert "greater than 0" in str(exc_info.value)

    def test_zero_amount_rejected(self):
        with pytest.raises(ValidationError):
            TransactionEvent(**{**VALID_TRANSACTION, "amount": 0})

    def test_amount_over_limit_rejected(self):
        with pytest.raises(ValidationError):
            TransactionEvent(**{**VALID_TRANSACTION, "amount": 2_000_000})

    def test_invalid_timestamp_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            TransactionEvent(**{**VALID_TRANSACTION, "timestamp": "not-a-date"})
        assert "ISO8601" in str(exc_info.value)

    def test_invalid_channel_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            TransactionEvent(**{**VALID_TRANSACTION, "channel": "carrier_pigeon"})
        assert "Channel must be one of" in str(exc_info.value)

    def test_invalid_ip_rejected(self):
        with pytest.raises(ValidationError):
            TransactionEvent(**{**VALID_TRANSACTION, "ip_address": "not-an-ip"})

    def test_valid_ip_accepted(self):
        txn = TransactionEvent(**{**VALID_TRANSACTION, "ip_address": "10.0.0.1"})
        assert txn.ip_address == "10.0.0.1"

    def test_optional_fields_default_none(self):
        txn = TransactionEvent(**VALID_TRANSACTION)
        assert txn.location_lat is None
        assert txn.device_fingerprint is None


class TestFraudDecision:

    def test_valid_decision(self):
        d = FraudDecision(
            transaction_id="TXN-001",
            fraud_score=75,
            risk_level="HIGH",
            decision="REVIEW",
            signals=["AMOUNT_SPIKE"],
            reasoning="High amount spike detected.",
            recommended_action="Escalate to analyst.",
            analyzed_at="2024-06-01T10:00:00Z",
        )
        assert d.fraud_score == 75

    def test_score_out_of_range(self):
        with pytest.raises(ValidationError):
            FraudDecision(
                transaction_id="TXN-001",
                fraud_score=150,
                risk_level="HIGH",
                decision="REVIEW",
                signals=[],
                reasoning="test",
                recommended_action="test",
                analyzed_at="2024-06-01T10:00:00Z",
            )
