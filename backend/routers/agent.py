"""API used by the PrintDrop Local Agent (Windows). Machine principal: one agent = one shop.
Auth: `Authorization: Bearer pda_…` (only a SHA-256 of the key is stored)."""

import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from lib.authz import audit, now_utc, request_origin
from lib.db import db
from lib.pricing import parse_page_range
from lib.printing import CLAIM_LEASE_SECONDS, PRINT_LEASE_SECONDS, maybe_complete_order
from lib.security import sha256, sign_file_link
from models.schemas import (
    AgentClaimOut, AgentHeartbeatIn, AgentHeartbeatOut, AgentJobOut, AgentPairIn, AgentPairOut, AgentReportIn, AgentReportOut,
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
    await db.agents.update_one({"id": a.agent_id}, {"$set": {"last_seen_at": now, "version": body.version}})
    has_default = bool(await db.printers.find_one({"org_id": a.org_id, "shop_id": a.shop_id, "is_default": True}, {"_id": 1}))
    seen = []
    for pr in body.printers:
        seen.append(pr.name)
        res = await db.printers.update_one(
            {"org_id": a.org_id, "agent_id": a.agent_id, "name": pr.name},
            {"$set": {"status": pr.status, "status_detail": pr.detail, "supports_color": pr.supports_color, "last_seen_at": now},
             "$setOnInsert": {"id": str(uuid.uuid4()), "shop_id": a.shop_id, "enabled": True,
                              "is_default": pr.is_default and not has_default}},
            upsert=True,
        )
        if res.upserted_id and pr.is_default:
            has_default = True
    await db.printers.update_many({"org_id": a.org_id, "agent_id": a.agent_id, "name": {"$nin": seen}},
                                  {"$set": {"status": "offline", "status_detail": "Non détectée par l'agent"}})
    shop = await db.shops.find_one({"id": a.shop_id}, {"_id": 0, "name": 1})
    return AgentHeartbeatOut(shop_name=shop["name"] if shop else "", poll_seconds=POLL_SECONDS)


@router.post("/jobs/claim", response_model=AgentClaimOut)
async def claim(a: AgentPrincipal = Depends(get_agent)):
    printers = await db.printers.find(
        {"org_id": a.org_id, "agent_id": a.agent_id, "enabled": True, "status": "online"}, {"_id": 0}
    ).sort("is_default", -1).to_list(50)
    if not printers:
        return AgentClaimOut(jobs=[], message="Aucune imprimante activée et en ligne sur ce poste")
    printer = printers[0]["name"]
    jobs: list[AgentJobOut] = []
    for _ in range(3):
        now = now_utc()
        lease_id = uuid.uuid4().hex
        job = await db.print_jobs.find_one_and_update(
            {"org_id": a.org_id, "shop_id": a.shop_id, "status": "queued"},
            {"$set": {"status": "claimed", "agent_id": a.agent_id, "lease_id": lease_id, "printer_name": printer,
                      "lease_expires_at": now + timedelta(seconds=CLAIM_LEASE_SECONDS), "updated_at": now}},
            sort=[("created_at", 1)], projection={"_id": 0}, return_document=True,
        )
        if not job:
            break
        doc = await db.documents.find_one({"id": job["document_id"], "org_id": a.org_id}, {"_id": 0})
        if not doc:
            await db.print_jobs.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": "Document supprimé"}})
            continue
        exp, sig = sign_file_link(doc["id"], ttl_seconds=CLAIM_LEASE_SECONDS)
        jobs.append(AgentJobOut(
            id=job["id"], lease_id=lease_id, order_code=job["order_code"], kind=job["kind"], filename=job["filename"],
            file_kind=doc["kind"], options=job["options"], pages=parse_page_range(job["options"].get("page_range", ""), doc["page_count"]),
            printer_name=printer, download_url=f"/api/files/{doc['id']}?exp={exp}&sig={sig}",
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
    allowed = {"printing": ["claimed"], "printed": ["claimed", "printing"], "failed": ["claimed", "printing"], "requeue": ["claimed"]}
    if job["status"] not in allowed[body.status]:
        raise HTTPException(status_code=409, detail=f"Transition impossible : {job['status']} → {body.status}")
    if body.status == "printing":
        update = {"status": "printing", "lease_expires_at": now + timedelta(seconds=PRINT_LEASE_SECONDS)}
    elif body.status == "printed":
        update = {"status": "printed", "printed_at": now, "error": None}
    elif body.status == "failed":
        update = {"status": "failed", "error": body.error or "Erreur d'impression"}
    else:
        update = {"status": "queued", "agent_id": None, "lease_id": None, "lease_expires_at": None, "error": body.error or None}
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
