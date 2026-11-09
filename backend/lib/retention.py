"""Document retention: when an order is picked up or cancelled, every file of the order is deleted from storage
(original upload; print-ready PDFs are generated in memory and never stored). Order data — customer name/phone/email,
payment, history, pickup — is kept. Idempotent; documents whose deletion failed are retried by the hourly cron."""

import logging
from datetime import timedelta

from lib.authz import now_utc
from lib.db import db
from lib.storage import StorageError, delete_file

logger = logging.getLogger(__name__)

ORPHAN_UPLOAD_HOURS = 24  # uploads never attached to an order
FINAL_STATUSES = ["picked_up", "cancelled"]


async def _erase_documents(query: dict) -> tuple[int, int]:
    """Returns (deleted, failed). A document is marked purged only once its file is really gone."""
    deleted = failed = 0
    async for doc in db.documents.find({**query, "status": {"$ne": "purged"}}, {"_id": 0, "id": 1, "storage_key": 1}):
        try:
            if doc.get("storage_key"):
                await delete_file(doc["storage_key"])
        except (OSError, StorageError) as exc:
            failed += 1
            logger.error("retention: deletion failed for document %s (will retry): %s", doc["id"], exc)
            await db.documents.update_one({"id": doc["id"]}, {"$set": {"purge_error": str(exc)[:200]}, "$inc": {"purge_attempts": 1}})
            continue
        await db.documents.update_one({"id": doc["id"]}, {"$set": {"status": "purged", "storage_key": None, "purged_at": now_utc()},
                                                            "$unset": {"purge_error": ""}})
        deleted += 1
    return deleted, failed


SCAN_GRACE = timedelta(hours=24)  # digital scans: kept 24 h after the customer's first download


def _due(order: dict) -> bool:
    if order["status"] in FINAL_STATUSES:
        return True
    return order["status"] == "delivered" and bool(order.get("scan_downloaded_at")) and now_utc() - order["scan_downloaded_at"] >= SCAN_GRACE


async def purge_order(order_id: str) -> bool:
    """Delete the files of one finished order (idempotent). Order record untouched except purged_at."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0, "id": 1, "status": 1, "scan_downloaded_at": 1})
    if not order or not _due(order):
        return False  # never delete while pending / printing / ready, nor a scan the customer has not downloaded
    now = now_utc()
    await db.print_jobs.update_many({"order_id": order_id, "status": {"$in": ["queued", "claimed", "retry_wait"]}},
                                    {"$set": {"status": "cancelled", "error": "Document supprimé (commande terminée)", "updated_at": now}})
    _, failed = await _erase_documents({"order_id": order_id})
    if failed:
        return False
    res = await db.orders.update_one({"id": order_id, "purged_at": None}, {"$set": {"purged_at": now}})
    if res.modified_count:
        from lib.authz import audit
        await audit("order.documents_deleted", org_id=None, resource_type="order", resource_id=order_id, actor="system")
    return bool(res.modified_count)


async def run_retention() -> dict:
    """Hourly: finished orders whose files are not deleted yet (incl. failed attempts), and orphan uploads."""
    orders = 0
    async for o in db.orders.find({"status": {"$in": FINAL_STATUSES + ["delivered"]}, "purged_at": None}, {"_id": 0, "id": 1}):
        orders += await purge_order(o["id"])
    # scan pages of sessions abandoned for 24 h (finalised sessions erase their pages immediately)
    old = now_utc() - timedelta(hours=ORPHAN_UPLOAD_HOURS)
    async for pg in db.scan_pages.find({"created_at": {"$lt": old}}, {"_id": 0, "id": 1, "storage_key": 1}):
        try:
            await delete_file(pg["storage_key"])
            await db.scan_pages.delete_one({"id": pg["id"]})
        except OSError as exc:
            logger.error("retention: scan page %s not deleted (will retry): %s", pg["id"], exc)
    orphans, _ = await _erase_documents({"order_id": None, "created_at": {"$lt": now_utc() - timedelta(hours=ORPHAN_UPLOAD_HOURS)}})
    logger.info("retention: %s orders, %s orphan uploads deleted", orders, orphans)
    return {"orders": orders, "orphan_documents": orphans}
