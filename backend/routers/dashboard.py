"""Café dashboard (owner / manager / operator). Every query goes through TenantRepo, so a
resource from another organization is simply invisible (404), never 403."""

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request

from lib.authz import ROLE_RANK, Principal, TenantRepo, audit, now_utc, request_origin, require_tenant, tenant_repo
from lib.notify import enqueue_ready
from lib.printing import enqueue_initial_jobs
from lib.db import db
from lib.security import hash_password, sign_file_link
from models.schemas import (
    AuditOut, DownloadLinkOut, OrderOut, OrderPayIn, OrderStatusIn, Pricing, ShopCreateIn, ShopOut,
    ShopStatsOut, ShopUpdateIn, StaffCreateIn, StaffOut, StaffUpdateIn,
)
from routers.auth import new_shop_doc, unique_slug

router = APIRouter(tags=["dashboard"])

BUSINESS_TZ = ZoneInfo("Europe/Paris")
TRANSITIONS: dict[str, set[str]] = {
    "pending": {"printing", "ready", "cancelled"},
    "printing": {"ready", "pending", "cancelled"},
    "ready": {"picked_up", "printing", "cancelled"},
    "picked_up": set(),
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
    await repo.update_one("shops", {"id": shop_id}, {"$set": {"pricing": body.model_dump()}})
    await audit("pricing.update", principal=p, resource_type="shop", resource_id=shop_id,
                details={"before": before["pricing"], "after": body.model_dump()})
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
    now = now_utc()
    matched = await repo.update_one("orders", {"id": order_id, "status": current}, {
        "$set": {"status": target, "updated_at": now},
        "$push": {"history": {"status": target, "at": now, "by": p.name}},
    })
    if not matched:
        raise HTTPException(status_code=409, detail="La commande a été modifiée entre-temps, rechargez")
    await audit("order.status", principal=p, resource_type="order", resource_id=order_id,
                details={"code": order["code"], "from": current, "to": target})
    updated = await get_order_or_404(repo, order_id)
    if target == "printing" and current == "pending":
        await enqueue_initial_jobs(updated, p.name)  # sent to the local agent, if one is paired
    elif target == "ready":
        await enqueue_ready(updated, request_origin(request))
    elif target == "cancelled":
        await repo.update_many("print_jobs", {"order_id": order_id, "status": {"$in": ["queued", "claimed"]}},
                               {"$set": {"status": "cancelled", "updated_at": now}})
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


@router.post("/orders/{order_id}/documents/{doc_id}/link", response_model=DownloadLinkOut)
async def document_link(order_id: str, doc_id: str, p: Principal = Depends(require_tenant("documents:read"))):
    repo = tenant_repo(p)
    await get_order_or_404(repo, order_id)
    doc = await repo.find_one("documents", {"id": doc_id, "order_id": order_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    exp, sig = sign_file_link(doc_id)
    await audit("document.link", principal=p, resource_type="document", resource_id=doc_id, details={"order_id": order_id})
    return DownloadLinkOut(url=f"/api/files/{doc_id}?exp={exp}&sig={sig}", expires_at=exp)


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
