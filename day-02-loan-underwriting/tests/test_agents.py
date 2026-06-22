"""Unit tests for loan intelligence agents — no external dependencies required."""
import json
import pytest
from unittest.mock import MagicMock, patch, mock_open


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_APPLICATION = {
    "application_id": "APP-TEST-001",
    "applicant_name": "Test User",
    "age": 35,
    "annual_income": 60000,
    "employment_status": "employed",
    "credit_score": 700,
    "existing_debt": 5000,
    "loan_amount": 15000,
    "loan_purpose": "home_improvement",
    "payment_history": ["ON_TIME", "ON_TIME", "ON_TIME", "LATE", "ON_TIME", "ON_TIME"],
    "loan_term_months": 60,
    "interest_rate": 0.065,
    "credit_limit": 12000,
    "current_balance": 3600,
}

DECLINED_APPLICATION = {
    **VALID_APPLICATION,
    "application_id": "APP-TEST-002",
    "credit_score": 480,
    "existing_debt": 45000,
    "annual_income": 22000,
    "payment_history": ["MISSED", "MISSED", "LATE", "MISSED", "MISSED", "LATE"],
}


# ── Data ingestion ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestDataIngestion:
    def test_valid_application_passes(self):
        from src.tools.data_ingestion import validate_and_normalise
        result = validate_and_normalise(VALID_APPLICATION)
        assert result["credit_score"] == 700
        assert result["employment_status"] == "employed"

    def test_missing_field_raises(self):
        from src.tools.data_ingestion import validate_and_normalise
        bad = {k: v for k, v in VALID_APPLICATION.items() if k != "credit_score"}
        with pytest.raises(ValueError, match="Missing required fields"):
            validate_and_normalise(bad)

    def test_invalid_credit_score_raises(self):
        from src.tools.data_ingestion import validate_and_normalise
        bad = {**VALID_APPLICATION, "credit_score": 1200}
        with pytest.raises(ValueError, match="credit_score"):
            validate_and_normalise(bad)

    def test_invalid_payment_status_raises(self):
        from src.tools.data_ingestion import validate_and_normalise
        bad = {**VALID_APPLICATION, "payment_history": ["ON_TIME", "SOMETIMES"]}
        with pytest.raises(ValueError, match="payment_history"):
            validate_and_normalise(bad)

    def test_employment_status_normalised(self):
        from src.tools.data_ingestion import validate_and_normalise
        app = {**VALID_APPLICATION, "employment_status": "Self Employed"}
        result = validate_and_normalise(app)
        assert result["employment_status"] == "self_employed"

    def test_unknown_loan_purpose_defaults_to_other(self):
        from src.tools.data_ingestion import validate_and_normalise
        app = {**VALID_APPLICATION, "loan_purpose": "gambling"}
        result = validate_and_normalise(app)
        assert result["loan_purpose"] == "other"


# ── Feature engineering ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestFeatureEngineering:
    def test_dti_ratio_computed(self):
        from src.tools.data_ingestion import validate_and_normalise
        from src.tools.feature_engineering import engineer_features
        normalised = validate_and_normalise(VALID_APPLICATION)
        enriched = engineer_features(normalised)
        assert "dti_ratio" in enriched
        assert enriched["dti_ratio"] > 0

    def test_payment_history_score_all_on_time(self):
        from src.tools.data_ingestion import validate_and_normalise
        from src.tools.feature_engineering import engineer_features
        app = {**VALID_APPLICATION, "payment_history": ["ON_TIME"] * 6}
        enriched = engineer_features(validate_and_normalise(app))
        assert enriched["payment_history_score"] == 100
        assert enriched["missed_payments_count"] == 0

    def test_payment_history_score_all_missed(self):
        from src.tools.data_ingestion import validate_and_normalise
        from src.tools.feature_engineering import engineer_features
        app = {**VALID_APPLICATION, "payment_history": ["MISSED"] * 6}
        enriched = engineer_features(validate_and_normalise(app))
        assert enriched["payment_history_score"] == 0
        assert enriched["missed_payments_count"] == 6

    def test_credit_utilisation_computed(self):
        from src.tools.data_ingestion import validate_and_normalise
        from src.tools.feature_engineering import engineer_features
        enriched = engineer_features(validate_and_normalise(VALID_APPLICATION))
        assert 0.0 <= enriched["credit_utilisation_rate"] <= 1.0

    def test_zero_credit_limit_handled(self):
        from src.tools.data_ingestion import validate_and_normalise
        from src.tools.feature_engineering import engineer_features
        app = {**VALID_APPLICATION, "credit_limit": 0.0, "current_balance": 0.0}
        enriched = engineer_features(validate_and_normalise(app))
        assert enriched["credit_utilisation_rate"] == 0.0

    def test_employment_stability_unemployed(self):
        from src.tools.data_ingestion import validate_and_normalise
        from src.tools.feature_engineering import engineer_features
        app = {**VALID_APPLICATION, "employment_status": "unemployed"}
        enriched = engineer_features(validate_and_normalise(app))
        assert enriched["employment_stability_score"] == 10


