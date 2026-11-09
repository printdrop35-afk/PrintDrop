"""Café dashboard (owner / manager / operator). Every query goes through TenantRepo, so a
resource from another organization is simply invisible (404), never 403."""

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from lib.authz import ROLE_RANK, Principal, TenantRepo, audit, now_utc, request_origin, require_tenant, tenant_repo
from lib.notify import NotifyError, enqueue_ready, resend_email, resend_sms, send_email, send_sms, to_e164, twilio_configured
from lib.retention import purge_order
from lib.billing import enforce_limit
from lib.platform import shop_vat_bp
from lib.pricing import PAPER_LABELS, SERVICE_CATEGORIES, UNIT_LABELS, ht_from_ttc, new_id
from lib.db import db
from lib.security import hash_password
from models.schemas import (
    AuditOut, DocumentHealthOut, DownloadLinkOut, OrderDocumentsHealthOut, OrderOut, OrderPayIn, ResendRequestOut, OrderStatusIn, Pricing, ShopCreateIn, ShopOut,
    ShopStatsOut, ShopUpdateIn, StaffCreateIn, StaffOut, StaffUpdateIn,
)
from routers.auth import new_shop_doc, unique_slug

from typing import Literal
from lib.storage import MEDIA_TYPES, StorageError, extract_pages, file_exists, read_file
from lib.pricing import parse_page_range
import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

BUSINESS_TZ = ZoneInfo("Europe/Paris")
TRANSITIONS: dict[str, set[str]] = {
    "pending": {"printing", "ready", "cancelled"},
    "printing": {"ready", "pending", "cancelled"},
    "ready": {"picked_up", "printing", "cancelled"},
    "picked_up": set(),
    "delivered": set(),  # set automatically on the customer's first scan download
    "cancelled": set(),
}


async def get_shop_or_404(repo: TenantRepo, shop_id: str) -> dict:
    shop = await repo.find_one("shops", {"id": shop_id})
    if not shop:
        raise HTTPException(status_code=404, detail="Boutique introuvable")
    return shop


