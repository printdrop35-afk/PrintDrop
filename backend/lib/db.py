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
        IndexModel([("code", ASCENDING)], name="code", unique=True),
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
