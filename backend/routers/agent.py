"""API used by the PrintDrop Local Agent (Windows). Machine principal: one agent = one shop.
Auth: `Authorization: Bearer pda_…` (only a SHA-256 of the key is stored)."""

import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from lib.authz import audit, now_utc, request_origin
from lib.db import db
from lib.pricing import parse_page_range
from lib.notify import alert_owner
from lib.printing import CLAIM_LEASE_SECONDS, PRINT_LEASE_SECONDS, maybe_complete_order
from lib.security import sha256
from lib.storage import MEDIA_TYPES, StorageError, extract_pages, read_file
from models.schemas import (
    AgentClaimOut, AgentCommandResultIn, AgentCopyProgressIn, AgentHeartbeatIn, AgentHeartbeatOut, AgentJobOut, AgentPairIn, AgentPairOut, AgentReportIn, AgentReportOut,
)

router = APIRouter(prefix="/agent", tags=["agent"])

POLL_SECONDS = 5


class AgentPrincipal(BaseModel):
    agent_id: str
    name: str
    org_id: str
    shop_id: str


async def get_agent(authorization: str = Header(default="")) -> AgentPrincipal:
    key = authorization.removeprefix("Bearer ").strip()
    if not key.startswith("pda_"):
        raise HTTPException(status_code=401, detail="Clé d'agent requise")
    agent = await db.agents.find_one({"key_hash": sha256(key), "status": "active"}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=401, detail="Agent inconnu ou révoqué")
    org = await db.organizations.find_one({"id": agent["org_id"], "status": "active"}, {"_id": 1})
    if not org:
        raise HTTPException(status_code=403, detail="Organisation suspendue")
    return AgentPrincipal(agent_id=agent["id"], name=agent["name"], org_id=agent["org_id"], shop_id=agent["shop_id"])


@router.post("/pair", response_model=AgentPairOut)
async def pair(body: AgentPairIn):
    now = now_utc()
    code = await db.pairing_codes.find_one_and_update(
        {"code_hash": sha256(body.code.strip().upper()), "used": False, "expires_at": {"$gt": now}},
        {"$set": {"used": True, "used_at": now}}, projection={"_id": 0},
    )
    if not code:
        raise HTTPException(status_code=404, detail="Code d'appairage invalide ou expiré")
    shop = await db.shops.find_one({"id": code["shop_id"], "org_id": code["org_id"]}, {"_id": 0})
    if not shop:
        raise HTTPException(status_code=404, detail="Boutique introuvable")
    api_key = "pda_" + secrets.token_urlsafe(32)
    agent_id = str(uuid.uuid4())
    await db.agents.insert_one({
        "id": agent_id, "org_id": shop["org_id"], "shop_id": shop["id"], "name": body.name.strip(),
        "hostname": body.hostname.strip(), "version": body.version.strip(), "key_hash": sha256(api_key),
        "status": "active", "last_seen_at": None, "created_at": now,
    })
    await audit("agent.paired", org_id=shop["org_id"], actor=f"agent:{body.name.strip()}", resource_type="agent",
                resource_id=agent_id, details={"hostname": body.hostname})
    return AgentPairOut(agent_id=agent_id, api_key=api_key, shop_id=shop["id"], shop_name=shop["name"])


