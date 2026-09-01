"""
Bounded Executor — runs recovery attempts within merchant-defined bounds
(max retries, max cost, DND hours) and produces a full audit trail.

Also holds the background tasks that mutate `store.transactions_db`
after a request has already returned a response to the client.
"""

import asyncio
import random
import time
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from models import AuditEntry, RecoveryResult, RecoveryStatus, FailureBucket, MerchantConfig, Transaction
from store import transactions_db, merchant_configs
from strategy import select_strategy
from config import rzp_client

def generate_llm_outreach(txn: Transaction) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return f"Hi there, it looks like your {txn.method} payment for ₹{txn.amount} failed due to a {txn.reason.lower()}. No worries at all! Here is a secure link to complete your payment:"
        
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"""Write a very short (2 sentence max) SMS message to a customer whose {txn.method} payment of ₹{txn.amount} just failed.
The failure reason given by the bank was: "{txn.reason}".
The message should be polite, empathetic, and tell them we generated a new secure link for them to try again.
Do not include placeholders for the link, just end the message with a colon."""
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"LLM Error: {e}")
        return f"Hi there, it looks like your {txn.method} payment for ₹{txn.amount} failed due to a {txn.reason.lower()}. No worries at all! Here is a secure link to complete your payment:"



async def execute_recovery(txn: Transaction, strategy: Dict[str, Any], config: MerchantConfig) -> RecoveryResult:
    """
    Execute recovery within merchant-defined bounds.
    Returns full audit trail and result.
    """
    start_time = datetime.now(timezone.utc)
    attempts = 0
    cost_accrued = 0.0
    audit = list(txn.audit)

    max_attempts = strategy["max_attempts"]

    while attempts < max_attempts and cost_accrued < config.max_cost_per_recovery:
        # Check DND
        current_hour = (datetime.now(timezone.utc).hour + 5) % 24  # IST
        if config.dnd_start_hour <= current_hour or current_hour < config.dnd_end_hour:
            audit.append(AuditEntry(
                timestamp=datetime.now(timezone.utc),
                action=f"DND active ({config.dnd_start_hour}:00-{config.dnd_end_hour}:00 IST). Scheduling for next window.",
                result="warn",
                cost_inr=0.0,
            ))
            break

        attempts += 1
        action_name = strategy["action"]
        channel = strategy["channels"][min(attempts - 1, len(strategy["channels"]) - 1)] if strategy["channels"] else "smart_retry"

        # If strategy uses payment links, generate an on-demand link!
        if channel == "payment_link":
            fake_link = f"https://recoverflow-backened.onrender.com/transactions/{txn.id}/pay"
            txn.payment_link_url = fake_link
            cost = 0.0  # Link isn't actually created until they click it!
            cost_accrued += cost
            
            llm_msg = generate_llm_outreach(txn)
            
            audit.append(AuditEntry(
                timestamp=datetime.now(timezone.utc),
                action=f"Attempt #{attempts}: Generated secure payment link via {channel}",
                result="info",
                cost_inr=cost,
                link_url=txn.payment_link_url,
                llm_message=llm_msg
            ))

            time_taken = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # Pause the AI loop here, wait for customer to pay!
            return RecoveryResult(
                txn_id=txn.id,
                status=RecoveryStatus.WAITING_FOR_CUSTOMER,
                amount_recovered=0,
                attempts_used=attempts,
                total_cost=cost_accrued,
                audit=audit,
                time_taken_seconds=time_taken,
            )
            # except Exception as e:
            #     audit.append(AuditEntry(
            #         timestamp=datetime.now(timezone.utc),
            #         action=f"Attempt #{attempts}: Failed to create real payment link — {str(e)}",
            #         result="fail",
            #         cost_inr=0.0,
            #     ))
            #     # Fall through to standard fail logic if it errors
        else:
            # Simulate execution for other channels
            await asyncio.sleep(0.5)  # Simulate API call latency

            cost = strategy.get("cost_per_attempt", 2.5)
            cost_accrued += cost

            # Simulate recovery outcome (65% success rate for demo)
            recovered = random.random() > 0.35

            if recovered:
                audit.append(AuditEntry(
                    timestamp=datetime.now(timezone.utc),
                    action=f"Attempt #{attempts}: {action_name} via {channel} — ₹{txn.amount} recovered",
                    result="success",
                    cost_inr=cost,
                ))
                time_taken = (datetime.now(timezone.utc) - start_time).total_seconds()
                return RecoveryResult(
                    txn_id=txn.id,
                    status=RecoveryStatus.RECOVERED,
                    amount_recovered=txn.amount,
                    attempts_used=attempts,
                    total_cost=cost_accrued,
                    audit=audit,
                    time_taken_seconds=time_taken,
                )
            else:
                audit.append(AuditEntry(
                    timestamp=datetime.now(timezone.utc),
                    action=f"Attempt #{attempts}: {action_name} via {channel} — failed",
                    result="fail",
                    cost_inr=cost,
                ))

                # Stop early on hard failures
                if txn.bucket == FailureBucket.HARD and attempts >= 1:
                    break

    # Max attempts exhausted or cost exceeded
    if cost_accrued >= config.max_cost_per_recovery:
        audit.append(AuditEntry(
            timestamp=datetime.now(timezone.utc),
            action=f"Stopped: cost limit ₹{config.max_cost_per_recovery} exceeded (spent ₹{cost_accrued:.2f})",
            result="warn",
            cost_inr=0.0,
        ))
    else:
        audit.append(AuditEntry(
            timestamp=datetime.now(timezone.utc),
            action=f"Max attempts ({max_attempts}) exhausted. Marked as failed.",
            result="fail",
            cost_inr=0.0,
        ))

    time_taken = (datetime.now(timezone.utc) - start_time).total_seconds()
    return RecoveryResult(
        txn_id=txn.id,
        status=RecoveryStatus.FAILED,
        amount_recovered=0,
        attempts_used=attempts,
        total_cost=cost_accrued,
        audit=audit,
        time_taken_seconds=time_taken,
    )


