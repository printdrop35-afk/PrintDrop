"""SaaS subscriptions: plans, effective status, manual renewal, Stripe Checkout + verified webhooks.

Payment truth comes ONLY from Stripe's API (Checkout Session retrieve) — never from the browser redirect
nor from the webhook body (only used to know which session to re-check). Without STRIPE_API_KEY, checkout is refused:
no payment is ever simulated."""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from emergentintegrations.payments.stripe.checkout import CheckoutError, CheckoutSessionRequest, StripeCheckout
from fastapi import HTTPException
from pymongo import ReturnDocument

from lib.authz import audit, now_utc
from lib.db import db
from lib.platform import get_settings

logger = logging.getLogger(__name__)
PERIOD_MONTHS = {"monthly": 1, "yearly": 12}
LIVE_STATUSES = {"trialing", "active", "past_due"}

DEFAULT_PLANS = [
    {"code": "starter", "name": "Starter", "description": "Pour un point de vente indépendant", "sort": 1,
     "prices_ht": {"monthly": 1900, "yearly": 19000}, "max_shops": 1, "max_staff": 3, "active": True,
     "features": ["1 boutique", "3 comptes employés", "QR code & portail client", "Tarifs personnalisés", "Rapport quotidien par e-mail"]},
    {"code": "pro", "name": "Professional", "description": "Pour les boutiques avec impression automatique", "sort": 2,
     "prices_ht": {"monthly": 3900, "yearly": 39000}, "max_shops": 3, "max_staff": 10, "active": True,
     "features": ["Jusqu'à 3 boutiques", "10 comptes employés", "Agent d'impression Windows", "Alertes e-mail / SMS clients", "Alertes papier & imprimantes"]},
    {"code": "business", "name": "Business", "description": "Pour les réseaux de boutiques", "sort": 3,
     "prices_ht": {"monthly": 7900, "yearly": 79000}, "max_shops": 10, "max_staff": 50, "active": True,
     "features": ["Jusqu'à 10 boutiques", "50 comptes employés", "Tarifs différents par boutique", "Journal d'audit complet", "Support prioritaire"]},
]


def aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year, month = dt.year + month // 12, month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return dt.replace(year=year, month=month, day=min(dt.day, days[month - 1]))


def effective_status(sub: dict, grace_days: int, now: datetime | None = None) -> str:
    """Status derived from dates (stored status may lag until the daily sweep)."""
    now = now or now_utc()
    status = sub.get("status", "trialing")
    if status == "canceled":
        return "canceled"
    if status == "trialing":
        end = aware(sub.get("trial_ends_at"))
        return "trialing" if end and now < end else "expired"
    end = aware(sub.get("current_period_end"))
    if not end:
        return "expired"
    if now < end:
        return "active"
    return "past_due" if now < end + timedelta(days=grace_days) else "expired"


async def get_plan(code: str) -> dict | None:
    return await db.plans.find_one({"code": code}, {"_id": 0})


async def subscription_view(org: dict) -> dict | None:
    sub = org.get("subscription")
    if not sub:
        return None
    settings = await get_settings()
    status = effective_status(sub, settings["grace_days"])
    plan = await get_plan(sub["plan_code"])
    end = aware(sub.get("trial_ends_at") if status == "trialing" else sub.get("current_period_end"))
    days_left = max(0, (end - now_utc()).days) if end and status in ("trialing", "active") else None
    return {
        "plan_code": sub["plan_code"], "plan_name": plan["name"] if plan else sub["plan_code"],
        "period": sub.get("period", "monthly"), "status": status, "trial_ends_at": sub.get("trial_ends_at"),
        "current_period_end": sub.get("current_period_end"), "granted_by_admin": sub.get("granted_by_admin", False),
        "days_left": days_left,
    }


async def org_can_take_orders(org_id: str) -> bool:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "subscription": 1})
    if not org or not org.get("subscription"):
        return True  # legacy org not yet migrated
    return effective_status(org["subscription"], (await get_settings())["grace_days"]) in LIVE_STATUSES


async def enforce_limit(org_id: str, kind: str) -> None:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "subscription": 1})
    plan = await get_plan(((org or {}).get("subscription") or {}).get("plan_code", "")) if org else None
    if not plan:
        return
    if kind == "shops":
        used, limit, label = await db.shops.count_documents({"org_id": org_id}), plan["max_shops"], "boutiques"
    else:
        used, limit, label = await db.memberships.count_documents({"org_id": org_id, "active": True}), plan["max_staff"], "comptes"
    if used >= limit:
        raise HTTPException(status_code=402, detail=f"Limite de l'offre {plan['name']} atteinte ({limit} {label}) — changez d'offre dans Abonnement")


