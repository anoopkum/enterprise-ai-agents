"""Tool: Blacklist check — merchant, IP address, device fingerprint against known fraud lists."""
import json
import logging
import os
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)


def check_blacklist(
    merchant_id: str,
    ip_address: str,
    device_fingerprint: str,
    card_number_hash: str,
) -> str:
    """
    Check multiple identifiers against the fraud blacklist in Cosmos DB.

    Args:
        merchant_id: Merchant identifier from the transaction
        ip_address: IP address used for transaction
        device_fingerprint: Hashed device ID
        card_number_hash: SHA-256 hash of PAN (never raw card number)

    Returns:
        JSON with blacklist_hits list and blacklist_score 0-100
    """
    try:
        client = CosmosClient(
            url=os.environ["COSMOS_DB_ENDPOINT"],
            credential=DefaultAzureCredential(),
        )
        db = client.get_database_client(os.environ.get("COSMOS_DB_NAME", "frauddb"))
        container = db.get_container_client("blacklists")

        identifiers = [
            ("merchant_id", merchant_id),
            ("ip_address", ip_address),
            ("device_fingerprint", device_fingerprint),
            ("card_hash", card_number_hash),
        ]

        hits = []
        blacklist_score = 0

        for id_type, id_value in identifiers:
            if not id_value:
                continue
            results = list(container.query_items(
                query="SELECT c.type, c.reason, c.added_date, c.severity FROM c WHERE c.type=@type AND c.value=@val",
                parameters=[
                    {"name": "@type", "value": id_type},
                    {"name": "@val", "value": id_value},
                ],
                enable_cross_partition_query=True,
            ))
            for r in results:
                severity = r.get("severity", "MEDIUM")
                hits.append({
                    "type": id_type,
                    "value": id_value,
                    "reason": r.get("reason"),
                    "severity": severity,
                    "added_date": r.get("added_date"),
                })
                blacklist_score += {"LOW": 20, "MEDIUM": 40, "HIGH": 60, "CRITICAL": 100}.get(severity, 40)

        return json.dumps({
            "blacklist_hits": hits,
            "blacklist_score": min(blacklist_score, 100),
            "hit_count": len(hits),
        })

    except Exception as exc:
        logger.error("Blacklist check failed: %s", exc)
        return json.dumps({"error": str(exc), "blacklist_hits": [], "blacklist_score": 0})