async def get_order_or_404(repo: TenantRepo, order_id: str) -> dict:
    order = await repo.find_one("orders", {"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    return order


# ---------- shops ----------
@router.get("/shops", response_model=list[ShopOut])
async def list_shops(p: Principal = Depends(require_tenant("shop:read"))):
    return await tenant_repo(p).find("shops", sort=[("created_at", 1)])


@router.post("/shops", response_model=ShopOut)
async def create_shop(body: ShopCreateIn, p: Principal = Depends(require_tenant("shop:create"))):
    await enforce_limit(p.org_id or "", "shops")
    repo = tenant_repo(p)
    doc = new_shop_doc(p.org_id or "", body.name.strip(), body.city.strip(), body.address.strip(), await unique_slug(body.name))
    doc = await repo.insert("shops", doc)
    await audit("shop.create", principal=p, resource_type="shop", resource_id=doc["id"], details={"name": doc["name"]})
    return doc


@router.patch("/shops/{shop_id}", response_model=ShopOut)
async def update_shop(shop_id: str, body: ShopUpdateIn, p: Principal = Depends(require_tenant("shop:edit"))):
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    changes = body.model_dump(exclude_none=True)
    if changes:
        await repo.update_one("shops", {"id": shop_id}, {"$set": changes})
        await audit("shop.update", principal=p, resource_type="shop", resource_id=shop_id, details=changes)
    return await get_shop_or_404(repo, shop_id)


@router.put("/shops/{shop_id}/pricing", response_model=ShopOut)
async def update_pricing(shop_id: str, body: Pricing, p: Principal = Depends(require_tenant("pricing:edit"))):
    repo = tenant_repo(p)
    before = await get_shop_or_404(repo, shop_id)
    data = body.model_dump()
    for coll in ("services", "rules", "discounts"):
        for item in data[coll]:
            item["id"] = item["id"] or new_id()  # ids are server-assigned
    await repo.update_one("shops", {"id": shop_id}, {"$set": {"pricing": data}})
    await audit("pricing.update", principal=p, resource_type="shop", resource_id=shop_id,
                details={"before": before["pricing"], "after": body.model_dump()})
    return await get_shop_or_404(repo, shop_id)


def _eur(cents: int) -> str:
    return f"{cents / 100:.2f}".replace(".", ",")


@router.get("/shops/{shop_id}/pricing/export")
async def export_pricing(shop_id: str, p: Principal = Depends(require_tenant("shop:read"))):
    """Price list as CSV (Excel-friendly: UTF-8 BOM, semicolon separator), TTC and HT."""
    shop = await get_shop_or_404(tenant_repo(p), shop_id)
    pr, vat = shop["pricing"], await shop_vat_bp()
    rows = [["Catégorie", "Prestation", "Unité", "Prix TTC (€)", "Prix HT (€)", "TVA (%)", "Statut"]]
    status = lambda active: "Actif" if active else "Désactivé"  # noqa: E731
    for size, c in pr["print"].items():
        for mode, label in (("bw", "N&B"), ("color", "Couleur")):
            rows.append(["Impression", f"{PAPER_LABELS[size]} {label} recto", "page", _eur(c[mode]), _eur(ht_from_ttc(c[mode], vat)), f"{vat / 100:g}", status(c.get("active", True))])
    rows.append(["Impression", f"Remise recto-verso", "%", f"{pr['duplex_discount_pct']}", "", "", "Actif"])
    for mode, label in (("bw", "N&B"), ("color", "Couleur")):
        c = pr["photocopy"][mode]
        rows.append(["Photocopie", f"Photocopie {label}", "page", _eur(c), _eur(ht_from_ttc(c, vat)), f"{vat / 100:g}", status(pr["photocopy"].get("active", True))])
    rows.append(["Numérisation", "Scan", "page", _eur(pr["scan_cents"]), _eur(ht_from_ttc(pr["scan_cents"], vat)), f"{vat / 100:g}", "Actif"])
    for svc in pr.get("services", []):
        price = ("à partir de " if svc.get("price_from") else "") + _eur(svc["price_cents"])
        rows.append([SERVICE_CATEGORIES[svc["category"]], svc["name"], UNIT_LABELS[svc["unit"]], price, _eur(ht_from_ttc(svc["price_cents"], vat)), f"{vat / 100:g}", status(svc.get("active", True))])
    for r in pr.get("rules", []):
        rows.append(["Règle", r["name"], f"dès {r['min_pages']} pages", f"-{r['discount_pct']} %", "", "", status(r.get("active", True))])
    for d in pr.get("discounts", []):
        val = f"-{d['value']} %" if d["kind"] == "percent" else f"-{_eur(d['value'])}"
        rows.append(["Remise", d["name"] + (f" (code {d['code']})" if d.get("code") else " (automatique)"), f"dès {_eur(d.get('min_order_cents', 0))} €", val, "", "", status(d.get("active", True))])
    rows.append(["Minimum", "Montant minimum de commande", "commande", _eur(pr.get("min_order_cents", 0)), _eur(ht_from_ttc(pr.get("min_order_cents", 0), vat)), f"{vat / 100:g}", "Actif"])
    csv = "\ufeff" + "\r\n".join(";".join('"' + str(v).replace('"', '""') + '"' for v in row) for row in rows)
    await audit("pricing.export", principal=p, resource_type="shop", resource_id=shop_id)
    return Response(csv, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="tarifs-{shop["slug"]}.csv"'})


@router.post("/shops/{shop_id}/pricing/copy-from/{source_id}", response_model=ShopOut)
async def copy_pricing(shop_id: str, source_id: str, p: Principal = Depends(require_tenant("pricing:edit"))):
    repo = tenant_repo(p)
    target = await get_shop_or_404(repo, shop_id)
    source = await get_shop_or_404(repo, source_id)  # both inside the caller's tenant
    await repo.update_one("shops", {"id": shop_id}, {"$set": {"pricing": source["pricing"]}})
    await audit("pricing.copy", principal=p, resource_type="shop", resource_id=shop_id,
                details={"from": source_id, "before": target["pricing"]})
    return await get_shop_or_404(repo, shop_id)


@router.get("/shops/{shop_id}/stats", response_model=ShopStatsOut)
async def shop_stats(shop_id: str, p: Principal = Depends(require_tenant("orders:read"))):
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    start = datetime.combine(datetime.now(BUSINESS_TZ).date(), time.min, tzinfo=BUSINESS_TZ)
    counts = {s: await repo.count("orders", {"shop_id": shop_id, "status": s}) for s in ("pending", "printing", "ready")}
    paid = await repo.aggregate("payments", [
        {"$match": {"shop_id": shop_id, "created_at": {"$gte": start}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}}},
    ])
    unpaid = await repo.aggregate("orders", [
        {"$match": {"shop_id": shop_id, "payment_status": "unpaid", "status": {"$ne": "cancelled"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_cents"}}},
    ])
    return ShopStatsOut(
        orders_today=await repo.count("orders", {"shop_id": shop_id, "created_at": {"$gte": start}}),
        revenue_today_cents=paid[0]["total"] if paid else 0,
        unpaid_cents=unpaid[0]["total"] if unpaid else 0,
        **counts,
    )


# ---------- orders ----------
@router.get("/shops/{shop_id}/orders", response_model=list[OrderOut])
async def list_orders(shop_id: str, status: str | None = None, p: Principal = Depends(require_tenant("orders:read"))):
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    f: dict = {"shop_id": shop_id}
    if status == "active":
        f["status"] = {"$in": ["pending", "printing", "ready"]}
    elif status in TRANSITIONS:
        f["status"] = status
    return await repo.find("orders", f, sort=[("created_at", -1)], limit=300)


@router.get("/shops/{shop_id}/orders/by-code/{code}", response_model=OrderOut)
async def order_by_code(shop_id: str, code: str, p: Principal = Depends(require_tenant("orders:read"))):
    """Counter scan: the in-progress order of THIS shop with this code (else the most recent one)."""
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    c = code.strip().upper()
    found = (await repo.find("orders", {"shop_id": shop_id, "code": c, "status": {"$in": ["pending", "printing", "ready"]}}, limit=1)
             or await repo.find("orders", {"shop_id": shop_id, "code": c}, sort=[("created_at", -1)], limit=1))
    if not found:
        raise HTTPException(status_code=404, detail="Aucune commande avec ce code dans cette boutique")
    return found[0]


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: str, p: Principal = Depends(require_tenant("orders:read"))):
    return await get_order_or_404(tenant_repo(p), order_id)


@router.post("/orders/{order_id}/status", response_model=OrderOut)
async def change_status(order_id: str, body: OrderStatusIn, request: Request, p: Principal = Depends(require_tenant("orders:update"))):
    repo = tenant_repo(p)
    order = await get_order_or_404(repo, order_id)
    current, target = order["status"], body.status
    if target not in TRANSITIONS[current]:
        raise HTTPException(status_code=409, detail=f"Transition impossible : {current} → {target}")
    if target == "picked_up" and order["payment_status"] == "unpaid":
        raise HTTPException(status_code=409, detail="Encaissez la commande avant de la marquer comme retirée")
    # authenticated staff complete orders from the dashboard: no customer code is asked (tenant scope = authorization)
    now = now_utc()
    matched = await repo.update_one("orders", {"id": order_id, "status": current}, {
        "$set": {"status": target, "updated_at": now},
        "$push": {"history": {"status": target, "at": now, "by": p.name}},
        **({"$unset": {"active_code": ""}} if target in ("picked_up", "cancelled") else {}),
    })
    if not matched:
        raise HTTPException(status_code=409, detail="La commande a été modifiée entre-temps, rechargez")
    await audit("order.status", principal=p, resource_type="order", resource_id=order_id,
                details={"code": order["code"], "from": current, "to": target})
    updated = await get_order_or_404(repo, order_id)
    # a status change never prints: printing only happens through an explicit, confirmed « Imprimer » action
    if target == "ready":
        await enqueue_ready(updated, request_origin(request))
    elif target == "cancelled":
        await repo.update_many("print_jobs", {"order_id": order_id, "status": {"$in": ["queued", "claimed"]}},
                               {"$set": {"status": "cancelled", "updated_at": now}})
    if target in ("picked_up", "cancelled"):  # retention: delete the document files right away (order data kept)
        await purge_order(order_id)
        updated = await get_order_or_404(repo, order_id)
    return updated


@router.post("/orders/{order_id}/pay", response_model=OrderOut)
async def record_counter_payment(order_id: str, body: OrderPayIn, p: Principal = Depends(require_tenant("orders:pay"))):
    repo = tenant_repo(p)
    order = await get_order_or_404(repo, order_id)
    if order["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="Commande annulée")
    now = now_utc()
    # Atomic guard: only the first request flips unpaid -> paid; the amount comes from the stored order.
    matched = await repo.update_one("orders", {"id": order_id, "payment_status": "unpaid"}, {
        "$set": {"payment_status": "paid_counter", "payment_method": body.method, "paid_at": now, "updated_at": now},
    })
    if not matched:
        raise HTTPException(status_code=409, detail="Commande déjà payée")
    await repo.insert("payments", {
        "id": str(uuid.uuid4()), "shop_id": order["shop_id"], "order_id": order_id, "amount_cents": order["total_cents"],
        "currency": "EUR", "method": body.method, "source": "counter", "recorded_by": p.user_id, "created_at": now,
    })
    await audit("payment.counter", principal=p, resource_type="order", resource_id=order_id,
                details={"code": order["code"], "amount_cents": order["total_cents"], "method": body.method})
    return await get_order_or_404(repo, order_id)


async def _documents_health(repo: TenantRepo, order: dict) -> list[DocumentHealthOut]:
    out = []
    for line in order["lines"]:
        if line.get("kind") != "print" or not line.get("document_id"):
            continue
        doc = await repo.find_one("documents", {"id": line["document_id"], "order_id": order["id"]})
        ok = bool(doc and doc.get("status") != "purged" and await file_exists(doc.get("storage_key")))
        out.append(DocumentHealthOut(document_id=line["document_id"], available=ok))
    return out


@router.get("/orders/{order_id}/documents/health", response_model=OrderDocumentsHealthOut)
async def documents_health(order_id: str, p: Principal = Depends(require_tenant("documents:read"))):
    """Is each document's file really in storage? Lets staff spot files lost before the durable-storage fix."""
    repo = tenant_repo(p)
    order = await get_order_or_404(repo, order_id)
    if order.get("purged_at"):
        return OrderDocumentsHealthOut(documents=[], resend_requested_at=order.get("resend_requested_at"))
    return OrderDocumentsHealthOut(documents=await _documents_health(repo, order), resend_requested_at=order.get("resend_requested_at"))


@router.post("/orders/{order_id}/request-resend", response_model=ResendRequestOut)
async def request_resend(order_id: str, request: Request, p: Principal = Depends(require_tenant("orders:update"))):
    """Ask the customer (e-mail and/or SMS) to send again a document whose file was lost. Returns the upload link
    so staff can also pass it on by phone when the customer left no contact."""
    repo = tenant_repo(p)
    order = await get_order_or_404(repo, order_id)
    if order["status"] in ("picked_up", "cancelled") or order.get("purged_at"):
        raise HTTPException(status_code=409, detail="Commande terminée")
    if all(d.available for d in await _documents_health(repo, order)):
        raise HTTPException(status_code=409, detail="Les documents de cette commande sont disponibles")
    shop = await repo.find_one("shops", {"id": order["shop_id"]})
    base = (order.get("public_origin") or request_origin(request)).rstrip("/")
    link = f"{base}/s/{shop['slug'] if shop else ''}"
    sent_email = sent_sms = False
    if order.get("customer_email"):
        try:
            subject, html = resend_email(order, link)
            await send_email(to=order["customer_email"], subject=subject, html=html)
            sent_email = True
        except (NotifyError, ValueError) as exc:
            logger.warning("request_resend email for %s: %s", order_id, exc)
    e164 = to_e164(order.get("customer_phone") or "") if order.get("customer_phone") else None
    if e164 and twilio_configured():
        try:
            await send_sms(to=e164, body=resend_sms(order, link))
            sent_sms = True
        except NotifyError as exc:
            logger.warning("request_resend sms for %s: %s", order_id, exc)
    now = now_utc()
    await repo.update_one("orders", {"id": order_id}, {"$set": {"resend_requested_at": now, "updated_at": now}})
    await audit("order.resend_requested", principal=p, resource_type="order", resource_id=order_id,
                details={"code": order["code"], "email": sent_email, "sms": sent_sms})
    return ResendRequestOut(sent_email=sent_email, sent_sms=sent_sms, upload_url=link, resend_requested_at=now)


@router.post("/orders/{order_id}/documents/{doc_id}/link", response_model=DownloadLinkOut)
async def document_link(order_id: str, doc_id: str, p: Principal = Depends(require_tenant("documents:read"))):
    repo = tenant_repo(p)
    await get_order_or_404(repo, order_id)
    doc = await repo.find_one("documents", {"id": doc_id, "order_id": order_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return DownloadLinkOut(url=f"/api/orders/{order_id}/documents/{doc_id}/file?variant=original&disposition=attachment", expires_at=0)


@router.get("/orders/{order_id}/documents/{doc_id}/file")
async def document_file(order_id: str, doc_id: str, variant: Literal["original", "print"] = "print",
                        disposition: Literal["attachment", "inline"] = "attachment",
                        p: Principal = Depends(require_tenant("documents:read"))):
    """Staff-only (session cookie) access. 'print' = PDF with only the customer's selected pages, built in memory.
    Downloading/viewing never creates a print job."""
    repo = tenant_repo(p)
    order = await get_order_or_404(repo, order_id)
    doc = await repo.find_one("documents", {"id": doc_id, "order_id": order_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    if doc.get("status") == "purged" or not doc.get("storage_key"):
        raise HTTPException(status_code=410, detail="Document supprimé après le retrait de la commande")
    try:
        data = await read_file(doc["storage_key"])
    except (StorageError, OSError) as exc:
        logger.error("document_file: stored file missing for document %s of order %s (%s)", doc_id, order_id, doc["storage_key"])
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur — demandez au client de renvoyer son document") from exc
    line = next((l for l in order["lines"] if l.get("document_id") == doc_id), None)
    base = (doc.get("filename") or "document").rsplit(".", 1)[0][:80]
    name, media = f"{base}.{doc['kind']}", MEDIA_TYPES[doc["kind"]]
    if variant == "print" and doc["kind"] == "pdf" and line:
        try:
            pages = parse_page_range((line.get("options") or {}).get("page_range", ""), doc["page_count"])
            if pages != list(range(1, doc["page_count"] + 1)):
                data = extract_pages(data, pages)
        except Exception as exc:
            logger.exception("print-ready PDF failed for %s", doc_id)
            raise HTTPException(status_code=422, detail="Impossible de préparer le PDF des pages demandées") from exc
        name = f"{base} - pages {','.join(map(str, pages))}.pdf" if len(pages) < doc["page_count"] else name
    await audit("document.download" if disposition == "attachment" else "document.view", principal=p, resource_type="document",
                resource_id=doc_id, details={"order_id": order_id, "variant": variant})
    from urllib.parse import quote
    return Response(data, media_type=media, headers={
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(name)}",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


# ---------- staff ----------
@router.get("/staff", response_model=list[StaffOut])
async def list_staff(p: Principal = Depends(require_tenant("staff:read"))):
    repo = tenant_repo(p)
    out = []
    for m in await repo.find("memberships", sort=[("created_at", 1)]):
        u = await db.users.find_one({"id": m["user_id"]}, {"_id": 0, "name": 1, "email": 1})
        if u:
            out.append(StaffOut(membership_id=m["id"], user_id=m["user_id"], name=u["name"], email=u["email"],
                                role=m["role"], active=m["active"], created_at=m["created_at"]))
    return out


@router.post("/staff", response_model=StaffOut)
async def create_staff(body: StaffCreateIn, p: Principal = Depends(require_tenant("staff:manage"))):
    await enforce_limit(p.org_id or "", "staff")
    if ROLE_RANK[body.role] >= ROLE_RANK[p.tenant_role or "operator"]:
        raise HTTPException(status_code=403, detail="Vous ne pouvez pas attribuer ce rôle")
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email")
    now = now_utc()
    user_id = str(uuid.uuid4())
    await db.users.insert_one({
        "id": user_id, "email": email, "name": body.name.strip(), "password_hash": hash_password(body.password),
        "platform_role": None, "active": True, "created_at": now,
    })
    m = await tenant_repo(p).insert("memberships", {
        "id": str(uuid.uuid4()), "user_id": user_id, "role": body.role, "active": True, "created_at": now,
    })
    await audit("staff.create", principal=p, resource_type="membership", resource_id=m["id"],
                details={"email": email, "role": body.role})
    return StaffOut(membership_id=m["id"], user_id=user_id, name=body.name.strip(), email=email,
                    role=body.role, active=True, created_at=now)


@router.patch("/staff/{membership_id}", response_model=StaffOut)
async def update_staff(membership_id: str, body: StaffUpdateIn, p: Principal = Depends(require_tenant("staff:manage"))):
    repo = tenant_repo(p)
    m = await repo.find_one("memberships", {"id": membership_id})
    if not m:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    if m["role"] == "owner" or m["user_id"] == p.user_id:
        raise HTTPException(status_code=403, detail="Le propriétaire ne peut pas être modifié ici")
    changes = body.model_dump(exclude_none=True)
    if changes:
        await repo.update_one("memberships", {"id": membership_id}, {"$set": changes})
        await audit("staff.update", principal=p, resource_type="membership", resource_id=membership_id, details=changes)
    m = await repo.find_one("memberships", {"id": membership_id})
    assert m
    u = await db.users.find_one({"id": m["user_id"]}, {"_id": 0})
    assert u
    return StaffOut(membership_id=m["id"], user_id=m["user_id"], name=u["name"], email=u["email"],
                    role=m["role"], active=m["active"], created_at=m["created_at"])


# ---------- audit ----------
@router.get("/audit", response_model=list[AuditOut])
async def list_audit(p: Principal = Depends(require_tenant("audit:read"))):
    since = now_utc() - timedelta(days=30)
    return await tenant_repo(p).find("audit_logs", {"at": {"$gte": since}}, sort=[("at", -1)], limit=200)
