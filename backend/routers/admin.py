"""PrintDrop super-admin (platform scope only). Sees aggregate counts per organization and can
suspend/reactivate or change plan — it has no access to tenant documents or customer data."""

import hashlib
import re

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from urllib.parse import urlparse

from lib.agent_release import RELEASE_ID, VERSION_RE, get_release
from lib.storage import delete_file, save_file
from lib.authz import Principal, audit, now_utc, require_platform
from lib.billing import subscription_view
from lib.db import db
from models.schemas import AdminOrgOut, AdminOrgUpdateIn, AdminStatsOut, AgentReleaseIn, AgentReleaseOut, AuditOut, ContactMessageOut, ContactMessageUpdateIn

router = APIRouter(prefix="/admin", tags=["admin"])


async def _group(coll: str, field: str = "org_id", sum_field: str | None = None) -> dict[str, int]:
    acc = {"$sum": f"${sum_field}"} if sum_field else {"$sum": 1}
    rows = await db[coll].aggregate([{"$group": {"_id": f"${field}", "v": acc}}]).to_list(10000)
    return {r["_id"]: r["v"] for r in rows}


@router.get("/stats", response_model=AdminStatsOut)
async def stats(_: Principal = Depends(require_platform("platform:read"))):
    revenue = await db.payments.aggregate([{"$group": {"_id": None, "t": {"$sum": "$amount_cents"}}}]).to_list(1)
    return AdminStatsOut(
        organizations=await db.organizations.count_documents({}),
        active_organizations=await db.organizations.count_documents({"status": "active"}),
        shops=await db.shops.count_documents({}),
        users=await db.users.count_documents({"platform_role": None}),
        orders=await db.orders.count_documents({}),
        revenue_cents=revenue[0]["t"] if revenue else 0,
    )


async def _org_rows(orgs: list[dict]) -> list[AdminOrgOut]:
    shops, orders, revenue = await _group("shops"), await _group("orders"), await _group("payments", sum_field="amount_cents")
    owners = {u["id"]: u["email"] for u in await db.users.find(
        {"id": {"$in": [o["owner_id"] for o in orgs]}}, {"_id": 0, "id": 1, "email": 1}).to_list(10000)}
    return [AdminOrgOut(
        id=o["id"], name=o["name"], status=o["status"], plan=o.get("plan", ""), subscription=await subscription_view(o),
        owner_email=owners.get(o["owner_id"], "—"),
        shops_count=shops.get(o["id"], 0), orders_count=orders.get(o["id"], 0),
        revenue_cents=revenue.get(o["id"], 0), created_at=o["created_at"],
    ) for o in orgs]


@router.get("/organizations", response_model=list[AdminOrgOut])
async def organizations(_: Principal = Depends(require_platform("platform:read"))):
    orgs = await db.organizations.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return await _org_rows(orgs)


@router.patch("/organizations/{org_id}", response_model=AdminOrgOut)
async def update_org(org_id: str, body: AdminOrgUpdateIn, p: Principal = Depends(require_platform("platform:manage"))):
    changes = body.model_dump(exclude_none=True)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation introuvable")
    if changes:
        await db.organizations.update_one({"id": org_id}, {"$set": changes})
        await audit("platform.org_update", principal=p, org_id=org_id, resource_type="organization",
                    resource_id=org_id, details=changes)
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    assert org
    return (await _org_rows([org]))[0]


@router.get("/audit", response_model=list[AuditOut])
async def platform_audit(_: Principal = Depends(require_platform("platform:read"))):
    return await db.audit_logs.find(
        {"action": {"$regex": r"^(platform\.|org\.register|authz\.denied|auth\.login_failed)"}}, {"_id": 0}
    ).sort("at", -1).to_list(200)


@router.get("/agent-release", response_model=AgentReleaseOut)
async def agent_release(_: Principal = Depends(require_platform("platform:read"))):
    return await get_release()


@router.put("/agent-release", response_model=AgentReleaseOut)
async def set_agent_release(body: AgentReleaseIn, p: Principal = Depends(require_platform("platform:manage"))):
    url = body.url.strip()
    if url:
        u = urlparse(url)
        if u.scheme != "https" or not u.netloc:
            raise HTTPException(status_code=422, detail="Le lien doit commencer par https://")
        if not u.path.lower().endswith(".exe"):
            raise HTTPException(status_code=422, detail="Le lien doit pointer directement vers le fichier .exe de l'installateur")
    doc = {"id": RELEASE_ID, "url": url, "version": body.version, "notes": body.notes.strip(), "updated_at": now_utc()}
    current = await db.platform_settings.find_one({"id": RELEASE_ID}, {"_id": 0}) or {}
    if current.get("file_key") and current.get("version") and VERSION_RE.match(current["version"]) and body.version != current["version"]:
        raise HTTPException(status_code=422, detail=f"La version doit rester {current['version']} : c'est celle de l'installateur hébergé. Envoyez le nouvel installateur pour changer de version.")
    await db.platform_settings.update_one({"id": RELEASE_ID}, {"$set": doc}, upsert=True)
    await audit("platform.agent_release", principal=p, resource_type="agent_release",
                resource_id=RELEASE_ID, details={"url": url, "version": body.version})
    return await get_release()