# ── Risk scoring ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRiskScoringAgent:
    def test_risk_band_low(self):
        from src.agents.risk_scoring_agent import _band
        assert _band(0.15) == "LOW"

    def test_risk_band_medium(self):
        from src.agents.risk_scoring_agent import _band
        assert _band(0.35) == "MEDIUM"

    def test_risk_band_high(self):
        from src.agents.risk_scoring_agent import _band
        assert _band(0.65) == "HIGH"

    def test_risk_band_critical(self):
        from src.agents.risk_scoring_agent import _band
        assert _band(0.90) == "CRITICAL"

    def test_risk_band_boundary_exactly_025(self):
        from src.agents.risk_scoring_agent import _band
        assert _band(0.25) == "MEDIUM"

    def test_risk_band_boundary_exactly_050(self):
        from src.agents.risk_scoring_agent import _band
        assert _band(0.50) == "HIGH"


# ── Model inference ───────────────────────────────────────────────────────────

@pytest.mark.unit
class TestModelInference:
    def test_feature_vector_ordered(self):
        from src.tools.model_inference import build_feature_vector
        from src.tools.data_ingestion import validate_and_normalise
        from src.tools.feature_engineering import engineer_features

        enriched = engineer_features(validate_and_normalise(VALID_APPLICATION))
        feature_names = [
            "age", "annual_income", "credit_score", "existing_debt",
            "loan_amount", "loan_term_months", "dti_ratio",
            "credit_utilisation_rate", "payment_history_score",
            "missed_payments_count", "late_payments_count",
            "loan_to_income_ratio", "employment_stability_score",
            "monthly_income", "estimated_monthly_payment",
        ]
        vec = build_feature_vector(enriched, feature_names)
        assert len(vec) == len(feature_names)
        assert vec[0] == float(VALID_APPLICATION["age"])

    def test_missing_feature_defaults_zero(self):
        from src.tools.model_inference import build_feature_vector
        vec = build_feature_vector({}, ["age", "credit_score"])
        assert vec == [0.0, 0.0]


# ── Compliance agent ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestComplianceAgent:
    def test_gdpr_flag_on_decline(self):
        from src.agents.compliance_agent import ComplianceAgent
        agent = ComplianceAgent.__new__(ComplianceAgent)
        agent._chroma_client = None
        agent._kb_collection = None

        flags = agent._evaluate_flags("DECLINE", {"dti_ratio": 0.3, "credit_score": 700, "loan_amount": 10000, "annual_income": 50000}, [])
        rule_refs = [f["rule_ref"] for f in flags]
        assert any("GDPR" in r for r in rule_refs)

    def test_high_dti_flag_triggered(self):
        from src.agents.compliance_agent import ComplianceAgent
        agent = ComplianceAgent.__new__(ComplianceAgent)
        flags = agent._evaluate_flags("REFER", {"dti_ratio": 0.60, "credit_score": 650, "loan_amount": 20000, "annual_income": 30000}, [])
        rule_refs = [f["rule_ref"] for f in flags]
        assert any("CONC" in r for r in rule_refs)

    def test_no_critical_flags_for_clean_approval(self):
        from src.agents.compliance_agent import ComplianceAgent
        agent = ComplianceAgent.__new__(ComplianceAgent)
        flags = agent._evaluate_flags("APPROVE", {"dti_ratio": 0.20, "credit_score": 780, "loan_amount": 10000, "annual_income": 80000}, [])
        critical = [f for f in flags if f["severity"] == "CRITICAL"]
        assert len(critical) == 0
