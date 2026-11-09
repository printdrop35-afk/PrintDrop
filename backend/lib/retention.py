"""Customer-data retention: document files + customer name/phone are erased once an order is collected or cancelled,
and at the latest RETENTION_DAYS after the order was placed. Order amounts/status stay for accounting and reports."""

import logging
from datetime import timedelta

from lib.authz import now_utc
from lib.db import db
from lib.storage import delete_file

logger = logging.getLogger(__name__)

RETENTION_DAYS = 7  # stated in the privacy policy — keep both in sync
ORPHAN_UPLOAD_HOURS = 24  # uploads never attached to an order
ANON_NAME = "Client anonymisé"


async def _erase_documents(query: dict) -> int:
    n = 0
    async for doc in db.documents.find({**query, "status": {"$ne": "purged"}}, {"_id": 0, "id": 1, "storage_key": 1}):
        if doc.get("storage_key"):
            try:
                delete_file(doc["storage_key"])
            except Exception as exc:  # file already gone / path issue — still mark as purged
                logger.warning("retention: file %s not deleted: %s", doc["id"], exc)
        await db.documents.update_one({"id": doc["id"]}, {"$set": {"status": "purged", "storage_key": None, "filename": None, "purged_at": now_utc()}})
        n += 1
    return n


async def purge_order(order_id: str) -> bool:
    """Erase files + customer identity of one order (idempotent)."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0, "id": 1, "purged_at": 1})
    if not order or order.get("purged_at"):
        return False
    now = now_utc()
    await db.print_jobs.update_many({"order_id": order_id, "status": {"$in": ["queued", "claimed", "retry_wait"]}},
                                    {"$set": {"status": "cancelled", "error": "Document supprimé (durée de conservation)", "updated_at": now}})
    await _erase_documents({"order_id": order_id})
    await db.orders.update_one({"id": order_id}, {"$set": {
        "customer_name": ANON_NAME, "customer_phone": "", "phone_digits": "", "customer_email": None, "note": "",
        "lines.$[].filename": None, "purged_at": now,
    }})
    return True


async def run_retention() -> dict:
    now = now_utc()
    due = {"purged_at": {"$in": [None]}, "$or": [
        {"status": {"$in": ["picked_up", "cancelled"]}},
        {"created_at": {"$lt": now - timedelta(days=RETENTION_DAYS)}},
    ]}
    orders = 0
    async for o in db.orders.find(due, {"_id": 0, "id": 1}):
        orders += await purge_order(o["id"])
    orphans = await _erase_documents({"order_id": None, "created_at": {"$lt": now - timedelta(hours=ORPHAN_UPLOAD_HOURS)}})
    logger.info("retention: %s orders, %s orphan uploads erased", orders, orphans)
    return {"orders": orders, "orphan_documents": orphans}
