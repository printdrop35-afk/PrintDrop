"""Shared Mongo handle — import `client`/`db` from here (server.py, routers, seed.py)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel

load_dotenv(Path(__file__).parent.parent / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url, tz_aware=True)  # datetimes come back UTC-aware
db = client[os.environ["DB_NAME"]]

logger = logging.getLogger(__name__)

# One entry per collection: every field a route filters, sorts, or dedupes on. Applied by ensure_indexes() at startup.
INDEXES: dict[str, list[IndexModel]] = {
    "users": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("email", ASCENDING)], name="email", unique=True),  # platform-global identities
    ],
    "organizations": [IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "memberships": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("user_id", ASCENDING), ("active", ASCENDING)], name="user_active"),
        IndexModel([("org_id", ASCENDING), ("created_at", ASCENDING)], name="org_created"),
    ],
    "shops": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("slug", ASCENDING)], name="slug", unique=True),
        IndexModel([("org_id", ASCENDING), ("created_at", ASCENDING)], name="org_created"),
    ],
    "documents": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("org_id", ASCENDING), ("order_id", ASCENDING)], name="org_order"),
        IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], name="status_created"),
    ],
    "orders": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        # 4-digit pickup codes are reused once an order is finished: uniqueness only while in progress (active_code)
        IndexModel([("code", ASCENDING), ("created_at", DESCENDING)], name="code_lookup"),
        IndexModel([("active_code", ASCENDING)], name="active_code", unique=True, partialFilterExpression={"active_code": {"$exists": True}}),
        IndexModel([("org_id", ASCENDING), ("shop_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)], name="org_shop_status_created"),
    ],
    "payments": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("order_id", ASCENDING)], name="order", unique=True),  # one payment per order
        IndexModel([("org_id", ASCENDING), ("shop_id", ASCENDING), ("created_at", DESCENDING)], name="org_shop_created"),
    ],
    "audit_logs": [
        IndexModel([("org_id", ASCENDING), ("at", DESCENDING)], name="org_at"),
        IndexModel([("action", ASCENDING), ("at", DESCENDING)], name="action_at"),
    ],
    "notification_jobs": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("order_id", ASCENDING), ("event", ASCENDING), ("channel", ASCENDING)], name="order_event_channel", unique=True),
        IndexModel([("status", ASCENDING), ("next_attempt_at", ASCENDING)], name="status_next"),
    ],
    "pairing_codes": [
        IndexModel([("code_hash", ASCENDING)], name="code_hash", unique=True),
        IndexModel([("expires_at", ASCENDING)], name="ttl", expireAfterSeconds=86400),
    ],
    "agents": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("key_hash", ASCENDING)], name="key_hash", unique=True),
        IndexModel([("org_id", ASCENDING), ("shop_id", ASCENDING), ("status", ASCENDING)], name="org_shop_status"),
    ],
    "printers": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("org_id", ASCENDING), ("agent_id", ASCENDING), ("name", ASCENDING)], name="org_agent_name", unique=True),
        IndexModel([("org_id", ASCENDING), ("shop_id", ASCENDING)], name="org_shop"),
    ],
    "print_jobs": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("order_id", ASCENDING), ("line_index", ASCENDING), ("kind_key", ASCENDING)], name="order_line_kind", unique=True),
        IndexModel([("org_id", ASCENDING), ("shop_id", ASCENDING), ("status", ASCENDING), ("created_at", ASCENDING)], name="org_shop_status_created"),
        IndexModel([("status", ASCENDING), ("lease_expires_at", ASCENDING)], name="status_lease"),
    ],
    "report_emails": [IndexModel([("org_id", ASCENDING), ("day", ASCENDING)], name="org_day", unique=True)],
    "cron_runs": [
        IndexModel([("run_id", ASCENDING)], name="run_id", unique=True),
        IndexModel([("at", ASCENDING)], name="ttl", expireAfterSeconds=30 * 86400),
    ],
    "plans": [IndexModel([("code", ASCENDING)], name="code", unique=True)],
    "platform_settings": [IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "migrations": [IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "invoices": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("provider_payment_id", ASCENDING)], name="provider_payment", unique=True,
                   partialFilterExpression={"provider_payment_id": {"$type": "string"}}),
        IndexModel([("number", ASCENDING)], name="number", unique=True, partialFilterExpression={"number": {"$type": "string"}}),
        IndexModel([("org_id", ASCENDING), ("created_at", DESCENDING)], name="org_created"),
    ],
    "counters": [IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "billing_reminders": [IndexModel([("key", ASCENDING)], name="key", unique=True)],
    "agent_commands": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("agent_id", ASCENDING), ("status", ASCENDING)], name="agent_status"),
        IndexModel([("created_at", ASCENDING)], name="ttl", expireAfterSeconds=7 * 86400),
    ],
    "owner_alerts": [IndexModel([("key", ASCENDING)], name="key", unique=True),
                     IndexModel([("at", ASCENDING)], name="ttl", expireAfterSeconds=30 * 86400)],
    "login_attempts": [
        IndexModel([("email", ASCENDING), ("at", ASCENDING)], name="email_at"),
        IndexModel([("at", ASCENDING)], name="ttl", expireAfterSeconds=3600),
    ],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:  # one at a time so a bad spec skips only itself
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:  # never block boot on an index; the log line names what to fix
                logger.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)
