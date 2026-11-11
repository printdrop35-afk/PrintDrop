"""Agent (organization) self-service: company phone + registration number, and AI-document usage this month."""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from lib.authz import Principal, audit, require_tenant
from lib.db import db
from models.schemas import AiDocUsageOut, OrgProfileIn, OrgProfileOut

router = APIRouter(prefix="/org", tags=["org"])


def month_start_utc() -> datetime:
    """First day of the current month at 00:00 in APP_TZ, as UTC (server-anchored, never browser dates)."""
    now = datetime.now(ZoneInfo(os.environ.get("APP_TZ", "UTC")))
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


@router.get("/profile", response_model=OrgProfileOut)
async def get_profile(p: Principal = Depends(require_tenant("shop:read"))):
    org = await db.organizations.find_one({"id": p.org_id}, {"_id": 0, "phone": 1, "siret": 1})
    return OrgProfileOut(phone=(org or {}).get("phone", ""), siret=(org or {}).get("siret", ""))


@router.patch("/profile", response_model=OrgProfileOut)
async def update_profile(body: OrgProfileIn, p: Principal = Depends(require_tenant("billing:manage"))):
    changes = {"phone": body.phone.strip(), "siret": body.siret.replace(" ", "")}
    res = await db.organizations.update_one({"id": p.org_id}, {"$set": changes})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Organisation introuvable")
    await audit("org.profile_update", principal=p, resource_type="organization", resource_id=p.org_id or "", details=changes)
    return OrgProfileOut(**changes)


@router.get("/ai-docs/usage", response_model=AiDocUsageOut)
async def ai_usage(p: Principal = Depends(require_tenant("orders:read"))):
    start = month_start_utc()
    docs = await db.documents.find({"org_id": p.org_id, "source": "ai", "created_at": {"$gte": start}},
                                   {"_id": 0, "order_id": 1}).to_list(100000)
    order_ids = [d["order_id"] for d in docs if d.get("order_id")]
    printed = await db.orders.count_documents({"org_id": p.org_id, "id": {"$in": order_ids}, "status": {"$in": ["ready", "picked_up"]}}) if order_ids else 0
    printed_docs = 0
    if printed:
        done = {o["id"] for o in await db.orders.find({"org_id": p.org_id, "id": {"$in": order_ids}, "status": {"$in": ["ready", "picked_up"]}},
                                                      {"_id": 0, "id": 1}).to_list(100000)}
        printed_docs = sum(1 for d in docs if d.get("order_id") in done)
    return AiDocUsageOut(created=len(docs), in_orders=len(order_ids), printed=printed_docs, since=start)
