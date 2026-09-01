"""
Transaction routes — simulate demo failures, manually trigger recovery,
and list/inspect transactions.
"""

import random
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import RedirectResponse

from models import AuditEntry, MerchantConfig, RecoveryStatus, Transaction
from store import merchant_configs, transactions_db
from scoring import classify_failure, score_recovery_potential
from strategy import select_strategy
from executor import auto_resolve_mock, process_recovery, fail_expired_mock_link, generate_llm_outreach, execute_recovery
from config import rzp_client

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
        txn.attempts_made = 0
    else:
        # Run the REAL execution engine instead of mocking it!
        result = await execute_recovery(txn, strategy, config)
        txn.status = result.status
        txn.audit = result.audit
        txn.attempts_made = result.attempts_used
        txn.cost_accrued = result.total_cost

    transactions_db[txn.id] = txn

    # Auto-resolve pending/retrying cases after a few seconds so revenue at risk doesn't climb infinitely
    if txn.status in [RecoveryStatus.PENDING, RecoveryStatus.RETRYING]:
        background_tasks.add_task(auto_resolve_mock, txn.id)
    elif txn.status == RecoveryStatus.WAITING_FOR_CUSTOMER:
        background_tasks.add_task(fail_expired_mock_link, txn.id)

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


@router.get("/transactions/{txn_id}/pay")
def pay_transaction(txn_id: str):
    """On-demand generation of a Razorpay link when the user clicks 'Pay Now'."""
    txn = transactions_db.get(txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # If the link was already generated, just redirect to it
    if txn.payment_link_url and "rzp.io" in txn.payment_link_url:
        return RedirectResponse(url=txn.payment_link_url)

    # Generate a fresh live link via Razorpay
    if rzp_client:
        try:
            pl = rzp_client.payment_link.create({
                "amount": txn.amount * 100,
                "currency": "INR",
                "description": "RecoverFlow AI Demo Recovery",
                "reference_id": txn.id,
                "expire_by": int(time.time()) + 960,
                "notes": {"txn_id": txn.id}
            })
            txn.payment_link_id = pl.get("id")
            txn.payment_link_url = pl.get("short_url")
            
            # Log the API cost now that we actually spent it
            txn.audit.append(AuditEntry(
                timestamp=datetime.now(timezone.utc),
                action="Customer opened link. Real Razorpay Payment Link generated.",
                result="success",
                cost_inr=0.50,
                strategy=txn.strategy
            ))
            return RedirectResponse(url=txn.payment_link_url)
        except Exception as e:
            print(f"[ON-DEMAND LINK ERR] {e}")
            raise HTTPException(status_code=500, detail="Failed to generate payment link via Razorpay.")
            
    # Mock fallback if no API keys
    mock_url = f"https://rzp.io/i/mock{random.randint(1000, 9999)}"
    txn.payment_link_url = mock_url
    return RedirectResponse(url=mock_url)




def sync_payment_link(txn: Transaction):
    """Smart Sync: Checks Razorpay for live payment link status."""
    if txn.status == RecoveryStatus.WAITING_FOR_CUSTOMER and txn.payment_link_id and rzp_client:
        try:
            pl = rzp_client.payment_link.fetch(txn.payment_link_id)
            status = pl.get("status")
            if status == "paid":
                txn.status = RecoveryStatus.RECOVERED
                txn.audit.append(AuditEntry(
                    timestamp=datetime.now(timezone.utc),
                    action=f"Payment Link Paid! Revenue recovered: ₹{txn.amount}",
                    result="success",
                    cost_inr=0.0
                ))
            elif status in ["expired", "cancelled"]:
                txn.status = RecoveryStatus.FAILED
                txn.audit.append(AuditEntry(
                    timestamp=datetime.now(timezone.utc),
                    action=f"Payment Link {status}.",
                    result="fail",
                    cost_inr=0.0
                ))
        except Exception as e:
            print(f"Failed to sync link {txn.payment_link_id}: {e}")

@router.get("/transactions")
def list_transactions(status: Optional[str] = None, limit: int = 50):
    """List all transactions with optional filtering."""
    txns = list(transactions_db.values())
    for t in txns:
        sync_payment_link(t)
        
    if status:
        txns = [t for t in txns if t.status.value == status]
    txns = sorted(txns, key=lambda x: x.created_at, reverse=True)[:limit]
    return txns


@router.get("/transactions/{txn_id}")
def get_transaction(txn_id: str):
    """Get detailed transaction with audit trail."""
    txn = transactions_db.get(txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    sync_payment_link(txn)
    return txn
