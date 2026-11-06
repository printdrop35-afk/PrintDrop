"""Platform-wide settings (super-admin): VAT rates, trial/grace periods, seller identity on invoices."""

from lib.db import db

DEFAULT_SETTINGS = {
    "shop_vat_rate_bp": 2000,          # 20 % — applied to shop prices (entered TTC)
    "subscription_vat_rate_bp": 2000,  # 20 % — added on top of plan prices (entered HT)
    "trial_days": 14,
    "grace_days": 7,
    "company_name": "PrintDrop",
    "company_address": "",
    "company_siret": "",
    "company_vat_number": "",
    "company_email": "",
}


async def get_settings() -> dict:
    doc = await db.platform_settings.find_one({"id": "global"}, {"_id": 0, "id": 0}) or {}
    return {**DEFAULT_SETTINGS, **doc}


async def shop_vat_bp() -> int:
    return (await get_settings())["shop_vat_rate_bp"]
