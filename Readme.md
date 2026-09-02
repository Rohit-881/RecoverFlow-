RecoverFlow AI
Context-aware revenue recovery engine for Razorpay Buildathon 2026
RecoverFlow AI detects revenue at risk from payment failures, scores recovery potential using customer context and failure type, selects the optimal intervention strategy, and executes bounded recovery — all with full audit trails and merchant-configurable stopping rules.
________________________________________
What It Does
Step	What Happens
Detect	Receives Razorpay webhooks (payment.failed, subscription.pending, invoice.failed)
Classify	Categorizes failure into soft / hard / customer-action / checkout-dropoff
Score	ML model scores recovery potential (0–100) using amount, LTV, history, method, time
Route	Selects strategy: smart retry, SMS, WhatsApp, email dunning, Hinglish voice call
Execute	Runs recovery within merchant bounds (max retries, max cost, DND hours)
Measure	Tracks exact ₹ recovered, attempts used, cost per recovery, audit trail
________________________________________
Files
File	Purpose
recoverflow_ai_dashboard.html	Standalone frontend dashboard — open in browser and demo immediately
recoverflow_ai_backend.py	FastAPI backend with webhook handler, AI engine, strategy router, executor
requirements.txt	Python dependencies
________________________________________
Quick Start (Frontend Only)
# Just open the HTML file in your browser
open recoverflow_ai_dashboard.html
The dashboard is fully self-contained with: - Live metrics (revenue at risk, money recovered, recovery rate) - Transaction table with filtering - AI scoring breakdown per transaction - Audit trail timeline - Live simulation mode - Merchant configuration panel
________________________________________
Quick Start (Full Stack)
1. Install dependencies
pip install -r requirements.txt
2. Run the backend
python recoverflow_ai_backend.py
# or
uvicorn recoverflow_ai_backend:app --reload --port 8000
3. Open the frontend
Open recoverflow_ai_dashboard.html in your browser. In production, wire the frontend to http://localhost:8000.
4. Test the webhook
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
5. Check metrics
curl http://localhost:8000/metrics
curl http://localhost:8000/transactions
________________________________________
API Endpoints
Endpoint	Method	Description
/webhooks/razorpay	POST	Receive Razorpay payment failure webhooks
/webhooks/inbound-message	POST	Receive inbound customer SMS/chat replies for NLP parsing
/transactions	GET	List all transactions
/transactions/{id}	GET	Get transaction details + audit trail
/transactions/{id}/recover	POST	Manually trigger recovery
/transactions/simulate	POST	Simulate a failure for demo
/metrics	GET	Dashboard metrics
/strategies/breakdown	GET	Recovery breakdown by strategy
/merchants/{id}/config	GET/PUT	Merchant recovery rules
/health	GET	Health check
________________________________________
Architecture
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
│ Recovery Scorer  │ ← XGBoost model (rule-based v1)
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
________________________________________
Scoring Model (v1)
Base score: 50
+ Amount bonus:     +15 (>₹10K) / +10 (>₹5K) / 0
+ LTV bonus:        +10 (>₹50K) / +5 (>₹20K) / 0
+ History bonus:    +20 (>70%) / +10 (>40%) / 0
+ Bucket bonus:     +20 (soft) / +5 (customer) / +10 (checkout) / -30 (hard)
+ Method bonus:     +5 (UPI/Netbanking) / 0
─────────────────────────────────────────
Final score: 0–100
Strategy Matrix
Failure Bucket	Score	Strategy	Max Attempts	Timing
Soft decline	70–100	Alt-gateway retry	2	Immediate
Customer action	40–70	Delayed retry + SMS/WA	3	Predicted payday
Hard decline	20–40	Card update → dunning	1 + 2 nudges	T+1, T+3, T+7
Fraud/blocked	0–20	Skip — manual review	0	N/A
Checkout drop-off	50–80	Abandoned cart WA	2	30 min + 24h
________________________________________

## ✨ Key Innovation: Hybrid AI Promise-to-Pay (P2P) Engine
RecoverFlow AI features an intelligent inbound webhook to handle customer SMS/chat replies. Instead of blindly trusting AI or relying entirely on human agents, it uses a **Hybrid Human-in-the-Loop Model** powered by **Google Gemini**:
- **Confidence Scoring**: Extracts the promised date, confidence level, and reasoning directly from natural language (e.g., *"Salary comes on the 5th"*).
- **Automated Pausing**: If the AI is highly confident, it extracts the date, sets the status to `PROMISE_TO_PAY`, and automatically pauses dunning.
- **Enterprise Risk Management**: If the transaction is high-value (>₹50,000), or if the message is vague/complex (low confidence), it routes the transaction to a **Manual Review Queue**. The AI attaches its reasoning to the audit log to assist the human agent in making the final call.

________________________________________
Merchant Configuration
Merchants can configure: - Max retry attempts (1–10) - Max cost per recovery (₹5–₹200) - Do-not-disturb hours (no calls/SMS during these hours) - Minimum recovery score (transactions below this go to manual review) - Auto-retry soft declines (immediate alt-gateway retry) - Channel enablement (SMS, WhatsApp, email, voice call, payment link)
________________________________________
Next Steps for Production
1.	Replace rule-based scorer with XGBoost trained on historical Razorpay recovery data
2.	Add Razorpay webhook signature verification using razorpay_secret
3.	Integrate Razorpay Payment Links API for recovery link generation
4.	Add Twilio/Exotel for Hinglish voice calls
5.	Add WhatsApp Business API for recovery nudges
6.	Add Redis for retry job queues
7.	Add A/B testing framework for strategy efficacy comparison
________________________________________
Team
Built for Razorpay Buildathon 2026 — Track 03: AI Revenue Recovery
