"""
Seed Cosmos DB with realistic bank transaction data for fraud detection showcase.

Five customer risk profiles:
  CUST-CLEAN   — 30 normal US transactions → agent should APPROVE
  CUST-VELOCITY — burst of 12 transactions in last hour → agent should REVIEW (HIGH)
  CUST-GEO     — last txn in US, now transacting from KP (FATF blacklist) → BLOCK
  CUST-BLACKLIST — device fingerprint on fraud blacklist → BLOCK
  CUST-MIXED   — moderate spend spike + suspicious merchant → REVIEW (MEDIUM)

Usage:
  pip install azure-cosmos azure-identity
  python scripts/seed_cosmos.py --endpoint https://cosmos-fraud-agent-staging.documents.azure.com:443/

  Or set env var:
  COSMOS_DB_ENDPOINT=https://... python scripts/seed_cosmos.py
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.identity import DefaultAzureCredential

DB_NAME = "frauddb"

# ─── helpers ──────────────────────────────────────────────────────────────────

def _ago(hours: float = 0, days: float = 0, minutes: float = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours, days=days, minutes=minutes)
    return dt.isoformat()


def _txn(
    customer_id: str,
    amount: float,
    country: str,
    city: str,
    lat: float,
    lon: float,
    channel: str,
    merchant_name: str,
    merchant_category: str,
    hours_ago: float = 0,
    status: str = "completed",
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "transaction_id": f"TXN-SEED-{uuid.uuid4().hex[:8].upper()}",
        "customer_id": customer_id,
        "amount": round(amount, 2),
        "currency": "USD",
        "merchant_id": f"MERCH-{hash(merchant_name) % 9000 + 1000}",
        "merchant_name": merchant_name,
        "merchant_category": merchant_category,
        "timestamp": _ago(hours=hours_ago),
        "location_country": country,
        "location_city": city,
        "location_lat": lat,
        "location_lon": lon,
        "channel": channel,
        "ip_address": f"192.168.{hash(customer_id) % 254}.{hash(merchant_name) % 254}",
        "device_fingerprint": f"device-{hash(customer_id) % 9000 + 1000}",
        "card_number_hash": f"sha256-{uuid.uuid4().hex}",
        "status": status,
    }


# ─── customer profiles ────────────────────────────────────────────────────────

def profile_clean() -> list[dict]:
    """CUST-CLEAN: 30 normal US grocery/gas/retail transactions over 30 days → APPROVE."""
    merchants = [
        ("Whole Foods Market", "5411", "New York", 40.7580, -73.9855),
        ("Shell Gas Station", "5541", "New York", 40.7489, -73.9680),
        ("Starbucks", "5812", "New York", 40.7614, -73.9776),
        ("Target", "5311", "New York", 40.7527, -74.0036),
        ("CVS Pharmacy", "5912", "New York", 40.7282, -73.9942),
    ]
    txns = []
    for i in range(30):
        m = merchants[i % len(merchants)]
        txns.append(_txn(
            customer_id="CUST-CLEAN",
            amount=round(15 + (i % 7) * 22.5, 2),
            country="US", city=m[2], lat=m[3], lon=m[4],
            channel="pos",
            merchant_name=m[0], merchant_category=m[1],
            hours_ago=24 * (30 - i),
        ))
    return txns


def profile_velocity() -> list[dict]:
    """CUST-VELOCITY: 12 transactions within the last hour (threshold=5) → HIGH / REVIEW."""
    txns = []
    # Normal history over past 30 days
    for i in range(20):
        txns.append(_txn(
            customer_id="CUST-VELOCITY",
            amount=80 + i * 5, country="US", city="Chicago",
            lat=41.8781, lon=-87.6298, channel="online",
            merchant_name="Amazon", merchant_category="5999",
            hours_ago=24 * (30 - i),
        ))
    # Burst: 12 txns within last 55 minutes (simulating card testing attack)
    for i in range(12):
        txns.append(_txn(
            customer_id="CUST-VELOCITY",
            amount=round(9.99 + i * 1.5, 2),
            country="US", city="Chicago", lat=41.8781, lon=-87.6298,
            channel="online",
            merchant_name="Digital Downloads Co", merchant_category="5735",
            hours_ago=(55 - i * 4) / 60,
        ))
    return txns


def profile_geo() -> list[dict]:
    """CUST-GEO: History in US, latest txn in KP (North Korea, FATF blacklist) → BLOCK."""
    txns = []
    # Clean US history
    for i in range(25):
        txns.append(_txn(
            customer_id="CUST-GEO",
            amount=200 + i * 10, country="US", city="Los Angeles",
            lat=34.0522, lon=-118.2437, channel="pos",
            merchant_name="Trader Joe's", merchant_category="5411",
            hours_ago=24 * (30 - i),
        ))
    # One legitimate UK business trip 3 days ago
    txns.append(_txn(
        customer_id="CUST-GEO",
        amount=450.00, country="GB", city="London",
        lat=51.5074, lon=-0.1278, channel="pos",
        merchant_name="Heathrow Airport Lounge", merchant_category="5812",
        hours_ago=72,
    ))
    return txns


def profile_blacklist() -> list[dict]:
    """CUST-BLACKLIST: Normal customer, but device fingerprint is on blacklist → BLOCK."""
    txns = []
    for i in range(20):
        txns.append(_txn(
            customer_id="CUST-BLACKLIST",
            amount=150 + i * 8, country="US", city="Miami",
            lat=25.7617, lon=-80.1918, channel="online",
            merchant_name="Best Buy", merchant_category="5065",
            hours_ago=24 * (20 - i),
        ))
    return txns


def profile_mixed() -> list[dict]:
    """CUST-MIXED: Moderate history + sudden 8x amount spike at crypto exchange → REVIEW."""
    txns = []
    # Average spend ~$120 over 30 days
    for i in range(25):
        txns.append(_txn(
            customer_id="CUST-MIXED",
            amount=100 + (i % 5) * 20, country="US", city="Seattle",
            lat=47.6062, lon=-122.3321, channel="online",
            merchant_name="Grocery Outlet", merchant_category="5411",
            hours_ago=24 * (30 - i),
        ))
    return txns


# ─── blacklist entries ────────────────────────────────────────────────────────

def blacklist_entries() -> list[dict]:
    """Known fraud entries: stolen device, compromised IP, blacklisted merchant."""
    return [
        {
            "id": str(uuid.uuid4()),
            "type": "device_fingerprint",
            "value": f"device-{hash('CUST-BLACKLIST') % 9000 + 1000}",
            "reason": "Device used in 47 fraudulent transactions across 12 banks",
            "severity": "CRITICAL",
            "added_date": _ago(days=15),
            "reported_by": "FraudShare Network",
        },
        {
            "id": str(uuid.uuid4()),
            "type": "merchant_id",
            "value": "MERCH-6051",
            "reason": "Unregistered crypto exchange facilitating money laundering",
            "severity": "HIGH",
            "added_date": _ago(days=30),
            "reported_by": "FinCEN Advisory 2026-03",
        },
        {
            "id": str(uuid.uuid4()),
            "type": "ip_address",
            "value": "185.220.101.45",
            "reason": "Tor exit node — used in card-not-present fraud ring",
            "severity": "HIGH",
            "added_date": _ago(days=7),
            "reported_by": "Internal Fraud Team",
        },
        {
            "id": str(uuid.uuid4()),
            "type": "card_hash",
            "value": "sha256-compromised-card-001",
            "reason": "Card number confirmed stolen in Acme Corp data breach",
            "severity": "CRITICAL",
            "added_date": _ago(days=2),
            "reported_by": "Breach Alert Service",
        },
    ]


# ─── main ─────────────────────────────────────────────────────────────────────

def seed(endpoint: str, dry_run: bool = False) -> None:
    print(f"\n{'DRY RUN — ' if dry_run else ''}Connecting to Cosmos DB: {endpoint}\n")

    if not dry_run:
        client = CosmosClient(url=endpoint, credential=DefaultAzureCredential())
        db = client.get_database_client(DB_NAME)
        txn_container = db.get_container_client("transactions")
        bl_container = db.get_container_client("blacklists")

    profiles = {
        "CUST-CLEAN (30 normal US txns → APPROVE)": profile_clean(),
        "CUST-VELOCITY (burst 12 txns/hour → HIGH/REVIEW)": profile_velocity(),
        "CUST-GEO (US history → KP transaction → BLOCK)": profile_geo(),
        "CUST-BLACKLIST (stolen device fingerprint → BLOCK)": profile_blacklist(),
        "CUST-MIXED (8x amount spike, crypto → REVIEW)": profile_mixed(),
    }

    total_txns = 0
    for label, txns in profiles.items():
        print(f"  {label}: {len(txns)} transactions")
        if not dry_run:
            for txn in txns:
                try:
                    txn_container.upsert_item(txn)
                except Exception as e:
                    print(f"    WARNING: upsert failed for {txn['transaction_id']}: {e}", file=sys.stderr)
        total_txns += len(txns)

    bl_entries = blacklist_entries()
    print(f"\n  Blacklist entries: {len(bl_entries)}")
    if not dry_run:
        for entry in bl_entries:
            try:
                bl_container.upsert_item(entry)
            except Exception as e:
                print(f"    WARNING: upsert failed for blacklist entry: {e}", file=sys.stderr)

    print(f"\n{'[DRY RUN] Would have seeded' if dry_run else 'Seeded'}: "
          f"{total_txns} transactions + {len(bl_entries)} blacklist entries\n")

    print("Test transactions to send to /analyze:")
    print("=" * 60)
    test_cases = [
        {
            "label": "APPROVE — clean customer, normal US grocery",
            "customer_id": "CUST-CLEAN",
            "amount": 85.50,
            "country": "US",
            "merchant": "Whole Foods Market",
        },
        {
            "label": "REVIEW/HIGH — velocity burst customer",
            "customer_id": "CUST-VELOCITY",
            "amount": 12.99,
            "country": "US",
            "merchant": "Digital Downloads Co",
        },
        {
            "label": "BLOCK — geo jump to FATF blacklist country",
            "customer_id": "CUST-GEO",
            "amount": 3500.00,
            "country": "KP",
            "merchant": "Pyongyang Exchange",
        },
        {
            "label": "BLOCK — device on fraud blacklist",
            "customer_id": "CUST-BLACKLIST",
            "amount": 999.00,
            "country": "US",
            "merchant": "Best Buy",
        },
        {
            "label": "REVIEW/MEDIUM — amount spike at crypto exchange",
            "customer_id": "CUST-MIXED",
            "amount": 9800.00,
            "country": "US",
            "merchant": "CryptoSwap Exchange",
        },
    ]
    for tc in test_cases:
        print(f"\n  [{tc['label']}]")
        payload = {
            "transaction_id": f"TXN-DEMO-{uuid.uuid4().hex[:6].upper()}",
            "customer_id": tc["customer_id"],
            "amount": tc["amount"],
            "currency": "USD",
            "merchant_id": f"MERCH-{abs(hash(tc['merchant'])) % 9000 + 1000}",
            "merchant_name": tc["merchant"],
            "merchant_category": "5411",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "location_country": tc["country"],
            "location_city": "New York",
            "location_lat": 40.7128,
            "location_lon": -74.0060,
            "channel": "online",
            "ip_address": "192.168.1.100",
            "device_fingerprint": f"device-{hash(tc['customer_id']) % 9000 + 1000}",
            "card_number_hash": f"sha256-{uuid.uuid4().hex[:16]}",
        }
        print(f"  curl -s -X POST https://ca-fraud-agent-staging.gentleisland-21cf69fe.eastus2.azurecontainerapps.io/analyze \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{json.dumps(payload)}'")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Cosmos DB with fraud detection test data")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("COSMOS_DB_ENDPOINT", ""),
        help="Cosmos DB endpoint URL",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be seeded, no writes")
    args = parser.parse_args()

    if not args.endpoint and not args.dry_run:
        print("ERROR: provide --endpoint or set COSMOS_DB_ENDPOINT", file=sys.stderr)
        sys.exit(1)

    seed(args.endpoint, dry_run=args.dry_run)
