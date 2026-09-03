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
from scoring import classify_failure, score_recovery_potential
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
            subscription_id = payment_entity.get("subscription_id")

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
            if subscription_id:
                txn.bucket = FailureBucket.SUBSCRIPTION_FAILED
            else:
                txn.bucket = classify_failure(error_reason)
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

            if txn.potential < config.min_recovery_score or txn.strategy == "manual_review":
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

        elif event == "invoice.expired":
            invoice_entity = payload["payload"]["invoice"]["entity"]
            amount_inr = int(invoice_entity.get("amount", 0) / 100)
            txn_id = invoice_entity.get("id")
            
            txn = Transaction(
                id=txn_id,
                amount=amount_inr,
                reason="Invoice Expired (Net-30 unpaid)",
                method="Invoice",
                ltv=100000,
                history=0.8,
                bucket=FailureBucket.B2B_OVERDUE
            )
            
            score_result = score_recovery_potential(txn)
            txn.potential = score_result["score"]
            config = merchant_configs.get("merchant_default", MerchantConfig())
            strategy = select_strategy(txn.potential, txn.bucket, txn.method, config)
            txn.strategy = strategy["action"]
            
            txn.audit = [
                AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Live Webhook received: invoice.expired", result="fail", strategy="Detection", cost_inr=0.0),
                AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Classified failure: {txn.bucket.value} | Scored recovery potential: {txn.potential}%", result="info", strategy="AI Scoring", cost_inr=0.0),
                AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Selected strategy: {txn.strategy}", result="info", strategy="Strategy Router", cost_inr=0.0),
            ]
            txn.status = RecoveryStatus.PENDING
            transactions_db[txn.id] = txn
            background_tasks.add_task(auto_resolve_mock, txn.id)
            print(f"[LIVE WEBHOOK] Processed B2B expired invoice {txn.id}")
            return {"status": "success"}
            
        elif event in ["subscription.cancelled", "subscription.halted"]:
            sub_entity = payload["payload"]["subscription"]["entity"]
            txn_id = sub_entity.get("id")
            
            amount_inr = 0
            plan_id = sub_entity.get("plan_id")
            if plan_id and rzp_client:
                try:
                    plan = rzp_client.plan.fetch(plan_id)
                    amount_inr = int(plan.get("item", {}).get("amount", 0) / 100)
                except Exception as e:
                    print(f"Error fetching plan for subscription: {e}")
            
            txn = Transaction(
                id=txn_id,
                amount=amount_inr,
                reason=f"Subscription {event.split('.')[1].title()}",
                method="Subscription",
                bucket=FailureBucket.SUBSCRIPTION_FAILED,
                status=RecoveryStatus.MANUAL_REVIEW,
                strategy="Manual intervention required"
            )
            txn.audit = [
                AuditEntry(timestamp=datetime.now(timezone.utc), action=f"Live Webhook received: {event}", result="fail", cost_inr=0.0)
            ]
            transactions_db[txn.id] = txn
            print(f"[LIVE WEBHOOK] Processed subscription {event.split('.')[1]} {txn.id}")
            return {"status": "success"}
                
        return {"status": "ignored"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[WEBHOOK ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

from pydantic import BaseModel
class InboundMessage(BaseModel):
    txn_id: str
    message: str

@router.post("/webhooks/inbound-message")
async def inbound_message(payload: InboundMessage):
    """Mock webhook to receive SMS replies and extract Promise-to-Pay dates using Gemini."""
    txn = transactions_db.get(payload.txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.audit.append(AuditEntry(
        timestamp=datetime.now(timezone.utc),
        action=f"Received inbound SMS: '{payload.message}'",
        result="info",
        cost_inr=0.0
    ))
    
    import os
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            import json
            prompt = f"""
Analyze this customer message: '{payload.message}'.
Today is: {datetime.now().strftime('%Y-%m-%d')}
Extract the promise to pay date if they mention one.

Respond ONLY with valid JSON in this exact format, with no markdown formatting or extra text:
{{
  "date": "YYYY-MM-DD" or null if no date is promised,
  "confidence": "high", "medium", or "low",
  "reasoning": "short explanation of why you chose this date and confidence level"
}}
"""
            response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
            raw_text = response.text.strip()
            print(f"[GEMINI RAW] {raw_text}")
            
            # Strip markdown code blocks if present
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:-3].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:-3].strip()
                
            try:
                result_json = json.loads(raw_text)
                extracted_date = result_json.get("date")
                confidence = result_json.get("confidence")
                reasoning = result_json.get("reasoning", "No reasoning provided")
                
                # Hybrid Logic Implementation
                if txn.amount > 50000: # Example high value threshold (₹50,000)
                    txn.status = RecoveryStatus.MANUAL_REVIEW
                    txn.audit.append(AuditEntry(
                        timestamp=datetime.now(timezone.utc),
                        action=f"High-value txn sent to manual review. AI reasoning: {reasoning}",
                        result="info",
                        strategy="Hybrid NLP",
                        cost_inr=0.0
                    ))
                    return {"status": "manual_review", "note": "High value transaction"}
                    
                elif extracted_date and confidence == "high":
                    promise_date = datetime.strptime(extracted_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    txn.promise_date = promise_date
                    txn.status = RecoveryStatus.PROMISE_TO_PAY
                    txn.audit.append(AuditEntry(
                        timestamp=datetime.now(timezone.utc),
                        action=f"AI extracted high-confidence date: {extracted_date}. Reason: {reasoning}",
                        result="success",
                        strategy="Hybrid NLP",
                        cost_inr=0.0
                    ))
                    print(f"[NLP] High-confidence promise date: {extracted_date} for {txn.id}")
                    return {"status": "promise_logged", "date": extracted_date}
                    
                elif len(payload.message.split()) > 5 or confidence in ["medium", "low"]:
                    txn.status = RecoveryStatus.MANUAL_REVIEW
                    txn.audit.append(AuditEntry(
                        timestamp=datetime.now(timezone.utc),
                        action=f"Vague/complex message sent to manual review. AI reasoning: {reasoning}",
                        result="warn",
                        strategy="Hybrid NLP",
                        cost_inr=0.0
                    ))
                    return {"status": "manual_review", "note": "Vague or complex message"}
                else:
                    # Message didn't contain a date and was short/simple
                    pass
            except (json.JSONDecodeError, ValueError) as e:
                print(f"[NLP JSON/Parse ERROR] {e}")
        except Exception as e:
            print(f"[NLP ERROR] {e}")
            
    return {"status": "message_logged", "note": "No promise date detected or API error."}
