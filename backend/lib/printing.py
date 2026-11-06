"""Print-job queue for the PrintDrop Local Agent.

Guarantees against accidental duplicate printing:
- one "initial" job per (order, line) — unique index on (order_id, line_index, kind_key);
- an agent must claim a job (atomic lease) and present the lease_id on every report;
- a job that started printing and lost its agent is never re-queued automatically: it becomes
  "failed / statut inconnu" and only a manual, audited reprint creates a new job.
"""

import uuid
from datetime import timedelta

from pymongo.errors import DuplicateKeyError

from lib.authz import audit, now_utc
from lib.db import db
from lib.notify import enqueue_ready

CLAIM_LEASE_SECONDS = 120
PRINT_LEASE_SECONDS = 600
AGENT_ONLINE_SECONDS = 90
ACTIVE_JOB_STATUSES = ["queued", "claimed", "printing"]


async def shop_has_active_agent(org_id: str, shop_id: str) -> bool:
    return bool(await db.agents.find_one({"org_id": org_id, "shop_id": shop_id, "status": "active"}, {"_id": 1}))


def _job_doc(order: dict, line_index: int, line: dict, kind: str, requested_by: str, reason: str = "") -> dict:
    now = now_utc()
    return {
        "id": str(uuid.uuid4()), "org_id": order["org_id"], "shop_id": order["shop_id"], "order_id": order["id"],
        "order_code": order["code"], "line_index": line_index, "document_id": line["document_id"],
        "filename": line["filename"], "options": line["options"], "pages": line["pages"],
        "kind": kind, "kind_key": "initial" if kind == "initial" else f"reprint-{uuid.uuid4().hex}",
        "reason": reason, "status": "queued", "agent_id": None, "printer_name": None, "lease_id": None,
        "lease_expires_at": None, "error": None, "requested_by": requested_by,
        "created_at": now, "updated_at": now, "printed_at": None,
    }


async def enqueue_initial_jobs(order: dict, requested_by: str) -> int:
    """Called when staff moves an order to 'printing'. No-op if the shop has no paired agent."""
    if not await shop_has_active_agent(order["org_id"], order["shop_id"]):
        return 0
    created = 0
    for idx, line in enumerate(order["lines"]):
        if line["kind"] != "print" or not line.get("document_id"):
            continue
        try:
            await db.print_jobs.insert_one(_job_doc(order, idx, line, "initial", requested_by))
            created += 1
        except DuplicateKeyError:
            pass  # already queued once for this order line — never duplicate
    return created


async def create_reprint(job: dict, requested_by: str, reason: str) -> dict:
    order = await db.orders.find_one({"id": job["order_id"], "org_id": job["org_id"]}, {"_id": 0})
    assert order
    doc = _job_doc(order, job["line_index"], order["lines"][job["line_index"]], "reprint", requested_by, reason)
    doc["reprint_of"] = job["id"]
    await db.print_jobs.insert_one(dict(doc))
    return doc


async def maybe_complete_order(order_id: str, org_id: str, actor: str, origin: str) -> None:
    """When every print line has a printed job and nothing is still active, move printing -> ready."""
    order = await db.orders.find_one({"id": order_id, "org_id": org_id}, {"_id": 0})
    if not order or order["status"] != "printing":
        return
    jobs = await db.print_jobs.find({"order_id": order_id, "org_id": org_id}, {"_id": 0}).to_list(500)
    if any(j["status"] in ACTIVE_JOB_STATUSES for j in jobs):
        return
    printed_lines = {j["line_index"] for j in jobs if j["status"] == "printed"}
    needed = {i for i, line in enumerate(order["lines"]) if line["kind"] == "print" and line.get("document_id")}
    if not needed or not needed <= printed_lines:
        return
    now = now_utc()
    res = await db.orders.update_one({"id": order_id, "org_id": org_id, "status": "printing"}, {
        "$set": {"status": "ready", "updated_at": now},
        "$push": {"history": {"status": "ready", "at": now, "by": actor}},
    })
    if res.modified_count:
        await audit("order.status", org_id=org_id, actor=actor, resource_type="order", resource_id=order_id,
                    details={"code": order["code"], "from": "printing", "to": "ready", "auto": True})
        order["status"] = "ready"
        await enqueue_ready(order, origin)


async def expire_stale_leases() -> None:
    now = now_utc()
    # Claimed but never started: safe to hand to another agent.
    await db.print_jobs.update_many(
        {"status": "claimed", "lease_expires_at": {"$lt": now}},
        {"$set": {"status": "queued", "agent_id": None, "lease_id": None, "lease_expires_at": None, "updated_at": now}},
    )
    # Started printing and the agent vanished: outcome unknown -> never auto-retry.
    await db.print_jobs.update_many(
        {"status": "printing", "lease_expires_at": {"$lt": now}},
        {"$set": {"status": "failed", "error": "Statut inconnu (agent déconnecté pendant l'impression) — vérifiez avant de réimprimer",
                  "lease_id": None, "updated_at": now}},
    )


def is_online(last_seen_at) -> bool:
    return bool(last_seen_at) and (now_utc() - last_seen_at) < timedelta(seconds=AGENT_ONLINE_SECONDS)
