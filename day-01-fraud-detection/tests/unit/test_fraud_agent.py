"""Unit tests for FraudDetectionAgent — mocks AI Foundry SDK calls."""
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
    "reasoning": "Transaction score critically high.",
    "recommended_action": "Block card and notify customer.",
}


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("AI_FOUNDRY_ENDPOINT", "https://test.api.azureml.ms")
    monkeypatch.setenv("COSMOS_DB_ENDPOINT", "https://test.documents.azure.com:443/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")


def _make_mock_message(decision_json: str) -> MagicMock:
    """Build a mock ThreadMessage with text content."""
    msg = MagicMock()
    block = MagicMock()
    block.text.value = decision_json
    msg.content = [block]
    return msg


def _build_mock_project_client(decision_json: str) -> MagicMock:
    """Build a mock AgentsClient with all sub-operations wired up.

    AgentsClient exposes create_agent/threads/messages/runs directly (no .agents sub-namespace).
    """
    from azure.ai.agents.models import RunStatus

    client = MagicMock()

    # create_agent — directly on the client
    mock_agent = MagicMock()
    mock_agent.id = "agent-123"
    client.create_agent.return_value = mock_agent

    # threads.create
    mock_thread = MagicMock()
    mock_thread.id = "thread-456"
    client.threads.create.return_value = mock_thread

    # messages.create (fire and forget)
    client.messages.create.return_value = MagicMock()

    # runs.create_and_process — status must equal the real RunStatus enum
    mock_run = MagicMock()
    mock_run.status = RunStatus.COMPLETED
    mock_run.id = "run-789"
    mock_run.last_error = None
    client.runs.create_and_process.return_value = mock_run

    # messages.get_last_message_by_role
    client.messages.get_last_message_by_role.return_value = _make_mock_message(decision_json)

    return client


class TestFraudDetectionAgent:

    @patch("src.agent.fraud_agent.AgentsClient")
    @patch("src.agent.fraud_agent.DefaultAzureCredential")
    def test_analyze_transaction_block_decision(self, mock_cred, mock_client_cls, mock_env):
        mock_client_cls.return_value = _build_mock_project_client(json.dumps(MOCK_DECISION))
        agent = FraudDetectionAgent()
        result = agent.analyze_transaction(SAMPLE_TRANSACTION)

        assert result["transaction_id"] == "TXN-TEST-001"
        assert result["decision"] == "BLOCK"
        assert result["fraud_score"] == 85
        assert result["risk_level"] == "CRITICAL"
        assert "analyzed_at" in result
        assert "agent_run_id" in result

    @patch("src.agent.fraud_agent.AgentsClient")
    @patch("src.agent.fraud_agent.DefaultAzureCredential")
    def test_analyze_transaction_approve_decision(self, mock_cred, mock_client_cls, mock_env):
        approve = {**MOCK_DECISION, "fraud_score": 10, "risk_level": "LOW", "decision": "APPROVE"}
        mock_client_cls.return_value = _build_mock_project_client(json.dumps(approve))
        agent = FraudDetectionAgent()
        result = agent.analyze_transaction(SAMPLE_TRANSACTION)

        assert result["decision"] == "APPROVE"
        assert result["fraud_score"] == 10

    @patch("src.agent.fraud_agent.AgentsClient")
    @patch("src.agent.fraud_agent.DefaultAzureCredential")
    def test_fallback_on_run_failure(self, mock_cred, mock_client_cls, mock_env):
        client = _build_mock_project_client("{}")
        mock_run = MagicMock()
        mock_run.status.value = "failed"
        mock_run.id = "run-fail"
        mock_run.last_error.message = "timeout"
        client.runs.create_and_process.return_value = mock_run

        mock_run.status = "failed"  # raw string won't equal RunStatus.COMPLETED

        mock_client_cls.return_value = client
        agent = FraudDetectionAgent()
        result = agent.analyze_transaction(SAMPLE_TRANSACTION)

        assert result["decision"] == "REVIEW"
        assert "agent_error" in result["signals"]

    @patch("src.agent.fraud_agent.AgentsClient")
    @patch("src.agent.fraud_agent.DefaultAzureCredential")
    def test_agent_reuses_existing_id(self, mock_cred, mock_client_cls, mock_env):
        mock_client_cls.return_value = _build_mock_project_client(json.dumps(MOCK_DECISION))
        agent = FraudDetectionAgent()
        agent.analyze_transaction(SAMPLE_TRANSACTION)
        agent.analyze_transaction(SAMPLE_TRANSACTION)
        # create_agent only called once — id is cached
        assert agent.client.create_agent.call_count == 1

    def test_fallback_decision_structure(self, mock_env):
        agent = FraudDetectionAgent()
        fallback = agent._fallback_decision(SAMPLE_TRANSACTION, "test error")

        assert fallback["transaction_id"] == "TXN-TEST-001"
        assert fallback["decision"] == "REVIEW"
        assert fallback["fraud_score"] == 50
        assert "analyzed_at" in fallback

    @patch("src.agent.fraud_agent.AgentsClient")
    @patch("src.agent.fraud_agent.DefaultAzureCredential")
    def test_fallback_when_no_message_returned(self, mock_cred, mock_client_cls, mock_env):
        client = _build_mock_project_client("{}")
        client.messages.get_last_message_by_role.return_value = None
        mock_client_cls.return_value = client

        agent = FraudDetectionAgent()
        result = agent.analyze_transaction(SAMPLE_TRANSACTION)

        assert result["decision"] == "REVIEW"
        assert "agent_error" in result["signals"]
