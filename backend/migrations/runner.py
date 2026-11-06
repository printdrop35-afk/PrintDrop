"""Versioned, idempotent database migrations. Applied ids are recorded in `migrations`.
Run automatically at startup and manually with: cd /app/backend && python -m migrations.runner"""

import asyncio
import logging
from datetime import timedelta

from lib.authz import now_utc
from lib.billing import DEFAULT_PLANS
from lib.db import db
from lib.platform import DEFAULT_SETTINGS
from lib.pricing import LEGACY_DEFAULT_PRINT, default_pricing, example_services

logger = logging.getLogger(__name__)


async def m001_pricing_v2() -> None:
    """Add v2 pricing fields (active flags, services catalogue, rules, discounts, minimum) to every shop.
    Shops still on the untouched Stage-1 defaults receive the new example prices; edited prices are kept."""
    new_defaults = default_pricing()
    async for shop in db.shops.find({}, {"_id": 0, "id": 1, "pricing": 1}):
        p = dict(shop.get("pricing") or {})
        untouched = {k: {"bw": v["bw"], "color": v["color"]} for k, v in p.get("print", {}).items()} == LEGACY_DEFAULT_PRINT
        if untouched:
            p["print"] = new_defaults["print"]
            p["photocopy"] = new_defaults["photocopy"]
        for size, prices in p.get("print", {}).items():
            prices.setdefault("active", True)
        p.setdefault("photocopy", new_defaults["photocopy"]).setdefault("active", True)
        p.setdefault("min_order_cents", 0)
        p.setdefault("services", example_services())
        p.setdefault("rules", [])
        p.setdefault("discounts", [])
        await db.shops.update_one({"id": shop["id"]}, {"$set": {"pricing": p}})


async def m002_subscriptions() -> None:
    """Seed the three plans and platform settings; give every existing organization a 14-day trial
    (no payment is invented: nobody is marked as paid)."""
    for plan in DEFAULT_PLANS:
        await db.plans.update_one({"code": plan["code"]}, {"$setOnInsert": {**plan, "created_at": now_utc()}}, upsert=True)
    await db.platform_settings.update_one({"id": "global"}, {"$setOnInsert": {"id": "global", **DEFAULT_SETTINGS}}, upsert=True)
    now = now_utc()
    await db.organizations.update_many({"subscription": {"$exists": False}}, {"$set": {
        "subscription": {"plan_code": "pro", "period": "monthly", "status": "trialing",
                         "trial_ends_at": now + timedelta(days=DEFAULT_SETTINGS["trial_days"]),
                         "current_period_end": None, "granted_by_admin": False, "updated_at": now},
    }})


MIGRATIONS = [("001_pricing_v2", m001_pricing_v2), ("002_subscriptions", m002_subscriptions)]


async def run_migrations() -> list[str]:
    applied = []
    for mid, fn in MIGRATIONS:
        if await db.migrations.find_one({"id": mid}):
            continue
        await fn()
        await db.migrations.insert_one({"id": mid, "applied_at": now_utc()})
        logger.info("migration %s applied", mid)
        applied.append(mid)
    return applied


if __name__ == "__main__":
    print("Applied:", asyncio.run(run_migrations()) or "none (up to date)")
