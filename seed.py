"""
Demo data seeding — populates `store.transactions_db` on app startup
so the dashboard has content to show immediately.
"""

import random
from datetime import datetime, timezone

from models import AuditEntry, FailureBucket, RecoveryStatus, Transaction
from store import transactions_db, merchant_configs
from scoring import score_recovery_potential
from strategy import select_strategy


async def seed_data():
    """Seed demo data on startup."""
    demo_txns = [
        {"amount": 2499, "reason": "Insufficient funds", "method": "UPI", "ltv": 45000, "history": 0.82, "bucket": "customer_action"},
        {"amount": 12999, "reason": "Bank timeout", "method": "Credit Card", "ltv": 120000, "history": 0.91, "bucket": "soft"},
        {"amount": 899, "reason": "Expired card", "method": "Debit Card", "ltv": 12000, "history": 0.45, "bucket": "hard"},
        {"amount": 4599, "reason": "Do not honor", "method": "Credit Card", "ltv": 8000, "history": 0.20, "bucket": "hard"},
        {"amount": 599, "reason": "Network error", "method": "UPI", "ltv": 25000, "history": 0.75, "bucket": "soft"},
        {"amount": 8999, "reason": "Checkout drop-off", "method": "UPI", "ltv": 35000, "history": 0.60, "bucket": "checkout_dropoff"},
        {"amount": 349, "reason": "UPI declined", "method": "UPI", "ltv": 5000, "history": 0.50, "bucket": "customer_action"},
        {"amount": 15999, "reason": "Subscription mandate fail", "method": "eNACH", "ltv": 200000, "history": 0.88, "bucket": "soft"},
    ]

    for i, data in enumerate(demo_txns):
        txn = Transaction(
            id=f"pay_{chr(65+i)}{random.randint(1000,9999)}{chr(97+i)}{random.randint(1000,9999)}",
            amount=data["amount"],
            reason=data["reason"],
            method=data["method"],
            ltv=data["ltv"],
            history=data["history"],
            bucket=FailureBucket(data["bucket"]),
        )
        score_result = score_recovery_potential(txn)
        txn.potential = score_result["score"]
        config = merchant_configs["merchant_default"]
        strategy = select_strategy(txn.potential, txn.bucket, txn.method, config)
        txn.strategy = strategy["action"]

        # Pre-set status for demo
        statuses = ["recovered", "recovered", "retrying", "failed", "recovered", "retrying", "pending", "recovered"]
        txn.status = RecoveryStatus(statuses[i])

        txn.audit = [
            AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Webhook received: payment.failed — {data['reason']} (Gateway: HDFC)", result="fail", strategy="Detection", cost_inr=0.0),
            AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Classified failure: {txn.bucket.value} | Scored recovery potential: {txn.potential}%", result="info", strategy="AI Scoring", cost_inr=0.0),
            AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Selected strategy: {txn.strategy} (Optimiser routing)", result="info", strategy="Strategy Router", cost_inr=0.0),
        ]

        if txn.status == RecoveryStatus.RECOVERED:
            txn.audit.append(AuditEntry(timestamp=datetime.now(timezone.utc), action=f"₹{txn.amount} recovered successfully", result="success", strategy=txn.strategy, cost_inr=2.50))
        elif txn.status == RecoveryStatus.FAILED:
            txn.audit.append(AuditEntry(timestamp=datetime.now(timezone.utc), action="Max retries exhausted", result="fail", strategy=txn.strategy, cost_inr=5.00))

        transactions_db[txn.id] = txn

    print(f"[SEED] Loaded {len(demo_txns)} demo transactions")
