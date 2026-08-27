"""
Transaction routes — simulate demo failures, manually trigger recovery,
and list/inspect transactions.
"""

import random
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from models import AuditEntry, MerchantConfig, RecoveryStatus, Transaction
from store import merchant_configs, transactions_db
from scoring import classify_failure, score_recovery_potential
from strategy import select_strategy
from executor import auto_resolve_mock, process_recovery

router = APIRouter(tags=["transactions"])


@router.post("/transactions/simulate")
async def simulate_failure(background_tasks: BackgroundTasks):
    """Simulate a payment failure for demo purposes."""
    reasons = ['Bank timeout', 'Insufficient funds', 'Network error', 'Expired card', 'UPI declined', 'Do not honor', 'Checkout drop-off']
    methods = ['UPI', 'Credit Card', 'Debit Card', 'eNACH']
    reason = random.choice(reasons)
    method = random.choice(methods)
    amount = random.choice([349, 599, 899, 1299, 2499, 4599, 8999, 12999, 15999])

    txn = Transaction(
        id=f"pay_{random.randint(10000000, 99999999)}",
        amount=amount,
        reason=reason,
        method=method,
        ltv=random.randint(5000, 200000),
        history=round(random.random(), 2),
    )
    txn.bucket = classify_failure(reason, reason)
    score_result = score_recovery_potential(txn)
    txn.potential = score_result["score"]

    config = merchant_configs["merchant_default"]
    strategy = select_strategy(txn.potential, txn.bucket, txn.method, config)
    txn.strategy = strategy["action"]

    gateway = random.choice(['HDFC', 'ICICI', 'Razorpay', 'Stripe'])
    txn.audit = [
        AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Webhook received: payment.failed — {reason} (Gateway: {gateway})", result="fail", strategy="Detection", cost_inr=0.0),
        AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Classified failure: {txn.bucket.value} | Scored recovery potential: {txn.potential}%", result="info", strategy="AI Scoring", cost_inr=0.0),
        AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Selected strategy: {txn.strategy} (Optimiser routing)", result="info", strategy="Strategy Router", cost_inr=0.0),
    ]

    if txn.potential < config.min_recovery_score:
        txn.status = RecoveryStatus.MANUAL_REVIEW
    else:
        # Heavily favor RECOVERED to showcase a successful AI agent (60% recovered, 25% retrying, 10% pending, 10% failed)
        txn.status = random.choices(
            population=[
                RecoveryStatus.RECOVERED,
                RecoveryStatus.RETRYING,
                RecoveryStatus.PENDING,
                RecoveryStatus.FAILED
            ],
            weights=[60, 25, 10, 10],
            k=1
        )[0]

    if txn.status == RecoveryStatus.RECOVERED:
        txn.audit.append(AuditEntry(timestamp=datetime.now(timezone.utc), action=f"₹{txn.amount} recovered successfully via {method}", result="success", strategy=txn.strategy, cost_inr=2.50))
    elif txn.status == RecoveryStatus.FAILED:
        txn.audit.append(AuditEntry(timestamp=datetime.now(timezone.utc), action="Max retries exhausted", result="fail", strategy=txn.strategy, cost_inr=5.00))

    transactions_db[txn.id] = txn

    # Auto-resolve pending/retrying cases after a few seconds so revenue at risk doesn't climb infinitely
    if txn.status in [RecoveryStatus.PENDING, RecoveryStatus.RETRYING]:
        background_tasks.add_task(auto_resolve_mock, txn.id)

    return {"status": txn.status.value, "txn_id": txn.id, "amount": txn.amount}


@router.post("/transactions/{txn_id}/recover")
async def trigger_recovery(txn_id: str, background_tasks: BackgroundTasks):
    """Manually trigger recovery for a pending transaction."""
    txn = transactions_db.get(txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    config = merchant_configs.get(txn.merchant_id, MerchantConfig())
    strategy = select_strategy(txn.potential, txn.bucket, txn.method, config)

    txn.status = RecoveryStatus.RETRYING
    background_tasks.add_task(process_recovery, txn_id, strategy, config)

    return {"status": "recovery_started", "txn_id": txn_id}


@router.get("/transactions")
async def list_transactions(status: Optional[str] = None, limit: int = 50):
    """List all transactions with optional filtering."""
    txns = list(transactions_db.values())
    if status:
        txns = [t for t in txns if t.status.value == status]
    txns = sorted(txns, key=lambda x: x.created_at, reverse=True)[:limit]
    return txns


@router.get("/transactions/{txn_id}")
async def get_transaction(txn_id: str):
    """Get detailed transaction with audit trail."""
    txn = transactions_db.get(txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn
