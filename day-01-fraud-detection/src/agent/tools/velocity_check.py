"""Tool: Velocity checking — detects unusual spend frequency or rapid amount spikes."""
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

# Configurable thresholds (override via env)
MAX_TXN_PER_HOUR = int(os.environ.get("VELOCITY_MAX_TXN_PER_HOUR", "5"))
MAX_TXN_PER_DAY = int(os.environ.get("VELOCITY_MAX_TXN_PER_DAY", "20"))
MAX_AMOUNT_SPIKE_MULTIPLIER = float(os.environ.get("VELOCITY_AMOUNT_SPIKE_MULTIPLIER", "5.0"))


def check_velocity(customer_id: str, current_amount: float, current_timestamp: str) -> str:
    """
    Analyse transaction velocity patterns against configurable thresholds.

    Args:
        customer_id: Customer to check
        current_amount: Amount of the incoming transaction
        current_timestamp: ISO8601 timestamp of the incoming transaction

    Returns:
        JSON with velocity_flags list and severity score 0-100
    """
    try:
        client = CosmosClient(
            url=os.environ["COSMOS_DB_ENDPOINT"],
            credential=DefaultAzureCredential(),
        )
        db = client.get_database_client(os.environ.get("COSMOS_DB_NAME", "frauddb"))
        container = db.get_container_client("transactions")

        now = datetime.fromisoformat(current_timestamp.replace("Z", "+00:00"))
        one_hour_ago = (now - timedelta(hours=1)).isoformat()
        one_day_ago = (now - timedelta(days=1)).isoformat()
        thirty_days_ago = (now - timedelta(days=30)).isoformat()

        # Count txns in last hour
        hour_result = list(container.query_items(
            query="SELECT VALUE COUNT(1) FROM c WHERE c.customer_id=@cid AND c.timestamp >= @since",
            parameters=[{"name": "@cid", "value": customer_id}, {"name": "@since", "value": one_hour_ago}],
            enable_cross_partition_query=True,
        ))
        txn_last_hour = hour_result[0] if hour_result else 0

        # Count txns in last 24h
        day_result = list(container.query_items(
            query="SELECT VALUE COUNT(1) FROM c WHERE c.customer_id=@cid AND c.timestamp >= @since",
            parameters=[{"name": "@cid", "value": customer_id}, {"name": "@since", "value": one_day_ago}],
            enable_cross_partition_query=True,
        ))
        txn_last_day = day_result[0] if day_result else 0

        # Average spend over last 30 days
        avg_result = list(container.query_items(
            query="SELECT VALUE AVG(c.amount) FROM c WHERE c.customer_id=@cid AND c.timestamp >= @since",
            parameters=[{"name": "@cid", "value": customer_id}, {"name": "@since", "value": thirty_days_ago}],
            enable_cross_partition_query=True,
        ))
        avg_amount = avg_result[0] if avg_result else 0.0

        flags = []
        velocity_score = 0

        if txn_last_hour > MAX_TXN_PER_HOUR:
            flags.append(f"HIGH_FREQUENCY: {txn_last_hour} transactions in last hour (threshold: {MAX_TXN_PER_HOUR})")
            velocity_score += 40

        if txn_last_day > MAX_TXN_PER_DAY:
            flags.append(f"HIGH_DAILY_VOLUME: {txn_last_day} transactions today (threshold: {MAX_TXN_PER_DAY})")
            velocity_score += 20

        if avg_amount > 0 and current_amount > avg_amount * MAX_AMOUNT_SPIKE_MULTIPLIER:
            spike = round(current_amount / avg_amount, 1)
            flags.append(f"AMOUNT_SPIKE: {spike}x above 30-day average (avg: {avg_amount:.2f})")
            velocity_score += 40

        return json.dumps({
            "customer_id": customer_id,
            "velocity_score": min(velocity_score, 100),
            "velocity_flags": flags,
            "metrics": {
                "txn_last_hour": txn_last_hour,
                "txn_last_day": txn_last_day,
                "avg_amount_30d": round(avg_amount, 2),
                "current_amount": current_amount,
            },
        })

    except Exception as exc:
        logger.error("Velocity check failed for %s: %s", customer_id, exc)
        return json.dumps({"error": str(exc), "velocity_score": 0, "velocity_flags": []})
