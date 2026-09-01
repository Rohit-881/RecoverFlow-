import asyncio
import sys
import os
import random

# Ensure we can import from the main project directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Transaction, MerchantConfig
from executor import execute_recovery

async def test_real_payment_link():
    print("Creating a test transaction...")
    txn = Transaction(
        id=f"pay_test_link_{random.randint(1000, 9999)}",
        amount=500, # ₹500
        reason="insufficient_funds",
        method="UPI"
    )
    
    # We force the strategy to use the 'payment_link' channel
    strategy = {
        "action": "Delayed Nudge",
        "max_attempts": 3,
        "channels": ["payment_link"]
    }
    
    config = MerchantConfig(dnd_start_hour=24, dnd_end_hour=-1)
    
    print("Calling the AI execute_recovery engine (This will hit the Razorpay API)...")
    result = await execute_recovery(txn, strategy, config)
    
    print(f"\nFinal Status: {result.status.value}")
    print("\nAudit Trail:")
    for entry in result.audit:
        print(f" -> {entry.action}")
        if hasattr(entry, 'link_url') and entry.link_url:
            print(f"    [LINK GENERATED]: {entry.link_url}")
            
if __name__ == "__main__":
    asyncio.run(test_real_payment_link())