@router.post("/heartbeat", response_model=AgentHeartbeatOut)
async def heartbeat(body: AgentHeartbeatIn, a: AgentPrincipal = Depends(get_agent)):
    now = now_utc()
    await db.agents.update_one({"id": a.agent_id}, {"$set": {"last_seen_at": now, "version": body.version, "drivers": body.drivers[:300], "scanners": body.scanners[:20],
                                                                  "scanner_caps": [c.model_dump() for c in body.scanner_caps[:20]]}})
    previous = {p["name"]: p.get("status") for p in await db.printers.find({"org_id": a.org_id, "agent_id": a.agent_id}, {"_id": 0, "name": 1, "status": 1}).to_list(100)}
    has_default = bool(await db.printers.find_one({"org_id": a.org_id, "shop_id": a.shop_id, "is_default": True}, {"_id": 1}))
    seen = []
    for pr in body.printers:
        seen.append(pr.name)
        res = await db.printers.update_one(
            {"org_id": a.org_id, "agent_id": a.agent_id, "name": pr.name},
            {"$set": {"status": pr.status, "status_detail": pr.detail, "supports_color": pr.supports_color, "last_seen_at": now,
                      "manufacturer": pr.manufacturer, "model": pr.model, "ip_address": pr.ip_address, "port_name": pr.port_name,
                      "driver_name": pr.driver_name, "driver_ok": pr.driver_ok, "capabilities": pr.capabilities.model_dump(),
                      "detected_connection": pr.connection_type},
             "$setOnInsert": {"id": str(uuid.uuid4()), "shop_id": a.shop_id, "enabled": True, "display_name": "",
                              "connection_type": pr.connection_type, "connection_confirmed": pr.connection_type in ("usb", "virtual"),
                              "is_default": pr.is_default and not has_default}},
            upsert=True,
        )
        if res.upserted_id and pr.is_default:
            has_default = True
        if previous.get(pr.name) == "online" and pr.status != "online":
            await alert_owner(a.org_id, f"printer-offline:{a.agent_id}:{pr.name}:{now:%Y%m%d%H}",
                              f"Imprimante « {pr.name} » {'hors ligne' if pr.status == 'offline' else 'en erreur'}",
                              f"L'imprimante « {pr.name} » ({a.name}) signale : {pr.detail or pr.status}. Les travaux restent en file ; vous pouvez les réaffecter depuis PrintDrop.")
    await db.printers.update_many({"org_id": a.org_id, "agent_id": a.agent_id, "name": {"$nin": seen}},
                                  {"$set": {"status": "offline", "status_detail": "Non détectée par l'agent"}})
    shop = await db.shops.find_one({"id": a.shop_id}, {"_id": 0, "name": 1})
    cmds = await db.agent_commands.find({"agent_id": a.agent_id, "org_id": a.org_id, "status": "queued"}, {"_id": 0}).to_list(10)
    if cmds:
        await db.agent_commands.update_many({"id": {"$in": [c["id"] for c in cmds]}}, {"$set": {"status": "sent", "sent_at": now}})
    return AgentHeartbeatOut(shop_name=shop["name"] if shop else "", poll_seconds=POLL_SECONDS,
                             commands=[{"id": c["id"], "type": c["type"], "payload": c["payload"]} for c in cmds])


@router.post("/commands/{command_id}/progress")
async def command_progress(command_id: str, body: AgentCopyProgressIn, a: AgentPrincipal = Depends(get_agent)):
    """Live photocopy progress (pages scanned, pages printed per the Windows spooler). Also proves the PC is alive."""
    cmd = await db.agent_commands.find_one({"id": command_id, "agent_id": a.agent_id, "org_id": a.org_id, "status": "sent", "type": "copy"}, {"_id": 0})
    if not cmd:
        raise HTTPException(status_code=404, detail="Commande inconnue")
    now = now_utc()
    await db.agents.update_one({"id": a.agent_id}, {"$set": {"last_seen_at": now}})
    await db.orders.update_one({"id": cmd["payload"]["order_id"], "org_id": a.org_id, "copy_job.state": "running"}, {"$set": {
        "copy_job.phase": body.phase, "copy_job.progress_scanned": body.scanned_pages, "copy_job.progress_printed_pages": body.printed_pages,
        "copy_job.total_print_pages": body.total_pages, "updated_at": now}})
    return {"ok": True}


