"""
RecoverFlow AI — Backend API
Razorpay Buildathon 2026

A context-aware revenue recovery engine that:
1. Receives Razorpay webhooks (payment.failed, subscription.pending, etc.)
2. Scores recovery potential using ML features
3. Selects optimal intervention strategy
4. Executes bounded recovery with merchant rules
5. Tracks every rupee recovered with full audit trail

Run: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
import random
import json
import asyncio

app = FastAPI(title="RecoverFlow AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================== DATA MODELS ========================

class FailureBucket(str, Enum):
    SOFT = "soft"
    HARD = "hard"
    CUSTOMER_ACTION = "customer_action"
    CHECKOUT_DROPOFF = "checkout_dropoff"

class RecoveryStatus(str, Enum):
    PENDING = "pending"
    RETRYING = "retrying"
    RECOVERED = "recovered"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"

class AuditEntry(BaseModel):
    timestamp: datetime
    action: str
    result: str  # "success", "fail", "info", "warn"
    cost_inr: float = 0.0

class Transaction(BaseModel):
    id: str
    amount: int
    currency: str = "INR"
    reason: str
    bucket: FailureBucket = FailureBucket.CUSTOMER_ACTION
    status: RecoveryStatus = RecoveryStatus.PENDING
    potential: int = 0
    strategy: str = "Pending AI scoring..."
    method: str
    ltv: int = 0
    history: float = 0.0
    customer_id: str = ""
    merchant_id: str = "merchant_default"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    audit: List[AuditEntry] = []
    attempts_made: int = 0
    cost_accrued: float = 0.0

class MerchantConfig(BaseModel):
    merchant_id: str = "merchant_default"
    max_retries: int = 3
    max_cost_per_recovery: float = 50.0
    dnd_start_hour: int = 22
    dnd_end_hour: int = 8
    min_recovery_score: int = 20
    auto_retry_soft: bool = True
    channels_enabled: Dict[str, bool] = {
        "smart_retry": True,
        "sms": True,
        "whatsapp": True,
        "email": True,
        "voice_call": True,
        "payment_link": True,
    }

class RecoveryResult(BaseModel):
    txn_id: str
    status: RecoveryStatus
    amount_recovered: int
    attempts_used: int
    total_cost: float
    audit: List[AuditEntry]
    time_taken_seconds: float

class DashboardMetrics(BaseModel):
    revenue_at_risk: float
    money_recovered: float
    recovery_rate: float
    avg_recovery_time_hours: float
    active_cases: int
    recovered_cases: int
    failed_cases: int

# ======================== IN-MEMORY STORE ========================

transactions_db: Dict[str, Transaction] = {}
merchant_configs: Dict[str, MerchantConfig] = {
    "merchant_default": MerchantConfig()
}

# ======================== AI SCORING ENGINE ========================

FAILURE_BUCKETS = {
    "soft": ["bank_timeout", "gateway_error", "network_error", "do_not_honor", "subscription_mandate_fail"],
    "hard": ["invalid_card", "expired_card", "cancelled_mandate", "fraud_block", "stolen_card"],
    "customer_action": ["insufficient_funds", "incorrect_otp", "incorrect_cvv", "upi_declined"],
    "checkout_dropoff": ["checkout_abandoned", "payment_page_exit"],
}

def classify_failure(error_code: str, description: str = "") -> FailureBucket:
    error_lower = error_code.lower().replace(" ", "_")
    for bucket, codes in FAILURE_BUCKETS.items():
        if any(code in error_lower for code in codes):
            return FailureBucket(bucket)
    return FailureBucket.CUSTOMER_ACTION

def score_recovery_potential(txn: Transaction) -> Dict[str, Any]:
    """
    Rule-based scoring model v1.
    In production, replace with XGBoost model trained on historical recovery data.
    """
    base_score = 50
    breakdown = {"base": base_score}

    # Amount factor
    if txn.amount > 10000:
        amount_bonus = 15
    elif txn.amount > 5000:
        amount_bonus = 10
    else:
        amount_bonus = 0
    base_score += amount_bonus
    breakdown["amount"] = amount_bonus

    # Customer LTV
    if txn.ltv > 50000:
        ltv_bonus = 10
    elif txn.ltv > 20000:
        ltv_bonus = 5
    else:
        ltv_bonus = 0
    base_score += ltv_bonus
    breakdown["ltv"] = ltv_bonus

    # Recovery history
    if txn.history > 0.7:
        history_bonus = 20
    elif txn.history > 0.4:
        history_bonus = 10
    else:
        history_bonus = 0
    base_score += history_bonus
    breakdown["history"] = history_bonus

    # Failure bucket
    if txn.bucket == FailureBucket.SOFT:
        bucket_bonus = 20
    elif txn.bucket == FailureBucket.CUSTOMER_ACTION:
        bucket_bonus = 5
    elif txn.bucket == FailureBucket.CHECKOUT_DROPOFF:
        bucket_bonus = 10
    else:
        bucket_bonus = -30
    base_score += bucket_bonus
    breakdown["bucket"] = bucket_bonus

    # Payment method
    if txn.method.lower() in ["upi", "netbanking"]:
        method_bonus = 5
    else:
        method_bonus = 0
    base_score += method_bonus
    breakdown["method"] = method_bonus

    final_score = max(0, min(100, base_score))

    return {
        "score": final_score,
        "breakdown": breakdown,
        "optimal_retry_time": predict_optimal_retry_time(txn),
    }

def predict_optimal_retry_time(txn: Transaction) -> datetime:
    """Predict best time to retry based on customer patterns."""
    now = datetime.utcnow()
    # Simple heuristic: retry during business hours (10 AM - 6 PM IST)
    if now.hour < 4 or now.hour > 12:  # UTC -> IST offset
        return now + timedelta(hours=(10 - (now.hour + 5) % 24) % 24)
    return now + timedelta(minutes=5)

# ======================== STRATEGY ROUTER ========================

def select_strategy(score: int, bucket: FailureBucket, method: str, config: MerchantConfig) -> Dict[str, Any]:
    """Select optimal recovery strategy based on score and context."""

    if score < config.min_recovery_score:
        return {"action": "manual_review", "max_attempts": 0, "timing": "N/A", "channels": []}

    if bucket == FailureBucket.SOFT and score > 70 and config.auto_retry_soft:
        return {
            "action": "smart_retry",
            "max_attempts": min(2, config.max_retries),
            "timing": "immediate",
            "channels": ["smart_retry"],
            "cost_per_attempt": 2.5,
        }

    if bucket == FailureBucket.CUSTOMER_ACTION and score > 50:
        channels = []
        if config.channels_enabled.get("sms"): channels.append("sms")
        if config.channels_enabled.get("whatsapp"): channels.append("whatsapp")
        if config.channels_enabled.get("payment_link"): channels.append("payment_link")
        return {
            "action": "delayed_retry_with_nudge",
            "max_attempts": min(3, config.max_retries),
            "timing": "predicted_payday",
            "channels": channels,
            "cost_per_attempt": 0.35,
        }

    if bucket == FailureBucket.HARD and score > 30:
        channels = []
        if config.channels_enabled.get("email"): channels.append("email")
        if config.channels_enabled.get("payment_link"): channels.append("payment_link")
        if config.channels_enabled.get("voice_call"): channels.append("voice_call")
        return {
            "action": "dunning_sequence",
            "max_attempts": min(1 + len(channels), config.max_retries),
            "timing": "T+1_T+3_T+7",
            "channels": channels,
            "cost_per_attempt": 4.0,
        }

    if bucket == FailureBucket.CHECKOUT_DROPOFF and score > 40:
        channels = []
        if config.channels_enabled.get("whatsapp"): channels.append("whatsapp")
        if config.channels_enabled.get("email"): channels.append("email")
        return {
            "action": "abandoned_cart_recovery",
            "max_attempts": min(2, config.max_retries),
            "timing": "30min_24h",
            "channels": channels,
            "cost_per_attempt": 0.35,
        }

    return {
        "action": "manual_review",
        "max_attempts": 0,
        "timing": "N/A",
        "channels": [],
    }

# ======================== BOUNDED EXECUTOR ========================

async def execute_recovery(txn: Transaction, strategy: Dict[str, Any], config: MerchantConfig) -> RecoveryResult:
    """
    Execute recovery within merchant-defined bounds.
    Returns full audit trail and result.
    """
    start_time = datetime.utcnow()
    attempts = 0
    cost_accrued = 0.0
    audit = list(txn.audit)

    max_attempts = strategy["max_attempts"]

    while attempts < max_attempts and cost_accrued < config.max_cost_per_recovery:
        # Check DND
        current_hour = (datetime.utcnow().hour + 5) % 24  # IST
        if config.dnd_start_hour <= current_hour or current_hour < config.dnd_end_hour:
            audit.append(AuditEntry(
                timestamp=datetime.utcnow(),
                action=f"DND active ({config.dnd_start_hour}:00-{config.dnd_end_hour}:00 IST). Scheduling for next window.",
                result="warn",
                cost_inr=0.0,
            ))
            break

        attempts += 1
        action_name = strategy["action"]
        channel = strategy["channels"][min(attempts - 1, len(strategy["channels"]) - 1)] if strategy["channels"] else "smart_retry"

        # Simulate execution
        await asyncio.sleep(0.5)  # Simulate API call latency

        cost = strategy.get("cost_per_attempt", 2.5)
        cost_accrued += cost

        # Simulate recovery outcome (65% success rate for demo)
        recovered = random.random() > 0.35

        if recovered:
            audit.append(AuditEntry(
                timestamp=datetime.utcnow(),
                action=f"Attempt #{attempts}: {action_name} via {channel} — ₹{txn.amount} recovered",
                result="success",
                cost_inr=cost,
            ))
            time_taken = (datetime.utcnow() - start_time).total_seconds()
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
                timestamp=datetime.utcnow(),
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
            timestamp=datetime.utcnow(),
            action=f"Stopped: cost limit ₹{config.max_cost_per_recovery} exceeded (spent ₹{cost_accrued:.2f})",
            result="warn",
            cost_inr=0.0,
        ))
    else:
        audit.append(AuditEntry(
            timestamp=datetime.utcnow(),
            action=f"Max attempts ({max_attempts}) exhausted. Marked as failed.",
            result="fail",
            cost_inr=0.0,
        ))

    time_taken = (datetime.utcnow() - start_time).total_seconds()
    return RecoveryResult(
        txn_id=txn.id,
        status=RecoveryStatus.FAILED,
        amount_recovered=0,
        attempts_used=attempts,
        total_cost=cost_accrued,
        audit=audit,
        time_taken_seconds=time_taken,
    )

# ======================== API ENDPOINTS ========================

@app.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive Razorpay webhooks for payment failures.
    In production, verify webhook signature using Razorpay secret.
    """
    payload = await request.json()
    event = payload.get("event", "")

    if event not in ["payment.failed", "subscription.pending", "invoice.failed"]:
        return {"status": "ignored", "event": event}

    # Extract payment data
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})

    txn = Transaction(
        id=payment.get("id", f"pay_{random.randint(100000, 999999)}"),
        amount=payment.get("amount", 0) // 100,  # Razorpay sends paise
        reason=payment.get("error_description", "Unknown"),
        method=payment.get("method", "unknown"),
        customer_id=payment.get("customer_id", ""),
        merchant_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {}).get("merchant_id", "merchant_default"),
    )

    # Classify and score
    txn.bucket = classify_failure(payment.get("error_code", ""), txn.reason)

    # Mock customer data (in production, fetch from CRM/DB)
    txn.ltv = random.randint(5000, 200000)
    txn.history = round(random.random(), 2)

    score_result = score_recovery_potential(txn)
    txn.potential = score_result["score"]

    # Select strategy
    config = merchant_configs.get(txn.merchant_id, MerchantConfig())
    strategy = select_strategy(txn.potential, txn.bucket, txn.method, config)
    txn.strategy = strategy["action"]

    # Initial audit
    txn.audit = [
        AuditEntry(
            timestamp=datetime.utcnow(),
            action=f"Webhook received: {event} — {txn.reason}",
            result="fail",
        ),
        AuditEntry(
            timestamp=datetime.utcnow(),
            action=f"Classified as: {txn.bucket.value} | Scored: {txn.potential}%",
            result="info",
        ),
        AuditEntry(
            timestamp=datetime.utcnow(),
            action=f"Selected strategy: {txn.strategy}",
            result="info",
        ),
    ]

    # Check if below minimum score
    if txn.potential < config.min_recovery_score:
        txn.status = RecoveryStatus.MANUAL_REVIEW
        txn.audit.append(AuditEntry(
            timestamp=datetime.utcnow(),
            action=f"Score {txn.potential}% below threshold {config.min_recovery_score}%. Routed to manual review.",
            result="warn",
        ))
        transactions_db[txn.id] = txn
        return {"status": "manual_review", "txn_id": txn.id, "score": txn.potential}

    txn.status = RecoveryStatus.RETRYING
    transactions_db[txn.id] = txn

    # Execute recovery in background
    background_tasks.add_task(process_recovery, txn.id, strategy, config)

    return {
        "status": "processing",
        "txn_id": txn.id,
        "score": txn.potential,
        "strategy": txn.strategy,
    }

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

