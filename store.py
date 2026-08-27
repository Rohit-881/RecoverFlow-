"""
In-memory "database" — shared state imported by every other module.

Because Python caches modules, every file that does
`from store import transactions_db, merchant_configs`
gets a reference to the SAME dict objects, so mutations made in one
module (e.g. executor.py) are visible everywhere else (e.g. routers).
"""

from typing import Dict
from models import Transaction, MerchantConfig

transactions_db: Dict[str, Transaction] = {}

merchant_configs: Dict[str, MerchantConfig] = {
    "merchant_default": MerchantConfig()
}
