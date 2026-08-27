"""
Webhook routes — receives live events from Razorpay, validates the
signature, and triggers the AI agent to recover failed payments.

Note: the old commented-out `/webhooks/razorpay` (unsigned, demo-only)
endpoint from the original single-file version was dropped as dead code.
This is the one real implementation, with signature verification.
"""

import random
from datetime import datetime, timezone

# pyrefly: ignore [missing-import]
import razorpay
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from config import rzp_client, RAZORPAY_WEBHOOK_SECRET
from models import AuditEntry, FailureBucket, RecoveryStatus, Transaction
from store import merchant_configs, transactions_db
from scoring import score_recovery_potential
from strategy import select_strategy
from executor import auto_resolve_mock
from models import MerchantConfig

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/razorpay")
@router.post("/webhooks/razorpay/")
async def razorpay_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives live events from Razorpay, validates the signature,
    and triggers the AI agent to recover failed payments.
    """
    try:
        body = await request.body()
        signature = request.headers.get("X-Razorpay-Signature", "")

        # Verify the webhook signature securely using Razorpay's official SDK
        if not RAZORPAY_WEBHOOK_SECRET:
            raise HTTPException(status_code=500, detail="Webhook secret is not configured on the server.")

        try:
            rzp_client.utility.verify_webhook_signature(
                body.decode('utf-8'),
                signature,
                RAZORPAY_WEBHOOK_SECRET
            )
        except razorpay.errors.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")

        payload = await request.json()
        event = payload.get("event")

        # Only process payment.failed events for now
        if event == "payment.failed":
            payment_entity = payload["payload"]["payment"]["entity"]

            # Map Razorpay's real data to our AI Transaction model
            amount_inr = int(payment_entity.get("amount", 0) / 100)  # Razorpay sends amounts in paise
            error_reason = payment_entity.get("error_description", "Unknown error")
            method = payment_entity.get("method", "Unknown")
            txn_id = payment_entity.get("id")

            # Use real historical context if available, otherwise mock for demo
            customer_history = round(random.random(), 2)  # In reality, fetch from DB
            customer_ltv = random.randint(5000, 200000)  # In reality, fetch from DB

            txn = Transaction(
                id=txn_id,
                amount=amount_inr,
                reason=error_reason,
                method=method,
                ltv=customer_ltv,
                history=customer_history
            )

            # Let the AI Agent classify, score, and strategize
            # Since Razorpay test errors are identical, we randomize the bucket to show different strategies
            txn.bucket = random.choice(list(FailureBucket))
            score_result = score_recovery_potential(txn)
            txn.potential = score_result["score"]

            config = merchant_configs.get("merchant_default", MerchantConfig())
            strategy = select_strategy(txn.potential, txn.bucket, txn.method, config)
            txn.strategy = strategy["action"]

            # Build the rich audit trail
            gateway = payment_entity.get("gateway", "Razorpay")
            txn.audit = [
                AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Live Webhook received: payment.failed — {error_reason} (Gateway: {gateway})", result="fail", strategy="Detection", cost_inr=0.0),
                AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Classified failure: {txn.bucket.value} | Scored recovery potential: {txn.potential}%", result="info", strategy="AI Scoring", cost_inr=0.0),
                AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Selected strategy: {txn.strategy}", result="info", strategy="Strategy Router", cost_inr=0.0),
            ]

            if txn.potential < config.min_recovery_score:
                txn.status = RecoveryStatus.MANUAL_REVIEW
            else:
                txn.status = RecoveryStatus.PENDING

            transactions_db[txn.id] = txn

            # Optionally trigger background auto-recovery logic here
            if txn.status == RecoveryStatus.PENDING:
                background_tasks.add_task(auto_resolve_mock, txn.id)

            print(f"[LIVE WEBHOOK] Processed failed payment {txn.id} for ₹{amount_inr}")
            return {"status": "success"}

        elif event == "payment_link.paid":
            pl_entity = payload["payload"]["payment_link"]["entity"]
            
            # Find the transaction using reference_id or notes
            txn_id = pl_entity.get("reference_id")
            if not txn_id:
                txn_id = pl_entity.get("notes", {}).get("txn_id")
                
            if txn_id and txn_id in transactions_db:
                txn = transactions_db[txn_id]
                txn.status = RecoveryStatus.RECOVERED
                txn.audit.append(
                    AuditEntry(
                        timestamp=datetime.now(timezone.utc),
                        action=f"Payment Link Paid! Revenue recovered: ₹{txn.amount}",
                        result="success",
                        cost_inr=0.0
                    )
                )
                print(f"[LIVE WEBHOOK] Payment link paid for {txn.id}. Recovered!")
                return {"status": "success"}
                
        return {"status": "ignored"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[WEBHOOK ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
