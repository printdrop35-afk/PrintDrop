"""PrintDrop super-admin (platform scope only). Sees aggregate counts per organization and can
suspend/reactivate or change plan — it has no access to tenant documents or customer data."""

from fastapi import APIRouter, Depends, HTTPException

from lib.authz import Principal, audit, require_platform
from lib.db import db
from models.schemas import AdminOrgOut, AdminOrgUpdateIn, AdminStatsOut, AuditOut

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
        id=o["id"], name=o["name"], status=o["status"], plan=o["plan"], owner_email=owners.get(o["owner_id"], "—"),
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
