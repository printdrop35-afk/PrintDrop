"""Owner billing (plans, Stripe checkout, invoices), the Stripe webhook, the renewal cron and the
super-admin plan / settings / subscription management."""

import asyncio
import hmac
import json
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from lib.authz import Principal, audit, now_utc, request_origin, require_platform, require_tenant
from lib.billing import (
    create_checkout, get_plan, payment_mode, plan_out, subscription_view, sweep_subscriptions, sync_invoice_from_stripe,
)
from lib.db import db
from lib.platform import get_settings
from models.schemas import (
    AdminSubscriptionIn, BillingOverviewOut, CheckoutIn, CheckoutOut, InvoiceOut, PlanIn, PlanOut,
    PlatformSettingsIn, PlatformSettingsOut, SubscriptionOut,
)

router = APIRouter(tags=["billing"])
INVOICE_FIELDS = {"_id": 0, "checkout_url": 0, "provider_payment_id": 0}


async def all_plans(active_only: bool) -> list[dict]:
    vat = (await get_settings())["subscription_vat_rate_bp"]
    q = {"active": True} if active_only else {}
    return [plan_out(p, vat) for p in await db.plans.find(q, {"_id": 0}).sort("sort", 1).to_list(50)]


# ---------- owner ----------
@router.get("/billing", response_model=BillingOverviewOut)
async def overview(p: Principal = Depends(require_tenant("billing:manage"))):
    org = await db.organizations.find_one({"id": p.org_id}, {"_id": 0})
    assert org
    sub = await subscription_view(org)
    invoices = await db.invoices.find({"org_id": p.org_id}, INVOICE_FIELDS).sort("created_at", -1).to_list(100)
    return BillingOverviewOut(
        subscription=SubscriptionOut(**sub) if sub else SubscriptionOut(plan_code="pro", plan_name="Professional", period="monthly", status="expired"),
        payment_configured=payment_mode() != "none", payment_mode=payment_mode(),  # type: ignore[arg-type]
        plans=[PlanOut(**pl) for pl in await all_plans(True)], invoices=[InvoiceOut(**i) for i in invoices],
        usage_shops=await db.shops.count_documents({"org_id": p.org_id}),
        usage_staff=await db.memberships.count_documents({"org_id": p.org_id, "active": True}),
    )


@router.post("/billing/checkout", response_model=CheckoutOut)
async def checkout(body: CheckoutIn, request: Request, p: Principal = Depends(require_tenant("billing:manage"))):
    plan = await get_plan(body.plan_code)
    if not plan:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    org = await db.organizations.find_one({"id": p.org_id}, {"_id": 0})
    assert org
    if plan["max_shops"] < await db.shops.count_documents({"org_id": p.org_id}):
        raise HTTPException(status_code=409, detail=f"L'offre {plan['name']} est limitée à {plan['max_shops']} boutique(s)")
    return await create_checkout(org, plan, body.period, request_origin(request), p)


