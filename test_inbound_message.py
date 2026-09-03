import requests
import json

def run_live_test():
    base_url = "http://127.0.0.1:8000" # Changed to local server for testing
    
    # 1. Fetch existing transactions from the LIVE running server
    print(f"Fetching existing transactions from {base_url}...")
    try:
        response = requests.get(f"{base_url}/transactions")
        transactions = response.json()
    except Exception as e:
        print("Error connecting to server. Make sure it is running!")
        print(e)
        return
        
    # -------------------------------------------------------------------
    # TRANSACTION SELECTION:
    # Set manual_txn_id to a specific ID (e.g. "pay_F8047f5965") to test a specific txn,
    # or keep manual_txn_id = None to automatically pick the first active transaction.
    # -------------------------------------------------------------------
    manual_txn_id = None  # e.g. "pay_F8047f5965"

    if manual_txn_id:
        txn_id = manual_txn_id
    else:
        # Find a transaction that is currently 'pending' or 'retrying'
        active_txns = [t for t in transactions if t["status"] in ["pending", "retrying"]]
        
        if not active_txns:
            print("No active transactions found. Simulate a failure in the dashboard first!")
            return
            
        txn_id = active_txns[0]["id"]

    print(f"\n--- Selected Transaction ID: {txn_id} ---\n")
    
    # -------------------------------------------------------------------
    # TEST MESSAGES — Uncomment the message you want to test:
    # -------------------------------------------------------------------
    
    # Message 1: Promise to Pay with specific timing / Friday
    # message = "I don't have the money right now, I will pay next Friday."
    
    # Message 2: Vague / Complex promise (Paycheck / next week)
    message = "I am currently waiting on my next paycheck to clear. I should be able to get this sorted out sometime late next week, hopefully by Friday."
    
    # Message 3: High Confidence Promise with explicit date
    # message = "Sorry for the delay! I will make the payment on 2026-09-15 without fail."
    
    # Message 4: Complex inquiry / Finance review (Sent to Manual Review)
    # message = "I need to check with my accounting team because our company billing period starts next month."
    
    # Message 5: Refusal / Cancellation Request
    # message = "Please cancel this invoice, I am no longer using this service."

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
