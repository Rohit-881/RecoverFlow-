"""
AI Scoring Engine — failure classification, recovery-potential scoring,
and optimal retry-time prediction.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from models import Transaction, FailureBucket

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
    now = datetime.now(timezone.utc)
    # Simple heuristic: retry during business hours (10 AM - 6 PM IST)
    if now.hour < 4 or now.hour > 12:  # UTC -> IST offset
        return now + timedelta(hours=(10 - (now.hour + 5) % 24) % 24)
    return now + timedelta(minutes=5)
