import hmac
import hashlib
import json
import requests
import os
from dotenv import load_dotenv

load_dotenv()
SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "123456")
URL = "https://recoverflow-backened.onrender.com/webhooks/razorpay" 

def send_webhook(event_type, payload):
    body = json.dumps(payload, separators=(',', ':'))
    signature = hmac.new(
        SECRET.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature
    }
    
    print(f"Sending {event_type} webhook to {URL} ...")
    response = requests.post(URL, data=body, headers=headers)
    print(f"Response: {response.status_code} - {response.text}\n")

import random
import time

if __name__ == "__main__":
    for i in range(5):
        # Generate 5 random Subscriptions
        sub_id = f"pay_SUB_TEST_{random.randint(1000,9999)}"
        subscription_payload = {
          "event": "payment.failed",
          "payload": {
            "payment": {
              "entity": {
                "id": sub_id,
                "amount": random.choice([49900, 99900, 149900, 199900]),
                "method": "card",
                "error_description": "Insufficient funds in bank account",
                "subscription_id": f"sub_XYZ{random.randint(100,999)}"
              }
            }
          }
        }
        send_webhook("payment.failed (Subscription)", subscription_payload)
        time.sleep(1)
        
        # Generate 5 random B2B Invoices
        inv_id = f"inv_B2B_TEST_{random.randint(1000,9999)}"
        invoice_payload = {
          "event": "invoice.expired",
          "payload": {
            "invoice": {
              "entity": {
                "id": inv_id,
                "amount": random.choice([5000000, 15000000, 25000000, 50000000]) 
              }
            }
          }
        }
        send_webhook("invoice.expired (B2B)", invoice_payload)
        time.sleep(1)