def plan_out(plan: dict, vat_bp: int) -> dict:
    ttc = {k: (None if v is None else v + round(v * vat_bp / 10000)) for k, v in plan["prices_ht"].items()}
    return {**plan, "vat_rate_bp": vat_bp, "prices_ttc": ttc}


# ---------------- Stripe ----------------
def stripe_key() -> str:
    return os.environ.get("STRIPE_API_KEY", "").strip()


def payment_mode() -> str:
    key = stripe_key()
    return "live" if key.startswith(("sk_live_", "rk_live_")) else "test" if key.startswith(("sk_test_", "rk_test_")) else "none"


def stripe_client(origin: str = "") -> StripeCheckout:
    if payment_mode() == "none":
        raise HTTPException(status_code=503, detail="Paiement en ligne non configuré — aucune transaction possible pour l'instant")
    return StripeCheckout(api_key=stripe_key(), webhook_url=f"{origin}/api/webhook/stripe" if origin else None)


async def create_checkout(org: dict, plan: dict, period: str, origin: str, actor) -> dict:
    ht = plan["prices_ht"].get(period)
    if ht is None or not plan.get("active", True):
        raise HTTPException(status_code=422, detail="Cette offre n'est pas disponible pour cette période")
    client = stripe_client(origin)
    settings = await get_settings()
    vat_bp = settings["subscription_vat_rate_bp"]
    vat = round(ht * vat_bp / 10000)
    now = now_utc()
    invoice = {
        "id": str(uuid.uuid4()), "number": None, "org_id": org["id"], "status": "pending",
        "plan_code": plan["code"], "plan_name": plan["name"], "period": period,
        "amount_ht_cents": ht, "vat_rate_bp": vat_bp, "vat_cents": vat, "amount_ttc_cents": ht + vat,
        "provider": "stripe", "provider_payment_id": None, "checkout_url": None, "mode": payment_mode(),
        "period_start": None, "period_end": None, "created_at": now, "paid_at": None, "created_by": actor.email,
        "buyer_name": org["name"],
        "seller": {k: settings[k] for k in ("company_name", "company_address", "company_siret", "company_vat_number", "company_email")},
    }
    await db.invoices.insert_one(dict(invoice))  # recorded BEFORE redirecting to Stripe
    back = f"{origin}/dashboard/abonnement?facture={invoice['id']}"
    try:
        session = await client.create_checkout_session(CheckoutSessionRequest(
            amount=float(invoice["amount_ttc_cents"]) / 100, currency="eur",
            success_url=f"{back}&session_id={{CHECKOUT_SESSION_ID}}", cancel_url=back,
            metadata={"invoice_id": invoice["id"], "org_id": org["id"], "plan": plan["code"], "period": period}))
    except CheckoutError as exc:
        logger.warning("Stripe checkout failed for invoice %s: %s", invoice["id"], exc)
        await db.invoices.update_one({"id": invoice["id"]}, {"$set": {"status": "failed"}})
        raise HTTPException(status_code=502, detail="Le prestataire de paiement a refusé la demande") from exc
    await db.invoices.update_one({"id": invoice["id"]}, {"$set": {"provider_payment_id": session.session_id, "checkout_url": session.url}})
    await audit("billing.checkout", principal=actor, resource_type="invoice", resource_id=invoice["id"],
                details={"plan": plan["code"], "period": period, "amount_ttc_cents": invoice["amount_ttc_cents"]})
    return {"invoice_id": invoice["id"], "checkout_url": session.url}