INSTALLER_MAX = 150 * 1024 * 1024


@router.post("/agent-release/upload", response_model=AgentReleaseOut)
async def upload_agent_installer(file: UploadFile = File(...), version: str = Query(default="", max_length=20),
                                 notes: str = Query(default="", max_length=500), p: Principal = Depends(require_platform("platform:manage"))):
    """Hosts the installer built by GitHub Actions on printdrop.fr. Only a real Inno Setup Windows installer is accepted;
    the download button appears for shops only once this upload succeeds."""
    data = await file.read(INSTALLER_MAX + 1)
    if len(data) > INSTALLER_MAX:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (150 Mo maximum)")
    if len(data) < 1024 * 1024 or data[:2] != b"MZ":
        raise HTTPException(status_code=422, detail="Ce fichier n'est pas un programme Windows (.exe) complet")
    if b"Inno Setup" not in data and b"NullsoftInst" not in data:
        raise HTTPException(status_code=422, detail="Ce fichier n'est pas l'installateur PrintDrop : utilisez PrintDrop-Setup-x.y.z.exe produit par GitHub Actions")
    if not version:
        m = re.search(r"(\d+\.\d+\.\d+)", file.filename or "")
        version = m.group(1) if m else ""
    if not VERSION_RE.match(version):
        raise HTTPException(status_code=422, detail="Indiquez la version de l'installateur (ex : 0.4.0)")
    key = await save_file("platform", "platform", data, "exe")
    old = await db.platform_settings.find_one({"id": RELEASE_ID}, {"_id": 0}) or {}
    doc = {"id": RELEASE_ID, "file_key": key, "filename": f"PrintDrop-Setup-{version}.exe", "sha256": hashlib.sha256(data).hexdigest(),
           "size_bytes": len(data), "version": version, "notes": (notes or old.get("notes", "")).strip(), "updated_at": now_utc()}
    await db.platform_settings.update_one({"id": RELEASE_ID}, {"$set": doc}, upsert=True)
    if old.get("file_key") and old["file_key"] != key and not old["file_key"].startswith("bundled:"):
        await delete_file(old["file_key"])
    await audit("platform.agent_installer_upload", principal=p, resource_type="agent_release", resource_id=RELEASE_ID,
                details={"version": version, "sha256": doc["sha256"], "size": len(data)})
    return await get_release()


@router.delete("/agent-release/file", response_model=AgentReleaseOut)
async def remove_agent_installer(p: Principal = Depends(require_platform("platform:manage"))):
    old = await db.platform_settings.find_one({"id": RELEASE_ID}, {"_id": 0}) or {}
    if old.get("file_key") and not old["file_key"].startswith("bundled:"):
        await delete_file(old["file_key"])
    await db.platform_settings.update_one({"id": RELEASE_ID}, {"$set": {"file_key": "", "filename": "", "sha256": "", "size_bytes": 0, "updated_at": now_utc()}})
    await audit("platform.agent_installer_remove", principal=p, resource_type="agent_release", resource_id=RELEASE_ID, details={})
    return await get_release()


@router.get("/contact-messages", response_model=list[ContactMessageOut])
async def contact_messages(_: Principal = Depends(require_platform("platform:read"))):
    """Contact & demo requests from the public site (also e-mailed to CONTACT_EMAIL when possible)."""
    return await db.contact_messages.find({}, {"_id": 0, "ip": 0}).sort("created_at", -1).to_list(300)


@router.patch("/contact-messages/{message_id}", response_model=ContactMessageOut)
async def update_contact_message(message_id: str, body: ContactMessageUpdateIn, p: Principal = Depends(require_platform("platform:manage"))):
    res = await db.contact_messages.update_one({"id": message_id}, {"$set": {"handled": body.handled, "handled_at": now_utc() if body.handled else None}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Message introuvable")
    await audit("platform.contact_handled", principal=p, resource_type="contact_message", resource_id=message_id, details={"handled": body.handled})
    return await db.contact_messages.find_one({"id": message_id}, {"_id": 0, "ip": 0})
