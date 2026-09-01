import requests

URL = "https://recoverflow-backened.onrender.com/webhooks/inbound-message"
# Using one of the IDs from the webhooks test
PAYLOAD = {
    "txn_id": "inv_B2B_TEST_456",
    "message": "I don't have the money right now, I will pay next Friday."
}

print(f"Sending mock SMS reply to {URL}...")
try:
    response = requests.post(URL, json=PAYLOAD)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
