"""Tool: Geolocation risk — impossible travel detection + high-risk country flagging."""
import json
import logging
import math
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Countries flagged as high-risk (FATF blacklist + grey list + internal policy)
HIGH_RISK_COUNTRIES = {
    "KP", "IR", "MM", "BY", "CU", "SY", "VE", "YE", "SD", "SO",
    "LY", "ML", "CF", "CD", "SS", "NI", "ZW",
}

IMPOSSIBLE_TRAVEL_SPEED_KMH = float(os.environ.get("IMPOSSIBLE_TRAVEL_SPEED_KMH", "900"))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def assess_geolocation_risk(
    customer_id: str,
    current_country: str,
    current_lat: float,
    current_lon: float,
    current_timestamp: str,
    previous_country: str,
    previous_lat: float,
    previous_lon: float,
    previous_timestamp: str,
) -> str:
    """
    Detect impossible travel and high-risk country transactions.

    Args:
        customer_id: Customer identifier
        current_country: ISO-3166 country code of current transaction
        current_lat: Latitude of current transaction
        current_lon: Longitude of current transaction
        current_timestamp: ISO8601 timestamp of current transaction
        previous_country: Country of last known transaction
        previous_lat: Latitude of previous transaction
        previous_lon: Longitude of previous transaction
        previous_timestamp: ISO8601 timestamp of previous transaction

    Returns:
        JSON with geo_flags and geo_risk_score 0-100
    """
    flags = []
    geo_score = 0

    try:
        if current_country.upper() in HIGH_RISK_COUNTRIES:
            flags.append(f"HIGH_RISK_COUNTRY: {current_country} is on restricted list")
            geo_score += 50

        if previous_lat and previous_lon:
            distance_km = _haversine_km(previous_lat, previous_lon, current_lat, current_lon)

            t1 = datetime.fromisoformat(previous_timestamp.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(current_timestamp.replace("Z", "+00:00"))
            hours_elapsed = max((t2 - t1).total_seconds() / 3600, 0.001)

            speed_kmh = distance_km / hours_elapsed

            if speed_kmh > IMPOSSIBLE_TRAVEL_SPEED_KMH:
                flags.append(
                    f"IMPOSSIBLE_TRAVEL: {distance_km:.0f}km in {hours_elapsed:.2f}h "
                    f"({speed_kmh:.0f} km/h, threshold: {IMPOSSIBLE_TRAVEL_SPEED_KMH} km/h)"
                )
                geo_score += 60

            if previous_country != current_country and hours_elapsed < 1:
                flags.append(
                    f"COUNTRY_SWITCH: {previous_country}→{current_country} within {hours_elapsed*60:.0f} minutes"
                )
                geo_score += 20

        return json.dumps({
            "customer_id": customer_id,
            "geo_risk_score": min(geo_score, 100),
            "geo_flags": flags,
            "current_country": current_country,
            "previous_country": previous_country,
        })

    except Exception as exc:
        logger.error("Geolocation assessment failed for %s: %s", customer_id, exc)
        return json.dumps({"error": str(exc), "geo_risk_score": 0, "geo_flags": []})
