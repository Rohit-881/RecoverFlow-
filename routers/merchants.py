"""
Merchant routes — get/update per-merchant recovery configuration.
"""

from fastapi import APIRouter

from models import MerchantConfig
from store import merchant_configs

router = APIRouter(tags=["merchants"])


@router.put("/merchants/{merchant_id}/config")
async def update_merchant_config(merchant_id: str, config: MerchantConfig):
    """Update merchant recovery configuration."""
    config.merchant_id = merchant_id
    merchant_configs[merchant_id] = config
    return config


@router.get("/merchants/{merchant_id}/config")
async def get_merchant_config(merchant_id: str):
    """Get merchant recovery configuration."""
    return merchant_configs.get(merchant_id, MerchantConfig(merchant_id=merchant_id))
