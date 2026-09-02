from fastapi.testclient import TestClient
from main import app
import json

def run_test():
    with TestClient(app) as client:
        # 1. Fetch existing transactions to get a valid ID dynamically
        print("Fetching existing transactions...")
        response = client.get("/transactions")
        transactions = response.json()
        
        # Find a transaction that is currently 'pending' or 'retrying'
        active_txns = [t for t in transactions if t["status"] in ["pending", "retrying"]]
        
        if not active_txns:
            print("No active transactions found in the database. Using a fallback ID (may result in 404).")
            txn_id = "pay_97255972"
        else:
            txn_id = active_txns[0]["id"]
            
        print(f"\n--- Selected Transaction ID: {txn_id} ---\n")
        
        # 2. Fire the webhook with the found ID
        payload = {
            "txn_id": txn_id,
            "message": "Sorry I am out of town, I will pay my bill next Friday."
        }
        
        print("Sending POST request to /webhooks/inbound-message ...")
        webhook_response = client.post("/webhooks/inbound-message", json=payload)
        
        print("\n--- Response ---")
        print(f"Status Code: {webhook_response.status_code}")
        print(f"Body: {json.dumps(webhook_response.json(), indent=2)}")

if __name__ == "__main__":
    run_test()
