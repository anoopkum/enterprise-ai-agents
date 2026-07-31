"""Integration tests for the KYC/AML FastAPI app — orchestrator is mocked."""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


MOCK_RESULT = {
    "customer_id": "C000003",
    "decision": {
        "decision": "EDD",
        "risk_level": "MEDIUM",
        "risk_score": 0.65,
        "reasons": ["Screening flagged PEP / high-risk jurisdiction"],
        "identity_confidence": 0.82,
        "screening_verdict": "EDD",
        "citations": ["aml-R100"],
        "requires_human_review": True,
        "unsafe_to_auto_action": True,
        "guardrail_violations": [],
        "sar": {
            "subject": "Jane Doe",
            "customer_id": "C000003",
            "reason": "Politically Exposed Person",
            "risk_indicators": ["PEP"],
            "recommended_action": "File SAR with FIU and freeze onboarding pending review",
        },
    },
    "hallucination_report": {"flagged_count": 0, "any_hallucination": False},
    "aml": {"assessment_source": "fallback"},
}


@pytest.fixture
def client():
    mock = MagicMock()
    mock.run.return_value = MOCK_RESULT
    mock.health_check.return_value = {
        "vector_store": "chromadb",
        "graph_store": "neo4j",
        "graph_stats": {"nodes": 100, "edges": 200},
    }

    import src.api.main as api_module
    from src.api.main import app

    # Inject the mock before lifespan runs so the `if _orchestrator is None` guard skips init.
    api_module._orchestrator = mock
    api_module._decisions_store.clear()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, mock

    api_module._orchestrator = None
    api_module._decisions_store.clear()


@pytest.mark.integration
class TestRoot:
    def test_root_redirects_to_docs_in_dev(self, client):
        # A bare-URL visit must land on Swagger, not a 404.
        c, _ = client
        resp = c.get("/", follow_redirects=False)
        assert resp.status_code in (307, 308)
        assert resp.headers["location"] == "/docs"


@pytest.mark.integration
class TestHealth:
    def test_health_returns_200(self, client):
        c, _ = client
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_health_reports_components(self, client):
        c, _ = client
        body = c.get("/health").json()
        assert body["components"]["vector_store"] == "chromadb"
        assert body["components"]["graph_store"] == "neo4j"

    def test_health_degraded_when_graph_unavailable(self, client):
        # An unreachable optional backend (e.g. a paused Neo4j Aura instance)
        # must degrade the probe, not 500 it.
        c, mock = client
        mock.health_check.return_value = {
            "vector_store": "azure_search",
            "graph_store": "neo4j",
            "graph_stats": {"backend": "neo4j", "status": "unavailable", "error": "DNS resolve failed"},
        }
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"


@pytest.mark.integration
class TestScreen:
    def test_screen_by_id_returns_decision(self, client):
        c, mock = client
        resp = c.post("/screen", json={"customer_id": "C000003"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "EDD"
        assert body["screening_verdict"] == "EDD"
        assert body["sar"]["risk_indicators"] == ["PEP"]
        mock.run.assert_called_once()

    def test_screen_flattens_nested_result(self, client):
        c, _ = client
        body = c.post("/screen", json={"customer_id": "C000003"}).json()
        # The API flattens orchestrator output into the KYCDecision shape.
        assert body["risk_score"] == 0.65
        assert body["assessment_source"] == "fallback"
        assert body["hallucination_flagged"] == 0

    def test_empty_request_is_422(self, client):
        c, _ = client
        resp = c.post("/screen", json={})
        assert resp.status_code == 422


@pytest.mark.integration
class TestDecisionsCache:
    def test_get_after_screen_returns_200(self, client):
        c, _ = client
        c.post("/screen", json={"customer_id": "C000003"})
        resp = c.get("/decisions/C000003")
        assert resp.status_code == 200
        assert resp.json()["customer_id"] == "C000003"

    def test_get_unknown_is_404(self, client):
        c, _ = client
        assert c.get("/decisions/NOPE").status_code == 404
