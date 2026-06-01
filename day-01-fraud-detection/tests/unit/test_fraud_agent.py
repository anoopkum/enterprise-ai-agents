"""Unit tests for FraudDetectionAgent — mocks AI Foundry calls."""
import json
from unittest.mock import MagicMock, patch
import pytest

from src.agent.fraud_agent import FraudDetectionAgent


SAMPLE_TRANSACTION = {
    "transaction_id": "TXN-TEST-001",
    "customer_id": "CUST-12345",
    "amount": 5000.00,
    "currency": "GBP",
    "merchant_id": "MERCH-999",
    "merchant_name": "Test Merchant",
    "merchant_category": "5065",
    "timestamp": "2024-06-01T14:30:00Z",
    "location_country": "GB",
    "location_city": "London",
    "location_lat": 51.5074,
    "location_lon": -0.1278,
    "channel": "online",
    "ip_address": "192.168.1.1",
    "device_fingerprint": "abc123",
    "card_number_hash": "sha256hash",
}

MOCK_DECISION = {
    "transaction_id": "TXN-TEST-001",
    "fraud_score": 85,
    "risk_level": "CRITICAL",
    "decision": "BLOCK",
    "signals": ["AMOUNT_SPIKE", "HIGH_RISK_COUNTRY"],
    "reasoning": "Transaction score critically high due to amount spike and high-risk signals.",
    "recommended_action": "Block card and notify customer.",
}


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("AI_FOUNDRY_CONNECTION_STRING", "test-conn-string")
    monkeypatch.setenv("COSMOS_DB_ENDPOINT", "https://test.documents.azure.com:443/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")


def build_mock_client(decision_json: str) -> MagicMock:
    mock_client = MagicMock()
    mock_agent = MagicMock()
    mock_agent.id = "agent-123"
    mock_client.agents.create_agent.return_value = mock_agent

    mock_thread = MagicMock()
    mock_thread.id = "thread-456"
    mock_client.agents.create_thread.return_value = mock_thread

    mock_run = MagicMock()
    mock_run.status = "completed"
    mock_run.id = "run-789"
    mock_client.agents.create_and_process_run.return_value = mock_run

    mock_msg = MagicMock()
    mock_msg.role = "assistant"
    mock_content = MagicMock()
    mock_content.text.value = decision_json
    mock_msg.content = [mock_content]

    mock_messages = MagicMock()
    mock_messages.data = [mock_msg]
    mock_client.agents.list_messages.return_value = mock_messages

    return mock_client


class TestFraudDetectionAgent:

    @patch("src.agent.fraud_agent.AIProjectClient.from_connection_string")
    def test_analyze_transaction_block_decision(self, mock_foundry, mock_env):
        mock_foundry.return_value = build_mock_client(json.dumps(MOCK_DECISION))
        agent = FraudDetectionAgent()
        result = agent.analyze_transaction(SAMPLE_TRANSACTION)

        assert result["transaction_id"] == "TXN-TEST-001"
        assert result["decision"] == "BLOCK"
        assert result["fraud_score"] == 85
        assert result["risk_level"] == "CRITICAL"
        assert "analyzed_at" in result
        assert "agent_run_id" in result

    @patch("src.agent.fraud_agent.AIProjectClient.from_connection_string")
    def test_analyze_transaction_approve_decision(self, mock_foundry, mock_env):
        approve_decision = {**MOCK_DECISION, "fraud_score": 10, "risk_level": "LOW", "decision": "APPROVE"}
        mock_foundry.return_value = build_mock_client(json.dumps(approve_decision))
        agent = FraudDetectionAgent()
        result = agent.analyze_transaction(SAMPLE_TRANSACTION)

        assert result["decision"] == "APPROVE"
        assert result["fraud_score"] == 10

    @patch("src.agent.fraud_agent.AIProjectClient.from_connection_string")
    def test_fallback_on_run_failure(self, mock_foundry, mock_env):
        mock_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.id = "agent-123"
        mock_client.agents.create_agent.return_value = mock_agent
        mock_client.agents.create_thread.return_value = MagicMock(id="thread-x")
        mock_run = MagicMock()
        mock_run.status = "failed"
        mock_run.last_error = "timeout"
        mock_run.id = "run-fail"
        mock_client.agents.create_and_process_run.return_value = mock_run
        mock_foundry.return_value = mock_client

        agent = FraudDetectionAgent()
        result = agent.analyze_transaction(SAMPLE_TRANSACTION)

        assert result["decision"] == "REVIEW"
        assert "agent_error" in result["signals"]

    @patch("src.agent.fraud_agent.AIProjectClient.from_connection_string")
    def test_agent_reuses_existing_id(self, mock_foundry, mock_env):
        mock_foundry.return_value = build_mock_client(json.dumps(MOCK_DECISION))
        agent = FraudDetectionAgent()
        agent.analyze_transaction(SAMPLE_TRANSACTION)
        agent.analyze_transaction(SAMPLE_TRANSACTION)
        assert agent.client.agents.create_agent.call_count == 1

    def test_fallback_decision_structure(self, mock_env):
        agent = FraudDetectionAgent()
        fallback = agent._fallback_decision(SAMPLE_TRANSACTION, "test error")

        assert fallback["transaction_id"] == "TXN-TEST-001"
        assert fallback["decision"] == "REVIEW"
        assert fallback["fraud_score"] == 50
        assert "analyzed_at" in fallback