@router.post("/commands/{command_id}/result")
async def command_result(command_id: str, body: AgentCommandResultIn, a: AgentPrincipal = Depends(get_agent)):
    cmd = await db.agent_commands.find_one_and_update(
        {"id": command_id, "agent_id": a.agent_id, "org_id": a.org_id, "status": "sent"},
        {"$set": {"status": "done" if body.ok else "failed", "result": body.result, "error": body.error, "done_at": now_utc()}},
        projection={"_id": 0})
    if not cmd:
        raise HTTPException(status_code=404, detail="Commande inconnue")
    if cmd["type"] == "copy":
        from routers.counter import apply_copy_result
        await apply_copy_result(cmd, body.ok, body.result, body.error)
    elif cmd["type"] == "test_connection" and cmd["payload"].get("printer_name"):
        # « Prête » is only shown after a successful real check by the agent
        await db.printers.update_one({"org_id": a.org_id, "agent_id": a.agent_id, "name": cmd["payload"]["printer_name"]},
                                     {"$set": {"verified_at": now_utc() if body.ok else None, "verify_error": "" if body.ok else body.error}})
    return {"ok": True}


@router.post("/jobs/claim", response_model=AgentClaimOut)
async def claim(a: AgentPrincipal = Depends(get_agent)):
    printers = await db.printers.find(
        {"org_id": a.org_id, "agent_id": a.agent_id, "enabled": True, "status": "online"}, {"_id": 0}
    ).sort("is_default", -1).to_list(50)
    if not printers:
        return AgentClaimOut(jobs=[], message="Aucune imprimante activée et en ligne sur ce poste")
    mine = {p["id"]: p["name"] for p in printers}
    default = printers[0]
    jobs: list[AgentJobOut] = []
    for _ in range(3):
        now = now_utc()
        lease_id = uuid.uuid4().hex
        claimable = {"$or": [{"status": "queued"}, {"status": "retry_wait", "next_attempt_at": {"$lte": now}}]}
        # a job assigned to a printer is only taken by the agent that owns it; unassigned jobs go to the default
        target = {"$or": [{"printer_id": {"$in": list(mine)}}, {"printer_id": None}]}
        job = await db.print_jobs.find_one_and_update(
            {"org_id": a.org_id, "shop_id": a.shop_id, "$and": [claimable, target]},
            {"$set": {"status": "claimed", "agent_id": a.agent_id, "lease_id": lease_id,
                      "lease_expires_at": now + timedelta(seconds=CLAIM_LEASE_SECONDS), "updated_at": now}},
            sort=[("created_at", 1)], projection={"_id": 0}, return_document=True,
        )
        if not job:
            break
        printer = mine.get(job.get("printer_id") or "", default["name"])
        await db.print_jobs.update_one({"id": job["id"]}, {"$set": {"printer_name": printer, "printer_id": job.get("printer_id") or default["id"]}})
        doc = await db.documents.find_one({"id": job["document_id"], "org_id": a.org_id}, {"_id": 0})
        if not doc:
            await db.print_jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": "Document supprimé"}})
            continue
        selected = parse_page_range(job["options"].get("page_range", ""), doc["page_count"])
        jobs.append(AgentJobOut(
            id=job["id"], lease_id=lease_id, order_code=job["order_code"], kind=job["kind"], filename=job["filename"],
            # the agent receives a file that contains ONLY the selected pages, so it prints the whole file
            file_kind=doc["kind"], options=job["options"], pages=list(range(1, len(selected) + 1)) if doc["kind"] == "pdf" else [1],
            printer_name=printer, download_url=f"/api/agent/jobs/{job['id']}/file?lease={lease_id}",
        ))
    return AgentClaimOut(jobs=jobs)