@app.post("/transactions/simulate")
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

    txn.audit = [
        AuditEntry(timestamp=datetime.utcnow(), action=f"Simulated failure: {reason}", result="info"),
        AuditEntry(timestamp=datetime.utcnow(), action=f"Scored: {txn.potential}%", result="info"),
        AuditEntry(timestamp=datetime.utcnow(), action=f"Strategy: {txn.strategy}", result="info"),
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
        txn.audit.append(AuditEntry(timestamp=datetime.utcnow(), action=f"₹{txn.amount} recovered successfully", result="success"))
    elif txn.status == RecoveryStatus.FAILED:
        txn.audit.append(AuditEntry(timestamp=datetime.utcnow(), action="Max retries exhausted", result="fail"))

    transactions_db[txn.id] = txn
    
    # Auto-resolve pending/retrying cases after a few seconds so revenue at risk doesn't climb infinitely
    if txn.status in [RecoveryStatus.PENDING, RecoveryStatus.RETRYING]:
        background_tasks.add_task(auto_resolve_mock, txn.id)
        
    return {"status": txn.status.value, "txn_id": txn.id, "amount": txn.amount}

async def auto_resolve_mock(txn_id: str):
    """Simulates the AI resolving the case in the background after some time."""
    await asyncio.sleep(12)  # Wait 12 seconds
    txn = transactions_db.get(txn_id)
    if txn and txn.status in [RecoveryStatus.PENDING, RecoveryStatus.RETRYING]:
        # Log the attempt method based on the strategy
        config = merchant_configs.get(txn.merchant_id, MerchantConfig())
        strategy = select_strategy(txn.potential, txn.bucket, txn.method, config)
        channels = strategy.get("channels", [])
        channel_name = channels[0] if channels else "system_retry"
        
        txn.audit.append(AuditEntry(
            timestamp=datetime.utcnow(), 
            action=f"Attempt #1: {channel_name.replace('_', ' ').title()} sent", 
            result="info"
        ))
        
        # Simulate the outcome
        txn.status = random.choices([RecoveryStatus.RECOVERED, RecoveryStatus.FAILED], weights=[85, 15])[0]
        result_str = "success" if txn.status == RecoveryStatus.RECOVERED else "fail"
        action_str = f"₹{txn.amount} recovered successfully (Auto)" if txn.status == RecoveryStatus.RECOVERED else "Max retries exhausted (Auto)"
        
        # Add outcome to audit 1 second later to show sequence
        txn.audit.append(AuditEntry(timestamp=datetime.utcnow() + timedelta(seconds=1), action=action_str, result=result_str))

@app.post("/transactions/{txn_id}/recover")
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

@app.get("/transactions")
async def list_transactions(status: Optional[str] = None, limit: int = 50):
    """List all transactions with optional filtering."""
    txns = list(transactions_db.values())
    if status:
        txns = [t for t in txns if t.status.value == status]
    txns = sorted(txns, key=lambda x: x.created_at, reverse=True)[:limit]
    return txns

@app.get("/transactions/{txn_id}")
async def get_transaction(txn_id: str):
    """Get detailed transaction with audit trail."""
    txn = transactions_db.get(txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn

@app.get("/metrics")
async def get_metrics() -> DashboardMetrics:
    """Get dashboard metrics."""
    txns = list(transactions_db.values())
    recovered = [t for t in txns if t.status == RecoveryStatus.RECOVERED]
    failed = [t for t in txns if t.status == RecoveryStatus.FAILED]
    active = [t for t in txns if t.status in [RecoveryStatus.PENDING, RecoveryStatus.RETRYING, RecoveryStatus.MANUAL_REVIEW]]

    total_risk = sum(t.amount for t in active)
    total_recovered = sum(t.amount for t in recovered)
    total_failed_resolved = sum(t.amount for t in failed)
    
    total_resolved = total_recovered + total_failed_resolved
    rate = (total_recovered / total_resolved * 100) if total_resolved > 0 else 0

    total_time = 0.0
    for t in recovered:
        strategy = t.strategy.lower()
        if any(x in strategy for x in ['immediate', 'alt-gateway', 'smart']):
            total_time += 0.1
        elif any(x in strategy for x in ['abandoned', 'cart']):
            total_time += 2.0
        elif any(x in strategy for x in ['delayed', 'nudge', 'sms']):
            total_time += 12.0
        elif any(x in strategy for x in ['dunning', 'email', 'card update']):
            total_time += 48.0
        else:
            total_time += 4.2
            
    avg_time = round(total_time / len(recovered), 1) if recovered else 0.0

    return DashboardMetrics(
        revenue_at_risk=total_risk,
        money_recovered=total_recovered,
        recovery_rate=round(rate, 1),
        avg_recovery_time_hours=avg_time,
        active_cases=len(active),
        recovered_cases=len(recovered),
        failed_cases=len(failed),
    )

@app.get("/strategies/breakdown")
async def get_strategy_breakdown():
    """Get recovery breakdown by strategy."""
    txns = [t for t in transactions_db.values() if t.status == RecoveryStatus.RECOVERED]
    breakdown = {}
    for t in txns:
        breakdown[t.strategy] = breakdown.get(t.strategy, 0) + t.amount
    total = sum(breakdown.values()) or 1
    return {k: round(v / total * 100, 1) for k, v in breakdown.items()}

@app.put("/merchants/{merchant_id}/config")
async def update_merchant_config(merchant_id: str, config: MerchantConfig):
    """Update merchant recovery configuration."""
    config.merchant_id = merchant_id
    merchant_configs[merchant_id] = config
    return config

@app.get("/merchants/{merchant_id}/config")
async def get_merchant_config(merchant_id: str):
    """Get merchant recovery configuration."""
    return merchant_configs.get(merchant_id, MerchantConfig(merchant_id=merchant_id))

# ======================== HEALTH CHECK ========================

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "RecoverFlow AI", "version": "1.0.0"}

# ======================== SEED DATA ========================

@app.on_event("startup")
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
            AuditEntry(timestamp=datetime.utcnow(), action=f"Payment failed — {data['reason']}", result="fail"),
            AuditEntry(timestamp=datetime.utcnow(), action=f"Scored recovery potential: {txn.potential}%", result="info"),
            AuditEntry(timestamp=datetime.utcnow(), action=f"Selected strategy: {txn.strategy}", result="info"),
        ]

        if txn.status == RecoveryStatus.RECOVERED:
            txn.audit.append(AuditEntry(timestamp=datetime.utcnow(), action=f"₹{txn.amount} recovered successfully", result="success"))
        elif txn.status == RecoveryStatus.FAILED:
            txn.audit.append(AuditEntry(timestamp=datetime.utcnow(), action="Max retries exhausted", result="fail"))

        transactions_db[txn.id] = txn

    print(f"[SEED] Loaded {len(demo_txns)} demo transactions")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)