async def process_recovery(txn_id: str, strategy: Dict[str, Any], config: MerchantConfig):
    """Background task to execute recovery."""
    txn = transactions_db.get(txn_id)
    if not txn:
        return

    result = await execute_recovery(txn, strategy, config)

    # Update transaction
    txn.status = result.status
    txn.audit = result.audit
    txn.attempts_made = result.attempts_used
    txn.cost_accrued = result.total_cost
    transactions_db[txn_id] = txn

    print(f"[RECOVERY] {txn_id}: {result.status.value} | ₹{result.amount_recovered} | {result.attempts_used} attempts | ₹{result.total_cost:.2f} cost")


async def auto_resolve_mock(txn_id: str):
    """Simulates the AI resolving the case in the background after some time."""
    try:
        await asyncio.sleep(12)  # Wait 12 seconds
    except asyncio.CancelledError:
        return
    txn = transactions_db.get(txn_id)
    if txn and txn.status in [RecoveryStatus.PENDING, RecoveryStatus.RETRYING]:
        # Log the attempt method based on the strategy
        config = merchant_configs.get(txn.merchant_id, MerchantConfig())
        strategy = select_strategy(txn.potential, txn.bucket, txn.method, config)
        channels = strategy.get("channels", [])
        channel_name = channels[0] if channels else "system_retry"

        txn.audit.append(AuditEntry(
            timestamp=datetime.now(timezone.utc),
            action=f"Attempt #1: {channel_name.replace('_', ' ').title()} sent",
            result="info",
            strategy=channel_name,
            cost_inr=0.50
        ))

        # Simulate the outcome
        txn.status = random.choices([RecoveryStatus.RECOVERED, RecoveryStatus.FAILED], weights=[75, 25])[0]
        result_str = "success" if txn.status == RecoveryStatus.RECOVERED else "fail"
        action_str = f"₹{txn.amount} recovered successfully (Auto)" if txn.status == RecoveryStatus.RECOVERED else "Max retries exhausted (Auto)"
        
        # Ensure attempts_made is correctly updated
        txn.attempts_made = 1 if txn.status == RecoveryStatus.RECOVERED else strategy.get("max_attempts", 3)

        # Add outcome to audit 1 second later to show sequence
        txn.audit.append(AuditEntry(timestamp=datetime.now(timezone.utc) + timedelta(seconds=1), action=action_str, result=result_str, strategy=channel_name, cost_inr=2.50 if txn.status == RecoveryStatus.RECOVERED else 5.00))

async def fail_expired_mock_link(txn_id: str):
    """Fails a mock payment link if the user didn't pay it in 5 minutes (mock expiry)."""
    try:
        await asyncio.sleep(300) # Wait 5 minutes
    except asyncio.CancelledError:
        return
    txn = transactions_db.get(txn_id)
    if txn and txn.status == RecoveryStatus.WAITING_FOR_CUSTOMER:
        txn.status = RecoveryStatus.FAILED
        txn.audit.append(AuditEntry(
            timestamp=datetime.now(timezone.utc),
            action="Payment link expired after 5 minutes.",
            result="fail",
            cost_inr=0.0
        ))
        print(f"[RECOVERY] {txn_id} payment link expired!")


