"""PrintDrop super-admin (platform scope only). Sees aggregate counts per organization and can
suspend/reactivate or change plan — it has no access to tenant documents or customer data."""

import hashlib
import re

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from urllib.parse import urlparse

from lib.agent_release import RELEASE_ID, VERSION_RE, get_release
from lib.storage import delete_file, save_file
from lib.authz import Principal, audit, now_utc, require_platform
from lib.billing import get_plan, printer_label, subscription_view
from lib.security import sign_file_link
from lib.db import db
from models.schemas import (AdminCustomerRow, AdminDocLinkOut, AdminDocRow, AdminOrderRow, AdminOrgDetailOut, AdminPaymentRow,
    AdminPaymentSummary, AdminShopRow, AdminStaffRow)
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
    docs, pays = await _group("documents"), await _group("payments")
    owners = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": [o["owner_id"] for o in orgs]}}, {"_id": 0, "id": 1, "email": 1, "name": 1, "phone": 1}).to_list(10000)}
    plans = {p["code"]: p for p in await db.plans.find({}, {"_id": 0}).to_list(100)}
    rows = []
    for o in orgs:
        owner = owners.get(o["owner_id"], {})
        plan = plans.get(((o.get("subscription") or {}).get("plan_code")) or o.get("plan", ""))
        rows.append(AdminOrgOut(
            id=o["id"], name=o["name"], status=o["status"], plan=o.get("plan", ""), subscription=await subscription_view(o),
            owner_email=owner.get("email", "—"), owner_name=owner.get("name", ""), owner_phone=owner.get("phone", "") or "",
            printer_plan=printer_label(plan),
            shops_count=shops.get(o["id"], 0), orders_count=orders.get(o["id"], 0),
            documents_count=docs.get(o["id"], 0), payments_count=pays.get(o["id"], 0),
            revenue_cents=revenue.get(o["id"], 0), created_at=o["created_at"],
        ))
    return rows


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


# ---------- one Agent (organization) in detail — super-admin only, every query scoped to that org_id ----------
@router.get("/organizations/{org_id}/details", response_model=AdminOrgDetailOut)
async def organization_details(org_id: str, p: Principal = Depends(require_platform("platform:read"))):
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation introuvable")
    scope = {"org_id": org_id}
    plan_label = printer_label(await get_plan(((org.get("subscription") or {}).get("plan_code")) or org.get("plan", "")))
    orders = await db.orders.find(scope, {"_id": 0}).sort("created_at", -1).to_list(1000)
    by_id = {o["id"]: o for o in orders}
    shops = await db.shops.find(scope, {"_id": 0}).sort("created_at", 1).to_list(200)
    members = await db.memberships.find(scope, {"_id": 0}).to_list(500)
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": [m["user_id"] for m in members]}}, {"_id": 0, "password_hash": 0}).to_list(500)}
    documents = await db.documents.find(scope, {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(1000)
    payments = await db.payments.find(scope, {"_id": 0}).sort("created_at", -1).to_list(1000)
    activity = await db.audit_logs.find(scope, {"_id": 0}).sort("at", -1).to_list(300)

    def plan_of(o: dict | None) -> str:
        return (o or {}).get("printer_plan") or plan_label

    def done_at(o: dict):
        ev = [h["at"] for h in o.get("history", []) if h.get("status") in ("picked_up", "delivered")]
        return ev[-1] if ev else None

    customers: dict[str, dict] = {}
    for o in sorted(orders, key=lambda x: x["created_at"]):
        k = (o.get("phone_digits") or o.get("customer_email") or o.get("customer_name") or "").lower()
        c = customers.setdefault(k, {"name": o.get("customer_name") or "", "email": o.get("customer_email") or "", "phone": o.get("customer_phone") or "",
                                     "first_order_at": o["created_at"], "orders_count": 0, "total_cents": 0, "order_codes": []})
        c["orders_count"] += 1
        c["total_cents"] += o.get("total_cents", 0)
        c["order_codes"].append(o["code"])
    pending = sum(1 for o in orders if o.get("payment_status") == "unpaid" and o.get("status") != "cancelled")
    await audit("platform.org_view", principal=p, org_id=org_id, resource_type="organization", resource_id=org_id)
    return AdminOrgDetailOut(
        org=(await _org_rows([org]))[0],
        shops=[AdminShopRow(**s) for s in shops],
        staff=[AdminStaffRow(name=users.get(m["user_id"], {}).get("name", ""), email=users.get(m["user_id"], {}).get("email", ""),
                             role=m["role"], active=m.get("active", False)) for m in members],
        documents=[AdminDocRow(
            id=d["id"], filename=d.get("filename") or "(sans nom)", kind=d.get("kind") or "",
            source="ai" if d.get("source") == "ai" else "scan" if d.get("source") == "scan" else "upload",
            customer=by_id.get(d.get("order_id") or "", {}).get("customer_name") or "—", created_at=d["created_at"],
            order_code=by_id.get(d.get("order_id") or "", {}).get("code"), printer_plan=plan_of(by_id.get(d.get("order_id") or "")),
            status=d.get("status", ""), viewable=bool(d.get("storage_key")),
        ) for d in documents],
        payments=[AdminPaymentRow(
            id=pay["id"], reference=pay["id"][:8].upper(), customer=by_id.get(pay.get("order_id") or "", {}).get("customer_name") or "—",
            created_at=pay["created_at"], amount_cents=pay.get("amount_cents", 0), method=pay.get("method", ""), status="succeeded",
            order_code=by_id.get(pay.get("order_id") or "", {}).get("code"), printer_plan=plan_of(by_id.get(pay.get("order_id") or "")),
        ) for pay in payments],
        payment_summary=AdminPaymentSummary(total=len(payments), succeeded=len(payments), pending=pending, failed=0, refunds=0,
                                            revenue_cents=sum(x.get("amount_cents", 0) for x in payments)),
        orders=[AdminOrderRow(
            id=o["id"], code=o["code"], customer=o.get("customer_name") or "",
            documents=[ln["filename"] for ln in o.get("lines") or [] if ln.get("filename")], printer_plan=plan_of(o),
            created_at=o["created_at"], total_cents=o.get("total_cents", 0), payment_status=o.get("payment_status", "unpaid"),
            status=o["status"], completed_at=done_at(o),
        ) for o in orders],
        customers=[AdminCustomerRow(**c) for c in sorted(customers.values(), key=lambda c: c["first_order_at"], reverse=True)],
        activity=[AuditOut(**a) for a in activity],
    )


@router.post("/organizations/{org_id}/documents/{doc_id}/link", response_model=AdminDocLinkOut)
async def organization_document_link(org_id: str, doc_id: str, p: Principal = Depends(require_platform("platform:read"))):
    """Authorized viewing: short-lived signed link, only for a document of THIS org, logged in the audit trail."""
    doc = await db.documents.find_one({"id": doc_id, "org_id": org_id}, {"_id": 0, "id": 1, "storage_key": 1, "filename": 1})
    if not doc or not doc.get("storage_key"):
        raise HTTPException(status_code=404, detail="Document introuvable ou déjà supprimé")
    exp, sig = sign_file_link(doc["id"])
    await audit("platform.document_view", principal=p, org_id=org_id, resource_type="document", resource_id=doc_id, details={"filename": doc["filename"]})
    return AdminDocLinkOut(url=f"/api/files/{doc['id']}?exp={exp}&sig={sig}")
