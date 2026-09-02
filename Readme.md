# RecoverFlow AI

Context-aware revenue recovery engine for Razorpay Buildathon 2026

RecoverFlow AI detects revenue at risk from payment failures, scores recovery potential using an ML model trained on customer context and failure type, selects the optimal intervention strategy, and executes bounded recovery — all with full audit trails and merchant-configurable stopping rules.

---

## 🚀 Live Demo

| | Link |
|---|---|
| **Frontend (Dashboard)** | [recover-flow-zeta.vercel.app/dashboard.html](https://recover-flow-zeta.vercel.app/dashboard.html) |
| **Backend (API)** | [recoverflow-backened.onrender.com](https://recoverflow-backened.onrender.com) |

> ⚠️ **Note:** The backend is hosted on Render's free tier, which spins down after periods of inactivity. The first request after idle time may take 30–50 seconds to respond while the instance cold-starts — subsequent requests are fast. If you're demoing live, hit the `/health` endpoint a minute beforehand to warm it up.

---

## What It Does

| Step | What Happens |
|---|---|
| **Detect** | Receives Razorpay webhooks (`payment.failed`, `subscription.pending`, `invoice.failed`) |
| **Classify** | Categorizes failure into soft / hard / customer-action / checkout-dropoff |
| **Score** | ML model (Random Forest) scores recovery probability (0–100) using amount, LTV, history, method, time |
| **Route** | Selects strategy: smart retry, SMS, WhatsApp, email dunning, Hinglish voice call |
| **Execute** | Runs recovery within merchant bounds (max retries, max cost, DND hours) |
| **Measure** | Tracks exact ₹ recovered, attempts used, cost per recovery, audit trail |

---

## Files

| File | Purpose |
|---|---|
| `recoverflow_ai_dashboard.html` | Frontend dashboard — deployed on Vercel |
| `recoverflow_ai_backend.py` | FastAPI backend with webhook handler, ML engine, strategy router, executor — deployed on Render |
| `requirements.txt` | Python dependencies |

---

## Quick Start (Use the Live Deployment)

Just open the dashboard — it's already wired to the live backend:

👉 **https://recover-flow-zeta.vercel.app/dashboard.html**

No setup needed. Use the **Live Simulator** tab to trigger a full detect → score → route → recover cycle in real time.

---

## Quick Start (Run Locally)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the backend
```bash
python recoverflow_ai_backend.py
# or
uvicorn recoverflow_ai_backend:app --reload --port 8000
```

### 3. Open the frontend
Open `recoverflow_ai_dashboard.html` in your browser. By default it points to the deployed backend — update the API base URL in the file if you want it to hit `http://localhost:8000` instead.

### 4. Test the webhook
```bash
curl -X POST http://localhost:8000/webhooks/razorpay \
  -H "Content-Type: application/json" \
  -d '{
    "event": "payment.failed",
    "payload": {
      "payment": {
        "entity": {
          "id": "pay_test_001",
          "amount": 249900,
          "method": "upi",
          "error_code": "insufficient_funds",
          "error_description": "Insufficient funds",
          "customer_id": "cust_123"
        }
      }
    }
  }'
```

### 5. Check metrics
```bash
curl http://localhost:8000/metrics
curl http://localhost:8000/transactions
```

You can run the same checks against the live backend by swapping `localhost:8000` for `recoverflow-backened.onrender.com`.

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/webhooks/razorpay` | POST | Receive Razorpay payment failure webhooks |
| `/webhooks/inbound-message` | POST | Receive inbound customer SMS/chat replies for NLP parsing |
| `/transactions` | GET | List all transactions |
| `/transactions/{id}` | GET | Get transaction details + audit trail |
| `/transactions/{id}/recover` | POST | Manually trigger recovery |
| `/transactions/simulate` | POST | Simulate a failure for demo |
| `/metrics` | GET | Dashboard metrics |
| `/strategies/breakdown` | GET | Recovery breakdown by strategy |
| `/merchants/{id}/config` | GET/PUT | Merchant recovery rules |
| `/health` | GET | Health check (also useful for warming the Render free-tier instance) |

---

## Architecture

```
Razorpay Webhook
       │
       ▼
┌─────────────────┐
│  Webhook Handler │  ← Verify signature, parse payload
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Failure Classifier│ ← Map error_code → soft/hard/customer/checkout
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Recovery Scorer  │ ← Random Forest classifier (trained model)
│  (0–100 score)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Strategy Router  │ ← Select optimal intervention
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Bounded Executor │ ← Execute within merchant rules
│  (retry limits,  │    max cost, DND hours, audit)
│   cost tracking) │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
Recovered   Failed
    │         │
    ▼         ▼
Audit Trail  Audit Trail
```

---

## Scoring Model — Random Forest

The recovery scorer is a **`scikit-learn RandomForestClassifier`** (100 decision trees), trained on **10,000 synthetic historical transaction records**, predicting the probability of successful recovery. Cross-validation accuracy is **~79%**.

**Feature importances (Gini):**

| Feature | Importance |
|---|---|
| Failure bucket (soft / hard / customer) | 41.2% |
| Customer recovery history | 27.8% |
| Transaction amount | 14.5% |
| Customer lifetime value (LTV) | 11.3% |
| Payment method reliability | 5.2% |

## Strategy Matrix

| Failure Bucket | ML Recovery Prob. | Strategy | Max Attempts | Timing |
|---|---|---|---|---|
| Soft decline | > 70% | Alt-gateway retry | 2 | Now + 5 min |
| Customer action | 40–70% | Delayed retry + SMS/WhatsApp | 3 | Predicted payday |
| Hard decline | 20–40% | Card update → dunning sequence | 1 + 2 nudges | T+1, T+3, T+7 |
| Fraud / blocked | < 20% | Skip — manual review only | 0 | N/A |
| Checkout drop-off | 50–80% | Abandoned cart WhatsApp | 2 | 30 min + 24h |

---

## ✨ Key Innovation: Hybrid AI Promise-to-Pay (P2P) Engine

RecoverFlow AI features an intelligent inbound webhook to handle customer SMS/chat replies. Instead of blindly trusting AI or relying entirely on human agents, it uses a **Hybrid Human-in-the-Loop Model** powered by **Google Gemini**:

- **Confidence Scoring**: Extracts the promised date, confidence level, and reasoning directly from natural language (e.g., *"Salary comes on the 5th"*).
- **Automated Pausing**: If the AI is highly confident, it extracts the date, sets the status to `PROMISE_TO_PAY`, and automatically pauses dunning.
- **Enterprise Risk Management**: If the transaction is high-value (>₹50,000), or if the message is vague/complex (low confidence), it routes the transaction to a **Manual Review Queue**. The AI attaches its reasoning to the audit log to assist the human agent in making the final call.

---

## Merchant Configuration

Merchants can configure:
- Max retry attempts (1–10)
- Max cost per recovery (₹5–₹200)
- Do-not-disturb hours (no calls/SMS during these hours)
- Minimum recovery score (transactions below this go to manual review)
- Auto-retry soft declines (immediate alt-gateway retry)
- Channel enablement and per-channel cost/usage caps: smart retry (₹2.5, 2 uses), SMS (₹0.15, 3 uses), WhatsApp (₹0.35, 2 uses), email (₹0.05, 3 uses), Hinglish voice call (₹4.0, 1 use), payment link (₹0.10, 2 uses)

---

## Next Steps for Production

1. Add Razorpay webhook signature verification using `razorpay_secret`
2. Retrain the Random Forest model on real historical Razorpay recovery data (currently trained on synthetic data)
3. Integrate Razorpay Payment Links API for recovery link generation
4. Add Twilio/Exotel for Hinglish voice calls
5. Add WhatsApp Business API for recovery nudges
6. Add Redis for retry job queues
7. Add A/B testing framework for strategy efficacy comparison
8. Move backend off Render's free tier (or add a keep-alive ping) to eliminate cold-start latency

---

## Team

Built for Razorpay Buildathon 2026 — Track 03: AI Revenue Recovery
