"""
Strategy Router — selects the optimal recovery strategy given a score,
failure bucket, payment method, and merchant configuration.
"""

from typing import Any, Dict

from models import FailureBucket, MerchantConfig


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