@router.post("/jobs/{job_id}/report", response_model=AgentReportOut)
async def report(job_id: str, body: AgentReportIn, request: Request, a: AgentPrincipal = Depends(get_agent)):
    job = await db.print_jobs.find_one({"id": job_id, "org_id": a.org_id, "shop_id": a.shop_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Travail introuvable")
    if job["status"] == body.status == "printed" and job["agent_id"] == a.agent_id:
        return AgentReportOut(job_id=job_id, status="printed")  # idempotent retry of a lost response
    if job["agent_id"] != a.agent_id or job["lease_id"] != body.lease_id:
        raise HTTPException(status_code=409, detail="Bail invalide — ce travail n'appartient plus à cet agent")
    now = now_utc()
    # claimed (delivered to agent) -> spooled (accepted by Windows spooler) -> printing -> printed (completed per driver)
    allowed = {"spooled": ["claimed", "printing"], "printing": ["claimed", "spooled"], "printed": ["claimed", "spooled", "printing"],
               "failed": ["claimed", "spooled", "printing"], "requeue": ["claimed"]}
    if job["status"] not in allowed[body.status]:
        raise HTTPException(status_code=409, detail=f"Transition impossible : {job['status']} → {body.status}")
    if body.status in ("printing", "spooled"):
        update = {"status": body.status, "lease_expires_at": now + timedelta(seconds=PRINT_LEASE_SECONDS)}
        if body.status == "spooled":
            update["spooled_at"] = now
    elif body.status == "printed":
        update = {"status": "printed", "printed_at": now, "error": None}
    elif body.status == "failed":
        update = {"status": "failed", "error": body.error or "Erreur d'impression"}
    else:
        # printer unavailable before anything was sent: wait and retry (never counts as a print)
        update = {"status": "retry_wait", "next_attempt_at": now + timedelta(seconds=30), "agent_id": None, "lease_id": None,
                  "lease_expires_at": None, "error": body.error or None}
    res = await db.print_jobs.update_one({"id": job_id, "lease_id": body.lease_id, "status": job["status"]},
                                         {"$set": {**update, "updated_at": now}})
    if not res.modified_count:
        raise HTTPException(status_code=409, detail="Le travail a changé entre-temps")
    if body.status in ("printed", "failed"):
        await audit(f"job.{body.status}", org_id=a.org_id, actor=f"agent:{a.name}", resource_type="print_job",
                    resource_id=job_id, details={"code": job["order_code"], "printer": job["printer_name"], "error": body.error})
    if body.status == "printed":
        await maybe_complete_order(job["order_id"], a.org_id, f"Agent {a.name}", request_origin(request))
    return AgentReportOut(job_id=job_id, status=update["status"])


@router.get("/jobs/{job_id}/file")
async def job_file(job_id: str, lease: str, a: AgentPrincipal = Depends(get_agent)):
    """The document of a job this agent currently holds — reduced to the pages the customer selected."""
    job = await db.print_jobs.find_one({"id": job_id, "org_id": a.org_id, "agent_id": a.agent_id, "lease_id": lease,
                                        "status": {"$in": ["claimed", "printing"]}}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Travail introuvable ou bail expiré")
    doc = await db.documents.find_one({"id": job["document_id"], "org_id": a.org_id}, {"_id": 0})
    if not doc or not doc.get("storage_key"):
        raise HTTPException(status_code=404, detail="Document supprimé")
    try:
        data = await read_file(doc["storage_key"])
    except (StorageError, OSError) as exc:
        raise HTTPException(status_code=404, detail="Fichier supprimé") from exc
    if doc["kind"] == "pdf":
        pages = parse_page_range(job["options"].get("page_range", ""), doc["page_count"])
        if len(pages) < doc["page_count"]:
            data = extract_pages(data, pages)
    await audit("job.file", org_id=a.org_id, resource_type="print_job", resource_id=job_id, actor=f"agent:{a.name}",
                details={"pages": job["options"].get("page_range", "") or "toutes"})
    return Response(data, media_type=MEDIA_TYPES[doc["kind"]], headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/scan-sessions/{session_id}/pages")
async def agent_scan_page(session_id: str, file: UploadFile = File(...), a: AgentPrincipal = Depends(get_agent)):
    """One scanned page from the counter PC (stored at once: never lost if the browser disconnects)."""
    from routers.counter import add_page
    s = await db.scan_sessions.find_one({"id": session_id, "org_id": a.org_id, "shop_id": a.shop_id, "agent_id": a.agent_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session de scan inconnue")
    page = await add_page(s, await file.read(15 * 1024 * 1024 + 1), f"agent:{a.name}")
    return {"ok": True, "index": page["index"]}
