"""Tool: Retrieves recent transaction history for a customer."""
import os
import json
import logging
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)


def get_transaction_history(customer_id: str, limit: int = 30) -> str:
    """
    Retrieve the last N transactions for a customer from Cosmos DB.

    Args:
        customer_id: Unique customer identifier
        limit: Number of recent transactions to retrieve (default 30)

    Returns:
        JSON string of transaction list with amount, merchant, timestamp, location
    """
    try:
        client = CosmosClient(
            url=os.environ["COSMOS_DB_ENDPOINT"],
            credential=DefaultAzureCredential(),
        )
        db = client.get_database_client(os.environ.get("COSMOS_DB_NAME", "frauddb"))
        container = db.get_container_client("transactions")

        query = (
            "SELECT TOP @limit c.transaction_id, c.amount, c.currency, "
            "c.merchant_name, c.merchant_category, c.timestamp, "
            "c.location_country, c.location_city, c.channel, c.status "
            "FROM c WHERE c.customer_id = @customer_id "
            "ORDER BY c.timestamp DESC"
        )
        items = list(
            container.query_items(
                query=query,
                parameters=[
                    {"name": "@customer_id", "value": customer_id},
                    {"name": "@limit", "value": limit},
                ],
                enable_cross_partition_query=True,
            )
        )
        return json.dumps({"customer_id": customer_id, "transactions": items, "count": len(items)})

    except Exception as exc:
        logger.error("Failed to fetch transaction history for %s: %s", customer_id, exc)
        return json.dumps({"error": str(exc), "customer_id": customer_id, "transactions": []})
