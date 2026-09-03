import requests
import json

def run_live_test():
    base_url = "http://127.0.0.1:8000" # Changed to local server for testing
    
    # 1. Fetch existing transactions from the LIVE running server
    print(f"Fetching existing transactions from {base_url}...")
    try:
        response = requests.get(f"{base_url}/transactions")
        transactions = response.json()
        print("\n--- Available Transactions on Server ---")
        for t in transactions:
            print(f"  - ID: {t.get('id')} | Status: {t.get('status')} | Amount: INR {t.get('amount')} | Bucket: {t.get('bucket')}")
        print("----------------------------------------\n")
    except Exception as e:
        print("Error connecting to server. Make sure it is running!")
        print(e)
        return
        
    # -------------------------------------------------------------------
    # TRANSACTION SELECTION:
    # Set manual_txn_id to a specific ID (e.g. "pay_F8047f5965") to test a specific txn,
    # or keep manual_txn_id = None to automatically pick the first active transaction.
    # -------------------------------------------------------------------
    manual_txn_id = None  # e.g. "pay_F8047f5965" (or leave None to pick automatically)

    if manual_txn_id:
        txn_id = manual_txn_id
    else:
        if not transactions:
            print("No transactions found in server database!")
            return
        # Find active transaction or fallback to available transaction
        active_txns = [t for t in transactions if t["status"] in ["pending", "retrying", "manual_review"]]
        txn_id = active_txns[0]["id"] if active_txns else transactions[0]["id"]

    print(f"\n--- Selected Transaction ID: {txn_id} ---\n")
    
    # -------------------------------------------------------------------
    # TEST MESSAGES — Uncomment the message you want to test:
    # -------------------------------------------------------------------
    
    # 1. Clear Promise to Pay (Logs Promise-to-Pay Date)
    # message = "Sorry, I am out of town, I will pay my bill next Friday."
    
    # 2. Vague / Complex Message (Triggers Manual Review)
    message = "I might pay half next month if I have money"

    payload = {
        "txn_id": txn_id,
        "message": message
    }
    
    print("Sending POST request to /webhooks/inbound-message ...")
    webhook_response = requests.post(f"{base_url}/webhooks/inbound-message", json=payload)
    
    print("\n--- Response ---")
    print(f"Status Code: {webhook_response.status_code}")
    print(f"Body: {json.dumps(webhook_response.json(), indent=2)}")
    print("\nSUCCESS! Now go look at your Dashboard and click the 'Promised' filter!")

if __name__ == "__main__":
    run_live_test()
