"""
Data models — Enums and Pydantic schemas shared across the app.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum


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
    WAITING_FOR_CUSTOMER = "waiting_for_customer"


class AuditEntry(BaseModel):
    timestamp: datetime
    action: str
    result: str  # "success", "fail", "info", "warn"
    cost_inr: float = 0.0
    strategy: Optional[str] = None
    link_url: Optional[str] = None
    llm_message: Optional[str] = None


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
    payment_link_id: Optional[str] = None
    payment_link_url: Optional[str] = None


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
