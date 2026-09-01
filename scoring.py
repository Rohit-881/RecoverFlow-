"""
AI Scoring Engine — failure classification, recovery-potential scoring,
and optimal retry-time prediction.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import os
import joblib
import pandas as pd

from models import Transaction, FailureBucket

FAILURE_BUCKETS = {
    "soft": ["bank_timeout", "gateway_error", "network_error", "do_not_honor", "subscription_mandate_fail"],
    "hard": ["invalid_card", "expired_card", "cancelled_mandate", "fraud_block", "stolen_card"],
    "customer_action": ["insufficient_funds", "incorrect_otp", "incorrect_cvv", "upi_declined"],
    "checkout_dropoff": ["checkout_abandoned", "payment_page_exit"],
    "subscription_failed": ["subscription_mandate_fail"],
    "b2b_overdue": ["invoice_expired"],
}

# Load the machine learning model once on startup
model_path = os.path.join(os.path.dirname(__file__), 'recovery_model.pkl')
try:
    rf_model = joblib.load(model_path)
except Exception as e:
    print(f"Warning: Could not load ML model: {e}")
    rf_model = None

def classify_failure(error_code: str, description: str = "") -> FailureBucket:
    error_lower = error_code.lower().replace(" ", "_")
    for bucket, codes in FAILURE_BUCKETS.items():
        if any(code in error_lower for code in codes):
            return FailureBucket(bucket)
    return FailureBucket.CUSTOMER_ACTION

def predict_optimal_retry_time(txn: Transaction) -> datetime:
    """Predict best time to retry based on customer patterns."""
    now = datetime.now(timezone.utc)
    # Simple heuristic: retry during business hours (10 AM - 6 PM IST)
    if now.hour < 4 or now.hour > 12:  # UTC -> IST offset
        return now + timedelta(hours=(10 - (now.hour + 5) % 24) % 24)
    return now + timedelta(minutes=5)

def score_recovery_potential(txn: Transaction) -> Dict[str, Any]:
    """
    Score the probability of successful recovery using the trained ML model.
    """
    if rf_model is None:
        return {
            "score": 50, 
            "confidence": "low (fallback)",
            "optimal_retry_time": predict_optimal_retry_time(txn)
        }
        
    # Map method to integer (matching train_model.py logic)
    method_mapping = {'UPI': 0, 'Credit Card': 1, 'Debit Card': 2, 'eNACH': 3}
    method_val = method_mapping.get(txn.method, 4)
    
    # Map bucket to integer
    bucket_mapping = {
        FailureBucket.SOFT: 0, 
        FailureBucket.CUSTOMER_ACTION: 1, 
        FailureBucket.CHECKOUT_DROPOFF: 2, 
        FailureBucket.HARD: 3,
        FailureBucket.SUBSCRIPTION_FAILED: 4,
        FailureBucket.B2B_OVERDUE: 5
    }
    bucket_val = bucket_mapping.get(txn.bucket, 3)
    
    # Create feature dataframe
    features = pd.DataFrame([{
        'amount': txn.amount,
        'ltv': txn.ltv,
        'history': txn.history,
        'bucket': bucket_val,
        'method': method_val
    }])
    
    # Predict probability of class 1 (recovered)
    try:
        prob = rf_model.predict_proba(features)[0][1]
        score = int(prob * 100)
    except Exception as e:
        print(f"Prediction error: {e}")
        score = 50
        
    return {
        "score": score,
        "confidence": "high (ML model)",
        "optimal_retry_time": predict_optimal_retry_time(txn)
    }
