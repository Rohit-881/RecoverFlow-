"""
Metrics routes — dashboard-level numbers and per-strategy breakdown.

Note: the original file defined `/metrics` twice. This keeps the first,
more complete implementation (dynamic avg_recovery_time_hours computed
from strategy type, and revenue_at_risk that only counts still-active
cases). The second definition — flat 2.5h average, and revenue_at_risk
that double-counted failed transactions as "at risk" — was dropped.
"""

from fastapi import APIRouter

from models import DashboardMetrics, RecoveryStatus
from store import transactions_db

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
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


@router.get("/strategies/breakdown")
async def get_strategy_breakdown():
    """Get recovery breakdown by strategy."""
    txns = [t for t in transactions_db.values() if t.status == RecoveryStatus.RECOVERED]
    breakdown = {}
    for t in txns:
        breakdown[t.strategy] = breakdown.get(t.strategy, 0) + t.amount
    total = sum(breakdown.values()) or 1
    return {k: round(v / total * 100, 1) for k, v in breakdown.items()}
