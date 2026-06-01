"""Unit tests for agent tools — geolocation and velocity (no external deps)."""
import json
import pytest
from unittest.mock import MagicMock, patch

from src.agent.tools.geolocation_risk import assess_geolocation_risk, _haversine_km
from src.agent.tools.velocity_check import check_velocity


class TestHaversine:
    def test_same_location(self):
        assert _haversine_km(51.5, -0.1, 51.5, -0.1) == pytest.approx(0.0, abs=0.01)

    def test_london_to_paris(self):
        dist = _haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
        assert 340 < dist < 360

    def test_london_to_new_york(self):
        dist = _haversine_km(51.5074, -0.1278, 40.7128, -74.0060)
        assert 5500 < dist < 5600


class TestGeolocationRisk:
    def test_high_risk_country_flagged(self):
        result = json.loads(assess_geolocation_risk(
            customer_id="C1",
            current_country="KP",
            current_lat=39.0, current_lon=125.7,
            current_timestamp="2024-06-01T12:00:00Z",
            previous_country="GB",
            previous_lat=51.5, previous_lon=-0.1,
            previous_timestamp="2024-06-01T10:00:00Z",
        ))
        assert result["geo_risk_score"] >= 50
        assert any("HIGH_RISK_COUNTRY" in f for f in result["geo_flags"])

    def test_impossible_travel_flagged(self):
        result = json.loads(assess_geolocation_risk(
            customer_id="C1",
            current_country="US",
            current_lat=40.7128, current_lon=-74.0060,  # New York
            current_timestamp="2024-06-01T10:05:00Z",
            previous_country="GB",
            previous_lat=51.5074, previous_lon=-0.1278,  # London
            previous_timestamp="2024-06-01T10:00:00Z",   # 5 mins earlier
        ))
        assert result["geo_risk_score"] >= 60
        assert any("IMPOSSIBLE_TRAVEL" in f for f in result["geo_flags"])

    def test_normal_travel_no_flags(self):
        result = json.loads(assess_geolocation_risk(
            customer_id="C1",
            current_country="GB",
            current_lat=51.5074, current_lon=-0.1278,
            current_timestamp="2024-06-01T14:00:00Z",
            previous_country="GB",
            previous_lat=51.4800, previous_lon=-0.1200,  # 3km away
            previous_timestamp="2024-06-01T13:30:00Z",
        ))
        assert result["geo_risk_score"] == 0
        assert result["geo_flags"] == []


class TestVelocityCheck:
    @patch("src.agent.tools.velocity_check.CosmosClient")
    @patch("src.agent.tools.velocity_check.DefaultAzureCredential")
    def test_high_frequency_flagged(self, mock_cred, mock_cosmos, monkeypatch):
        monkeypatch.setenv("COSMOS_DB_ENDPOINT", "https://test.documents.azure.com")
        monkeypatch.setenv("VELOCITY_MAX_TXN_PER_HOUR", "5")

        mock_container = MagicMock()
        mock_container.query_items.side_effect = [[10], [5], [100.0]]
        mock_cosmos.return_value.get_database_client.return_value \
            .get_container_client.return_value = mock_container

        result = json.loads(check_velocity("C1", 150.0, "2024-06-01T12:00:00Z"))

        assert result["velocity_score"] > 0
        assert any("HIGH_FREQUENCY" in f for f in result["velocity_flags"])

    @patch("src.agent.tools.velocity_check.CosmosClient")
    @patch("src.agent.tools.velocity_check.DefaultAzureCredential")
    def test_amount_spike_flagged(self, mock_cred, mock_cosmos, monkeypatch):
        monkeypatch.setenv("COSMOS_DB_ENDPOINT", "https://test.documents.azure.com")

        mock_container = MagicMock()
        mock_container.query_items.side_effect = [[1], [2], [50.0]]  # avg 50, current 500
        mock_cosmos.return_value.get_database_client.return_value \
            .get_container_client.return_value = mock_container

        result = json.loads(check_velocity("C1", 500.0, "2024-06-01T12:00:00Z"))

        assert any("AMOUNT_SPIKE" in f for f in result["velocity_flags"])