async def next_invoice_number() -> str:
    year = now_utc().year
    counter = await db.counters.find_one_and_update(
        {"id": f"invoice-{year}"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    return f"PD-{year}-{counter['seq']:06d}"


async def sync_invoice_from_stripe(invoice: dict) -> dict:
    """Fetch the authoritative Checkout Session status from Stripe and apply it exactly once."""
    if not invoice.get("provider_payment_id") or invoice["status"] != "pending":
        return invoice
    try:
        st = await stripe_client().get_checkout_status(invoice["provider_payment_id"])
    except CheckoutError as exc:
        raise HTTPException(status_code=502, detail="Prestataire de paiement injoignable, réessayez") from exc
    if (st.currency or "").lower() != "eur" or st.amount_total != invoice["amount_ttc_cents"] or (st.metadata or {}).get("invoice_id") != invoice["id"]:
        logger.error("Stripe session %s does not match invoice %s", invoice["provider_payment_id"], invoice["id"])
        await audit("billing.mismatch", org_id=invoice["org_id"], outcome="deny", resource_type="invoice",
                    resource_id=invoice["id"], actor="stripe", details={"session_id": invoice["provider_payment_id"]})
        return invoice
    if st.payment_status == "paid":
        return await apply_paid(invoice)
    if st.status == "expired":
        updated = await db.invoices.find_one_and_update(
            {"id": invoice["id"], "status": "pending"}, {"$set": {"status": "expired"}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        await audit("billing.payment_expired", org_id=invoice["org_id"], resource_type="invoice", resource_id=invoice["id"], actor="stripe")
        return updated or invoice
    return invoice  # open / unpaid: customer still on the Stripe page


async def apply_paid(invoice: dict) -> dict:
    now = now_utc()
    claimed = await db.invoices.find_one_and_update(
        {"id": invoice["id"], "status": "pending"}, {"$set": {"status": "paid", "paid_at": now}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not claimed:  # already processed by a concurrent webhook / poll
        return await db.invoices.find_one({"id": invoice["id"]}, {"_id": 0}) or invoice
    org = await db.organizations.find_one({"id": invoice["org_id"]}, {"_id": 0})
    sub = (org or {}).get("subscription") or {}
    settings = await get_settings()
    current_end = aware(sub.get("current_period_end"))
    extend = effective_status(sub, settings["grace_days"], now) in ("active", "past_due") and current_end
    start = current_end if extend and current_end and current_end > now else now
    end = add_months(start, PERIOD_MONTHS[invoice["period"]])
    number = await next_invoice_number()
    await db.invoices.update_one({"id": invoice["id"]}, {"$set": {"number": number, "period_start": start, "period_end": end}})
    await db.organizations.update_one({"id": invoice["org_id"]}, {"$set": {
        "plan": invoice["plan_code"],
        "subscription": {**sub, "plan_code": invoice["plan_code"], "period": invoice["period"], "status": "active",
                         "current_period_end": end, "granted_by_admin": False, "updated_at": now},
    }})
    await audit("billing.payment_paid", org_id=invoice["org_id"], resource_type="invoice", resource_id=invoice["id"],
                actor="stripe", details={"number": number, "amount_ttc_cents": invoice["amount_ttc_cents"], "period_end": end.isoformat()})
    return await db.invoices.find_one({"id": invoice["id"]}, {"_id": 0}) or claimed


async def sweep_subscriptions(origin: str) -> int:
    """Daily: persist effective statuses and e-mail renewal reminders (J-3 and at expiry), once each."""
    from lib.notify import send_email  # local import: notify -> authz only, avoid cycles

    settings = await get_settings()
    changed = 0
    async for org in db.organizations.find({"subscription": {"$exists": True}}, {"_id": 0}):
        sub = org["subscription"]
        status = effective_status(sub, settings["grace_days"])
        if status != sub.get("status") and sub.get("status") != "canceled":
            await db.organizations.update_one({"id": org["id"]}, {"$set": {"subscription.status": status}})
            changed += 1
        end = aware(sub.get("trial_ends_at") if sub.get("status") == "trialing" else sub.get("current_period_end"))
        if not end or sub.get("granted_by_admin") and status == "active":
            continue
        days = (end - now_utc()).days
        kind = "j3" if 0 <= days <= 3 and status in ("trialing", "active") else "expired" if status in ("past_due", "expired") else None
        if not kind or org.get("report_email") is False and org.get("demo"):
            continue
        key = f"{org['id']}:{end.date().isoformat()}:{kind}"
        if await db.billing_reminders.find_one({"key": key}):
            continue
        owner = await db.users.find_one({"id": org["owner_id"]}, {"_id": 0, "email": 1, "name": 1})
        if not owner:
            continue
        await db.billing_reminders.insert_one({"key": key, "at": now_utc()})
        what = "votre période d'essai" if sub.get("status") == "trialing" else "votre abonnement"
        subject = (f"PrintDrop : {what} se termine le {end.strftime('%d/%m/%Y')}" if kind == "j3"
                   else "PrintDrop : abonnement à renouveler — vos boutiques n'acceptent plus de commandes" if status == "expired"
                   else "PrintDrop : paiement de renouvellement en attente")
        html = (f"<p>Bonjour {owner['name']},</p><p>{subject}.</p>"
                f"<p>Le renouvellement est manuel : rendez-vous sur <a href='{origin}/dashboard/abonnement'>votre espace Abonnement</a> "
                f"pour régler la période suivante.</p><p>— L'équipe PrintDrop</p>")
        try:
            await send_email(to=owner["email"], subject=subject, html=html)
        except Exception as exc:  # noqa: BLE001 — reminder failures must not stop the sweep
            logger.warning("reminder %s failed: %s", key, exc)
    return changed
