import requests
import json

def run_live_test():
    base_url = "https://recoverflow-backened.onrender.com"
    
    # 1. Fetch existing transactions from the LIVE running server
    print(f"Fetching existing transactions from {base_url}...")
    try:
        response = requests.get(f"{base_url}/transactions")
        transactions = response.json()
    except Exception as e:
        print("Error connecting to server. Make sure it is running!")
        print(e)
        return
        
    # Find a transaction that is currently 'pending' or 'retrying'
    active_txns = [t for t in transactions if t["status"] in ["pending", "retrying"]]
    
    if not active_txns:
        print("No active transactions found. Simulate a failure in the dashboard first!")
        return
        
    txn_id = active_txns[0]["id"]
    print(f"\n--- Selected Transaction ID: {txn_id} ---\n")
    
    # 2. Fire the webhook to the LIVE server
    payload = {
        "txn_id": txn_id,
        "message": "Sorry I am out of town, I will pay my bill next Friday."
    }
    
    print("Sending POST request to /webhooks/inbound-message ...")
    webhook_response = requests.post(f"{base_url}/webhooks/inbound-message", json=payload)
    
    print("\n--- Response ---")
    print(f"Status Code: {webhook_response.status_code}")
    print(f"Body: {json.dumps(webhook_response.json(), indent=2)}")
    print("\nSUCCESS! Now go look at your Dashboard and click the 'Promised' filter!")

if __name__ == "__main__":
    run_live_test()
