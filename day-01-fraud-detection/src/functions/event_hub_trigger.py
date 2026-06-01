"""
Azure Function — Event Hub trigger.
Consumes transaction events from Azure Event Hub and calls the fraud agent API.
"""
import json
import logging
import os
import httpx
import azure.functions as func

logger = logging.getLogger(__name__)

FRAUD_API_URL = os.environ.get("FRAUD_API_URL", "http://localhost:8000/analyze")
API_KEY = os.environ.get("FRAUD_API_KEY", "")


async def main(events: list[func.EventHubEvent]) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        for event in events:
            body = event.get_body().decode("utf-8")
            try:
                transaction = json.loads(body)
            except json.JSONDecodeError:
                logger.error("Invalid JSON in Event Hub message: %s", body[:200])
                continue

            txn_id = transaction.get("transaction_id", "unknown")
            logger.info("Processing transaction: %s", txn_id)

            try:
                response = await client.post(
                    FRAUD_API_URL,
                    json=transaction,
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": API_KEY,
                    },
                )
                response.raise_for_status()
                decision = response.json()

                logger.info(
                    "Transaction %s → %s (score: %s)",
                    txn_id,
                    decision.get("decision"),
                    decision.get("fraud_score"),
                )

                if decision.get("decision") in ("BLOCK", "REVIEW"):
                    logger.warning("ALERT: %s — %s", txn_id, decision.get("reasoning"))

            except httpx.HTTPError as exc:
                logger.error("HTTP error analyzing transaction %s: %s", txn_id, exc)
            except Exception as exc:
                logger.exception("Unexpected error for transaction %s: %s", txn_id, exc)