@router.get("/billing/invoices/{invoice_id}", response_model=InvoiceOut)
async def invoice(invoice_id: str, p: Principal = Depends(require_tenant("billing:manage"))):
    inv = await db.invoices.find_one({"id": invoice_id, "org_id": p.org_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if inv["status"] == "pending" and payment_mode() != "none":
        try:  # webhook may be delayed: ask Stripe directly (server-side, authoritative)
            inv = await sync_invoice_from_stripe(inv)
        except HTTPException:
            pass
    return InvoiceOut(**{k: v for k, v in inv.items() if k not in ("checkout_url", "provider_payment_id")})


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """The event body is never trusted: it only names a session, whose status is re-fetched from Stripe."""
    try:
        event = json.loads(await request.body())
        obj = (event.get("data") or {}).get("object") or {}
        session_id = obj.get("id") if str(event.get("type", "")).startswith("checkout.session.") else None
    except (ValueError, AttributeError):
        session_id = None
    inv = await db.invoices.find_one({"provider_payment_id": session_id}, {"_id": 0}) if isinstance(session_id, str) and session_id else None
    if inv and payment_mode() != "none":
        try:
            await sync_invoice_from_stripe(inv)
        except HTTPException:
            pass
    return {"ok": True}  # 200 for unknown ids too: reveals nothing, stops retries


@router.post("/cron/subscriptions-sweep")
async def cron_sweep(request: Request, authorization: str = Header(default=""), x_webhook_id: str = Header(default="")):
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if x_webhook_id:
        try:
            await db.cron_runs.insert_one({"run_id": x_webhook_id, "name": "subscriptions-sweep", "at": now_utc()})
        except DuplicateKeyError:
            return {"status": "duplicate"}
    asyncio.create_task(sweep_subscriptions(request_origin(request)))
    return {"status": "accepted"}


# ---------- super-admin ----------
@router.get("/admin/plans", response_model=list[PlanOut])
async def admin_plans(_: Principal = Depends(require_platform("platform:read"))):
    return await all_plans(False)


@router.put("/admin/plans/{code}", response_model=PlanOut)
async def admin_update_plan(code: str, body: PlanIn, p: Principal = Depends(require_platform("platform:manage"))):
    before = await get_plan(code)
    if not before:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    if body.prices_ht.monthly is None and body.prices_ht.yearly is None:
        raise HTTPException(status_code=422, detail="Proposez au moins une période de facturation")
    await db.plans.update_one({"code": code}, {"$set": body.model_dump()})
    await audit("platform.plan_update", principal=p, org_id=None, resource_type="plan", resource_id=code,
                details={"before": {k: before.get(k) for k in ("prices_ht", "active", "max_shops", "max_staff")}, "after": body.model_dump()})
    return next(pl for pl in await all_plans(False) if pl["code"] == code)


@router.get("/admin/settings", response_model=PlatformSettingsOut)
async def admin_settings(_: Principal = Depends(require_platform("platform:read"))):
    return PlatformSettingsOut(**await get_settings(), payment_provider="Stripe",
                               payment_configured=payment_mode() != "none", payment_mode=payment_mode())  # type: ignore[arg-type]


@router.put("/admin/settings", response_model=PlatformSettingsOut)
async def admin_update_settings(body: PlatformSettingsIn, p: Principal = Depends(require_platform("platform:manage"))):
    await db.platform_settings.update_one({"id": "global"}, {"$set": body.model_dump()}, upsert=True)
    await audit("platform.settings_update", principal=p, org_id=None, resource_type="settings", resource_id="global", details=body.model_dump())
    return await admin_settings(p)


@router.patch("/admin/organizations/{org_id}/subscription", response_model=SubscriptionOut)
async def admin_subscription(org_id: str, body: AdminSubscriptionIn, p: Principal = Depends(require_platform("platform:manage"))):
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation introuvable")
    sub = dict(org.get("subscription") or {"plan_code": "pro", "period": "monthly", "status": "trialing"})
    if body.plan_code:
        if not await get_plan(body.plan_code):
            raise HTTPException(status_code=404, detail="Offre introuvable")
        sub["plan_code"] = body.plan_code
    if body.period:
        sub["period"] = body.period
    if body.status == "active":
        # Manual grant by the admin — recorded as such, no invoice or payment is created.
        end = body.period_end or (now_utc() + timedelta(days=30))
        sub.update(status="active", current_period_end=end, granted_by_admin=True)
    elif body.status == "trialing":
        sub.update(status="trialing", trial_ends_at=body.period_end or now_utc() + timedelta(days=(await get_settings())["trial_days"]))
    elif body.status == "canceled":
        sub["status"] = "canceled"
    sub["updated_at"] = now_utc()
    await db.organizations.update_one({"id": org_id}, {"$set": {"subscription": sub, "plan": sub["plan_code"]}})
    await audit("platform.subscription_update", principal=p, org_id=org_id, resource_type="organization", resource_id=org_id,
                details={k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in body.model_dump(exclude_none=True).items()})
    view = await subscription_view({**org, "subscription": sub})
    assert view
    return SubscriptionOut(**view)


@router.get("/admin/invoices", response_model=list[InvoiceOut])
async def admin_invoices(_: Principal = Depends(require_platform("platform:read"))):
    return await db.invoices.find({}, INVOICE_FIELDS).sort("created_at", -1).to_list(200)
