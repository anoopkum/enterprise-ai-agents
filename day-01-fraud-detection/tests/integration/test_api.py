"""Integration tests for the FastAPI fraud detection endpoint."""
import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

VALID_PAYLOAD = {
    "transaction_id": "TXN-INT-001",
    "customer_id": "CUST-INT-001",
    "amount": 250.00,
    "currency": "GBP",
    "merchant_id": "MERCH-INT-001",
    "merchant_name": "Integration Test Merchant",
    "merchant_category": "5411",
    "timestamp": "2024-06-01T12:00:00Z",
    "location_country": "GB",
    "location_city": "London",
    "location_lat": 51.5074,
    "location_lon": -0.1278,
    "channel": "online",
    "ip_address": "10.0.0.1",
}

MOCK_DECISION = {
    "transaction_id": "TXN-INT-001",
    "fraud_score": 15,
    "risk_level": "LOW",
    "decision": "APPROVE",
    "signals": [],
    "reasoning": "No fraud signals detected.",
    "recommended_action": "Proceed with transaction.",
    "analyzed_at": "2024-06-01T12:00:05Z",
    "agent_run_id": "run-int-001",
    "thread_id": "thread-int-001",
}


@pytest.fixture
def test_client():
    with patch("src.api.main.FraudDetectionAgent") as mock_agent_cls:
        mock_agent = MagicMock()
        mock_agent.analyze_transaction.return_value = MOCK_DECISION
        mock_agent_cls.return_value = mock_agent

        from src.api.main import app
        with TestClient(app) as client:
            yield client, mock_agent


class TestAnalyzeEndpoint:

    def test_health_check(self, test_client):
        client, _ = test_client
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_valid_transaction_returns_decision(self, test_client):
        client, mock_agent = test_client
        response = client.post("/analyze", json=VALID_PAYLOAD)
        assert response.status_code == 200
        data = response.json()
        assert data["transaction_id"] == "TXN-INT-001"
        assert data["decision"] == "APPROVE"
        assert "fraud_score" in data

    def test_agent_called_with_correct_data(self, test_client):
        client, mock_agent = test_client
        client.post("/analyze", json=VALID_PAYLOAD)
        mock_agent.analyze_transaction.assert_called_once()
        call_args = mock_agent.analyze_transaction.call_args[0][0]
        assert call_args["transaction_id"] == "TXN-INT-001"

    def test_invalid_payload_returns_422(self, test_client):
        client, _ = test_client
        bad_payload = {**VALID_PAYLOAD, "amount": -100}
        response = client.post("/analyze", json=bad_payload)
        assert response.status_code == 422

    def test_missing_required_field_returns_422(self, test_client):
        client, _ = test_client
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "customer_id"}
        response = client.post("/analyze", json=payload)
        assert response.status_code == 422

    def test_invalid_channel_returns_422(self, test_client):
        client, _ = test_client
        response = client.post("/analyze", json={**VALID_PAYLOAD, "channel": "invalid"})
        assert response.status_code == 422

    def test_block_decision_response(self, test_client):
        client, mock_agent = test_client
        block_decision = {**MOCK_DECISION, "fraud_score": 90, "decision": "BLOCK", "risk_level": "CRITICAL"}
        mock_agent.analyze_transaction.return_value = block_decision
        response = client.post("/analyze", json=VALID_PAYLOAD)
        assert response.status_code == 200
        assert response.json()["decision"] == "BLOCK"
