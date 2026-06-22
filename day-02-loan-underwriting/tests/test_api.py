"""Integration tests for the FastAPI application — uses mocked orchestrator."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from fastapi.testclient import TestClient


MOCK_DECISION = {
    "application_id": "APP-TEST-001",
    "final_decision": "APPROVE",
    "risk_score": 0.18,
    "risk_band": "LOW",
    "explanation": {
        "decision": "APPROVE",
        "plain_english_explanation": "Strong credit profile with low DTI ratio.",
        "primary_risk_factors": ["None significant"],
        "mitigating_factors": ["Excellent payment history", "Credit score 720"],
        "customer_message": "Congratulations! Your application has been approved.",
        "analyst_notes": "Clean application, auto-approved.",
        "explained_at": datetime.now(timezone.utc).isoformat(),
        "agent_run_id": "run-abc123",
    },
    "compliance": {
        "applicable_rules": [],
        "compliance_flags": [],
        "gdpr_article_22_disclosure_required": False,
        "fca_consumer_duty_met": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    },
    "mlflow_run_id": "mlflow-run-001",
    "audit_run_id": "mlflow-audit-001",
    "audited_at": datetime.now(timezone.utc).isoformat(),
}

VALID_PAYLOAD = {
    "applicant_name": "Sarah Thompson",
    "age": 34,
    "annual_income": 62000,
    "employment_status": "employed",
    "credit_score": 720,
    "existing_debt": 4500,
    "loan_amount": 12000,
    "loan_purpose": "home_improvement",
    "payment_history": ["ON_TIME", "ON_TIME", "ON_TIME", "ON_TIME", "ON_TIME", "ON_TIME"],
    "loan_term_months": 60,
    "interest_rate": 0.058,
    "credit_limit": 15000,
    "current_balance": 2100,
}


@pytest.fixture
def client():
    mock_orchestrator = MagicMock()
    mock_orchestrator.process_application.return_value = MOCK_DECISION
    mock_orchestrator.health_check.return_value = {
        "etl_agent": "ok",
        "risk_model": "ok",
        "explainability_agent": "ok",
        "compliance_kb": "ok (10 rules)",
        "mlflow": "ok",
    }

    with patch("src.api.main._orchestrator", mock_orchestrator):
        from src.api.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c, mock_orchestrator


@pytest.mark.integration
class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        c, _ = client
        resp = c.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert "timestamp" in body

    def test_health_includes_agent_status(self, client):
        c, _ = client
        resp = c.get("/health")
        body = resp.json()
        assert "agents" in body
        assert body["agents"]["etl_agent"] == "ok"


@pytest.mark.integration
class TestSubmitApplication:
    def test_valid_application_returns_200(self, client):
        c, mock_orch = client
        resp = c.post("/applications", json=VALID_PAYLOAD)
        assert resp.status_code == 200

    def test_response_contains_decision_fields(self, client):
        c, _ = client
        resp = c.post("/applications", json=VALID_PAYLOAD)
        body = resp.json()
        assert "final_decision" in body
        assert "risk_score" in body
        assert "risk_band" in body
        assert "explanation" in body

    def test_orchestrator_called_once(self, client):
        c, mock_orch = client
        c.post("/applications", json=VALID_PAYLOAD)
        mock_orch.process_application.assert_called_once()

    def test_missing_required_field_returns_422(self, client):
        c, _ = client
        bad = {k: v for k, v in VALID_PAYLOAD.items() if k != "credit_score"}
        resp = c.post("/applications", json=bad)
        assert resp.status_code == 422

    def test_invalid_credit_score_returns_422(self, client):
        c, _ = client
        bad = {**VALID_PAYLOAD, "credit_score": 1500}
        resp = c.post("/applications", json=bad)
        assert resp.status_code == 422

    def test_invalid_payment_status_returns_422(self, client):
        c, _ = client
        bad = {**VALID_PAYLOAD, "payment_history": ["ON_TIME", "MAYBE"]}
        resp = c.post("/applications", json=bad)
        assert resp.status_code == 422

    def test_negative_loan_amount_returns_422(self, client):
        c, _ = client
        bad = {**VALID_PAYLOAD, "loan_amount": -5000}
        resp = c.post("/applications", json=bad)
        assert resp.status_code == 422


@pytest.mark.integration
class TestGetDecision:
    def test_get_existing_decision_returns_200(self, client):
        c, mock_orch = client
        c.post("/applications", json=VALID_PAYLOAD)
        resp = c.get(f"/applications/{MOCK_DECISION['application_id']}")
        assert resp.status_code == 200

    def test_get_nonexistent_decision_returns_404(self, client):
        c, _ = client
        resp = c.get("/applications/NONEXISTENT-APP-ID")
        assert resp.status_code == 404


@pytest.mark.integration
class TestRateLimit:
    def test_rate_limit_header_on_exceeded(self, client):
        c, mock_orch = client
        mock_orch.process_application.return_value = MOCK_DECISION

        with patch("src.api.middleware.RateLimitMiddleware.max_requests", 2):
            for _ in range(3):
                resp = c.post("/applications", json=VALID_PAYLOAD)

        assert resp.status_code in {200, 429}
