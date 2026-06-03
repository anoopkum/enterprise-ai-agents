"""
Load test for Fraud Detection Agent — staging environment.

Scenarios:
  1. HealthCheck   — lightweight GET /health (weight 2)
  2. NormalTxn     — typical low-risk card transaction (weight 5)
  3. HighValueTxn  — high-amount transaction triggering deeper analysis (weight 2)
  4. SuspiciousTxn — high-risk: foreign country, large amount, unusual merchant (weight 1)

Run (headless, 30s ramp, 60s sustained):
  locust -f tests/load/locustfile.py \
    --host https://ca-fraud-agent-staging.gentleisland-21cf69fe.eastus2.azurecontainerapps.io \
    --headless -u 20 -r 2 -t 90s \
    --html tests/load/report.html \
    --csv tests/load/results
"""

import random
import uuid
from datetime import datetime, timezone

from locust import HttpUser, TaskSet, between, events, task


def _txn(amount: float, country: str, channel: str, merchant: str, category: str) -> dict:
    return {
        "transaction_id": f"TXN-LOAD-{uuid.uuid4().hex[:8].upper()}",
        "customer_id": f"CUST-{random.randint(1000, 9999)}",
        "amount": amount,
        "currency": "USD",
        "merchant_id": f"MERCH-{random.randint(100, 999)}",
        "merchant_name": merchant,
        "merchant_category": category,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "location_country": country,
        "location_city": "New York",
        "location_lat": round(random.uniform(40.0, 41.0), 4),
        "location_lon": round(random.uniform(-74.5, -73.5), 4),
        "channel": channel,
        "ip_address": f"192.168.{random.randint(1,254)}.{random.randint(1,254)}",
        "device_fingerprint": f"device-{random.randint(1000, 9999)}",
        "card_number_hash": f"hash-{uuid.uuid4().hex[:16]}",
    }


class FraudDetectionTasks(TaskSet):

    @task(2)
    def health_check(self):
        with self.client.get("/health", name="GET /health", catch_response=True) as r:
            if r.status_code == 200 and "healthy" in r.text:
                r.success()
            else:
                r.failure(f"Unexpected: {r.status_code} {r.text[:80]}")

    @task(5)
    def normal_transaction(self):
        payload = _txn(
            amount=round(random.uniform(10, 500), 2),
            country="US",
            channel=random.choice(["pos", "online", "mobile"]),
            merchant="Grocery Store",
            category="5411",
        )
        with self.client.post("/analyze", json=payload, name="POST /analyze [normal]", catch_response=True) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 500:
                r.failure(f"500: {r.text[:120]}")
            elif r.status_code == 429:
                r.failure("Rate limited")
            else:
                r.failure(f"{r.status_code}: {r.text[:80]}")

    @task(2)
    def high_value_transaction(self):
        payload = _txn(
            amount=round(random.uniform(5000, 50000), 2),
            country="US",
            channel="online",
            merchant="Electronics Retailer",
            category="5065",
        )
        with self.client.post("/analyze", json=payload, name="POST /analyze [high-value]", catch_response=True) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 500:
                r.failure(f"500: {r.text[:120]}")
            else:
                r.failure(f"{r.status_code}: {r.text[:80]}")

    @task(1)
    def suspicious_transaction(self):
        payload = _txn(
            amount=round(random.uniform(1000, 9999), 2),
            country=random.choice(["NG", "KP", "IR", "RU"]),  # FATF high-risk
            channel="online",
            merchant="Crypto Exchange",
            category="6051",
        )
        with self.client.post("/analyze", json=payload, name="POST /analyze [suspicious]", catch_response=True) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 500:
                r.failure(f"500: {r.text[:120]}")
            else:
                r.failure(f"{r.status_code}: {r.text[:80]}")


class FraudAgentUser(HttpUser):
    tasks = [FraudDetectionTasks]
    # Wait 1–3s between requests per user (realistic fraud system usage pattern)
    wait_time = between(1, 3)


@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Print a final summary when the test ends."""
    stats = environment.stats
    total = stats.total
    print("\n" + "=" * 60)
    print("LOAD TEST SUMMARY")
    print("=" * 60)
    print(f"  Total requests  : {total.num_requests}")
    print(f"  Failures        : {total.num_failures} ({100 * total.fail_ratio:.1f}%)")
    print(f"  Avg response    : {total.avg_response_time:.0f} ms")
    print(f"  95th percentile : {total.get_response_time_percentile(0.95):.0f} ms")
    print(f"  99th percentile : {total.get_response_time_percentile(0.99):.0f} ms")
    print(f"  Requests/sec    : {total.current_rps:.1f}")
    print("=" * 60)
