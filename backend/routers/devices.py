"""Dashboard side of devices: agent pairing, agents, printers, print jobs (incl. controlled reprints)
and the notification log of an order. Everything is tenant-scoped through TenantRepo."""

import os
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException

from lib.authz import Principal, audit, now_utc, require_tenant, tenant_repo
from lib.db import db
from lib.notify import twilio_configured
from lib.printing import create_reprint, is_online
from lib.security import sha256
from models.schemas import (
    AgentOut, NotificationOut, NotificationStatusOut, PairingCodeOut, PrinterOut, PrinterUpdateIn, PrintJobOut, ReprintIn,
)
from routers.dashboard import get_order_or_404, get_shop_or_404


router = APIRouter(tags=["devices"])

PAIR_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


# ---------- agents ----------
@router.post("/shops/{shop_id}/agents/pairing-code", response_model=PairingCodeOut)
async def pairing_code(shop_id: str, p: Principal = Depends(require_tenant("devices:manage"))):
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    code = "".join(secrets.choice(PAIR_ALPHABET) for _ in range(8))
    expires = now_utc() + timedelta(minutes=10)
    await repo.insert("pairing_codes", {"id": str(uuid.uuid4()), "shop_id": shop_id, "code_hash": sha256(code),
                                        "used": False, "expires_at": expires, "created_by": p.user_id, "created_at": now_utc()})
    await audit("agent.pairing_code", principal=p, resource_type="shop", resource_id=shop_id)
    return PairingCodeOut(code=code, expires_at=expires)


@router.get("/shops/{shop_id}/agents", response_model=list[AgentOut])
async def list_agents(shop_id: str, p: Principal = Depends(require_tenant("devices:read"))):
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    agents = await repo.find("agents", {"shop_id": shop_id}, sort=[("created_at", -1)])
    return [AgentOut(**a, online=a["status"] == "active" and is_online(a.get("last_seen_at"))) for a in agents]


@router.post("/agents/{agent_id}/revoke", response_model=AgentOut)
async def revoke_agent(agent_id: str, p: Principal = Depends(require_tenant("devices:manage"))):
    repo = tenant_repo(p)
    if not await repo.update_one("agents", {"id": agent_id}, {"$set": {"status": "revoked"}}):
        raise HTTPException(status_code=404, detail="Agent introuvable")
    # Jobs it had claimed but not started go back to the queue.
    now = now_utc()
    await db.print_jobs.update_many({"org_id": p.org_id, "agent_id": agent_id, "status": "claimed"},
                                    {"$set": {"status": "queued", "agent_id": None, "lease_id": None, "updated_at": now}})
    await audit("agent.revoke", principal=p, resource_type="agent", resource_id=agent_id)
    a = await repo.find_one("agents", {"id": agent_id})
    assert a
    return AgentOut(**a, online=False)


# ---------- printers ----------
@router.get("/shops/{shop_id}/printers", response_model=list[PrinterOut])
async def list_printers(shop_id: str, p: Principal = Depends(require_tenant("devices:read"))):
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    active = {a["id"] for a in await repo.find("agents", {"shop_id": shop_id, "status": "active"})}
    printers = await repo.find("printers", {"shop_id": shop_id}, sort=[("name", 1)])
    return [PrinterOut(**pr, online=pr["agent_id"] in active and is_online(pr.get("last_seen_at")) and pr["status"] == "online")
            for pr in printers if pr["agent_id"] in active]


@router.patch("/printers/{printer_id}", response_model=PrinterOut)
async def update_printer(printer_id: str, body: PrinterUpdateIn, p: Principal = Depends(require_tenant("devices:manage"))):
    repo = tenant_repo(p)
    pr = await repo.find_one("printers", {"id": printer_id})
    if not pr:
        raise HTTPException(status_code=404, detail="Imprimante introuvable")
    changes = body.model_dump(exclude_none=True)
    if changes.get("is_default"):
            await db.printers.update_many({"org_id": p.org_id, "shop_id": pr["shop_id"]}, {"$set": {"is_default": False}})
    if changes:
        await repo.update_one("printers", {"id": printer_id}, {"$set": changes})
        await audit("printer.update", principal=p, resource_type="printer", resource_id=printer_id, details=changes)
    pr = await repo.find_one("printers", {"id": printer_id})
    assert pr
    return PrinterOut(**pr, online=is_online(pr.get("last_seen_at")) and pr["status"] == "online")


# ---------- print jobs ----------
@router.get("/orders/{order_id}/print-jobs", response_model=list[PrintJobOut])
async def order_jobs(order_id: str, p: Principal = Depends(require_tenant("orders:read"))):
    repo = tenant_repo(p)
    await get_order_or_404(repo, order_id)
    return await repo.find("print_jobs", {"order_id": order_id}, sort=[("created_at", 1)])


@router.post("/print-jobs/{job_id}/reprint", response_model=PrintJobOut)
async def reprint(job_id: str, body: ReprintIn, p: Principal = Depends(require_tenant("jobs:reprint"))):
    repo = tenant_repo(p)
    job = await repo.find_one("print_jobs", {"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Travail d'impression introuvable")
    if job["status"] not in ("printed", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail="Ce travail est encore en cours — attendez son résultat")
    if await repo.count("print_jobs", {"order_id": job["order_id"], "line_index": job["line_index"],
                                       "status": {"$in": ["queued", "claimed", "printing"]}}):
        raise HTTPException(status_code=409, detail="Une réimpression de ce document est déjà en file")
    order = await get_order_or_404(repo, job["order_id"])
    if order["status"] in ("picked_up", "cancelled"):
        raise HTTPException(status_code=409, detail="Commande clôturée — réimpression impossible")
    new = await create_reprint(job, p.name, body.reason.strip())
    if order["status"] != "printing":
        now = now_utc()
        await repo.update_one("orders", {"id": order["id"], "status": order["status"]}, {
            "$set": {"status": "printing", "updated_at": now},
            "$push": {"history": {"status": "printing", "at": now, "by": f"{p.name} (réimpression)"}},
        })
    await audit("job.reprint", principal=p, resource_type="print_job", resource_id=new["id"],
                details={"code": order["code"], "of": job_id, "reason": body.reason.strip()})
    return new


@router.post("/print-jobs/{job_id}/cancel", response_model=PrintJobOut)
async def cancel_job(job_id: str, p: Principal = Depends(require_tenant("orders:update"))):
    repo = tenant_repo(p)
    if not await repo.update_one("print_jobs", {"id": job_id, "status": {"$in": ["queued", "failed"]}},
                                 {"$set": {"status": "cancelled", "updated_at": now_utc()}}):
        raise HTTPException(status_code=409, detail="Seul un travail en file ou en échec peut être annulé")
    await audit("job.cancel", principal=p, resource_type="print_job", resource_id=job_id)
    job = await repo.find_one("print_jobs", {"id": job_id})
    assert job
    return job


# ---------- notifications ----------
@router.get("/orders/{order_id}/notifications", response_model=list[NotificationOut])
async def order_notifications(order_id: str, p: Principal = Depends(require_tenant("orders:read"))):
    repo = tenant_repo(p)
    await get_order_or_404(repo, order_id)
    return await repo.find("notification_jobs", {"order_id": order_id}, sort=[("created_at", 1)])


@router.get("/notifications/status", response_model=NotificationStatusOut)
async def notification_status(_: Principal = Depends(require_tenant("orders:read"))):
    return NotificationStatusOut(email_configured=bool(os.environ.get("EMERGENT_EMAIL_KEY")), sms_configured=twilio_configured())
