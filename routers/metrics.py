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


import os
import time

# Cache for AI insights
ai_insights_cache = {
    "timestamp": 0,
    "insights": {
        "risk_insight": "↓ 8% vs last week",
        "recovered_insight": "↑ 12% vs last week",
        "rate_insight": "↑ 3.2pp vs last week",
        "time_insight": "↓ 1.1h faster"
    }
}

@router.get("/metrics")
async def get_metrics() -> DashboardMetrics:
    """Get dashboard metrics."""
    txns = list(transactions_db.values())
    recovered = [t for t in txns if t.status == RecoveryStatus.RECOVERED]
    failed = [t for t in txns if t.status == RecoveryStatus.FAILED]
    active = [t for t in txns if t.status in [RecoveryStatus.PENDING, RecoveryStatus.RETRYING, RecoveryStatus.MANUAL_REVIEW, RecoveryStatus.PROMISE_TO_PAY]]

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

    # AI Insight Generation (cached for 5 minutes)
    current_time = time.time()
    if current_time - ai_insights_cache["timestamp"] > 300:
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and total_resolved > 0:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                prompt = f"""You are analyzing a payment recovery dashboard.
Current Metrics:
- Revenue at Risk: ₹{total_risk}
- Money Recovered: ₹{total_recovered}
- Recovery Rate: {rate:.1f}%
- Avg Recovery Time: {avg_time}h

Generate exactly 4 short sub-metric insights, one per line, starting with either an '↑' or '↓' arrow, simulating a comparison to historical data or explaining a trend.
Format:
Line 1 (Risk Insight): ↓ Risk is down...
Line 2 (Recovered Insight): ↑ Recovered...
Line 3 (Rate Insight): ↑ Rate is up...
Line 4 (Time Insight): ↓ Time is faster...
Do not include line labels like 'Line 1:', just the 4 lines."""
                response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                lines = [l.strip() for l in response.text.strip().split('\n') if l.strip()]
                if len(lines) >= 4:
                    ai_insights_cache["insights"] = {
                        "risk_insight": lines[0].replace("Line 1 (Risk Insight): ", "").replace("Line 1: ", ""),
                        "recovered_insight": lines[1].replace("Line 2 (Recovered Insight): ", "").replace("Line 2: ", ""),
                        "rate_insight": lines[2].replace("Line 3 (Rate Insight): ", "").replace("Line 3: ", ""),
                        "time_insight": lines[3].replace("Line 4 (Time Insight): ", "").replace("Line 4: ", "")
                    }
            except Exception as e:
                print(f"[AI INSIGHTS ERROR] {e}")
            finally:
                # Update timestamp even if it fails so we don't spam the API on the next request
                ai_insights_cache["timestamp"] = current_time

    return DashboardMetrics(
        revenue_at_risk=total_risk,
        money_recovered=total_recovered,
        recovery_rate=round(rate, 1),
        avg_recovery_time_hours=avg_time,
        active_cases=len(active),
        recovered_cases=len(recovered),
        failed_cases=len(failed),
        **ai_insights_cache["insights"]
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
