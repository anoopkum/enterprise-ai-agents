"""
Unit tests for the deterministic KYC agents.

These agents are rules-based on purpose (auditable, reproducible), so we can assert
exact verdicts without any Azure/LLM/graph dependency — every agent takes and
returns a plain context dict.
"""
import pytest

from src.agents.identity_agent import identity_agent
from src.agents.screening_agent import screening_agent
from src.agents.decision_agent import decision_agent


def _ctx(customer=None, graph=None, **extra):
    return {"customer": customer or {}, "graph": graph or {}, **extra}


@pytest.mark.unit
class TestScreeningAgent:
    def test_clean_customer_is_clear(self):
        out = screening_agent.screen(_ctx(customer={"pep_status": "No", "sanction_status": "No"}))
        s = out["screening"]
        assert s["verdict"] == "CLEAR"
        assert s["is_pep"] is False and s["is_sanctioned"] is False

    def test_pep_mandates_edd(self):
        out = screening_agent.screen(_ctx(customer={"pep_status": "Yes"}))
        assert out["screening"]["verdict"] == "EDD"
        assert out["screening"]["is_pep"] is True

    def test_sanction_blocks(self):
        out = screening_agent.screen(_ctx(customer={"sanction_status": "Yes"}))
        assert out["screening"]["verdict"] == "BLOCK"

    def test_high_risk_jurisdiction_is_context_not_a_block(self):
        # Residency in Iran/Russia is recorded as a hit but must NOT escalate the
        # verdict on its own — the dataset approves clean customers there.
        out = screening_agent.screen(_ctx(
            customer={"pep_status": "No", "sanction_status": "No"},
            graph={"countries": ["Iran"]},
        ))
        s = out["screening"]
        assert s["verdict"] == "CLEAR"
        assert any(h["type"] == "SANCTIONED_JURISDICTION" for h in s["hits"])


@pytest.mark.unit
class TestIdentityAgent:
    def test_full_document_set_high_confidence_no_gaps(self):
        ctx = _ctx(
            customer={"identity_verified": "Yes"},
            graph={"cases": [{"verified_documents": "5"}], "documents": []},
        )
        out = identity_agent.verify(ctx)
        ident = out["identity"]
        assert ident["gaps"] == []
        assert ident["identity_confidence"] >= 0.9

    def test_insufficient_documents_is_a_gap(self):
        ctx = _ctx(
            customer={"identity_verified": "No"},
            graph={"cases": [{"verified_documents": "2"}], "documents": []},
        )
        out = identity_agent.verify(ctx)
        assert any("Insufficient verified documents" in g for g in out["identity"]["gaps"])

    def test_unverified_address_alone_is_not_a_gap(self):
        # Regression: an unverified address must not, by itself, create a gap.
        ctx = _ctx(
            customer={"identity_verified": "Yes", "address_verified": "No"},
            graph={"cases": [{"verified_documents": "5"}], "documents": []},
        )
        out = identity_agent.verify(ctx)
        assert out["identity"]["gaps"] == []


@pytest.mark.unit
class TestDecisionAgent:
    def _decide(self, identity, screening, aml):
        ctx = {"customer": {"full_name": "Test", "customer_id": "C1"},
               "identity": identity, "screening": screening, "aml": aml}
        return decision_agent.decide(ctx)["decision"]

    def test_block_screening_rejects(self):
        d = self._decide(
            identity={"identity_confidence": 0.9, "gaps": []},
            screening={"verdict": "BLOCK", "is_sanctioned": True, "hits": []},
            aml={"risk_score": 0.2, "findings": []},
        )
        assert d["decision"] == "REJECT"
        assert d["sar"] is not None  # sanctions hit → SAR drafted

    def test_high_risk_score_rejects(self):
        d = self._decide(
            identity={"identity_confidence": 0.9, "gaps": []},
            screening={"verdict": "CLEAR", "hits": []},
            aml={"risk_score": 0.9, "findings": []},
        )
        assert d["decision"] == "REJECT"

    def test_pep_edd(self):
        d = self._decide(
            identity={"identity_confidence": 0.9, "gaps": []},
            screening={"verdict": "EDD", "is_pep": True, "hits": []},
            aml={"risk_score": 0.3, "findings": []},
        )
        assert d["decision"] == "EDD"

    def test_clean_approves_with_a_reason(self):
        d = self._decide(
            identity={"identity_confidence": 0.95, "gaps": []},
            screening={"verdict": "CLEAR", "hits": []},
            aml={"risk_score": 0.1, "findings": []},
        )
        assert d["decision"] == "APPROVE"
        assert d["reasons"]  # explainability: an approval still states why
