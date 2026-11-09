"""Public marketing-site endpoints: plan list for the pricing section and the contact / demo form."""

import html
import logging
import os
import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request

from lib.authz import now_utc
from lib.db import db
from lib.notify import NotifyError, send_email
from models.schemas import ContactIn, ContactOut, PublicPlanOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["site"])
CONTACT_LIMIT_PER_HOUR = 5


@router.get("/plans", response_model=list[PublicPlanOut])
async def public_plans():
    plans = await db.plans.find({"active": True}, {"_id": 0}).sort("sort", 1).to_list(20)
    return [PublicPlanOut(code=p["code"], name=p["name"], description=p.get("description", ""), features=p.get("features", []),
                          monthly_ht_cents=p["prices_ht"]["monthly"], yearly_ht_cents=p["prices_ht"].get("yearly")) for p in plans]


@router.post("/contact", response_model=ContactOut)
async def contact(body: ContactIn, request: Request):
    if body.website:  # honeypot: bots fill hidden fields — pretend success, store nothing
        return ContactOut(ok=True, delivered=False)
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0].strip()
    since = now_utc() - timedelta(hours=1)
    if await db.contact_messages.count_documents({"ip": ip, "created_at": {"$gte": since}}) >= CONTACT_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail="Trop de messages envoyés. Réessayez dans une heure.")
    msg = {"id": str(uuid.uuid4()), "kind": body.kind, "name": body.name.strip(), "business": body.business.strip(),
           "email": str(body.email).lower(), "subject": body.subject.strip(), "message": body.message.strip(),
           "ip": ip, "created_at": now_utc(), "delivered": False, "error": None}
    await db.contact_messages.insert_one(msg)

    to = os.environ.get("CONTACT_EMAIL", "")
    if not to:
        return ContactOut(ok=True, delivered=False)
    e = html.escape
    label = "Demande de démo" if body.kind == "demo" else "Message de contact"
    page = (f"<h2>{label} — site PrintDrop</h2><p><b>Nom :</b> {e(msg['name'])}<br><b>Établissement :</b> {e(msg['business']) or '—'}"
            f"<br><b>E-mail :</b> {e(msg['email'])}<br><b>Sujet :</b> {e(msg['subject'])}</p>"
            f"<p style=\"white-space:pre-wrap\">{e(msg['message'])}</p>")
    try:
        await send_email(to=to, subject=f"[PrintDrop] {label} : {msg['subject'][:80]}", html=page)
        await db.contact_messages.update_one({"id": msg["id"]}, {"$set": {"delivered": True}})
        return ContactOut(ok=True, delivered=True)
    except (NotifyError, ValueError) as exc:
        logger.warning("contact email not sent: %s", exc)
        await db.contact_messages.update_one({"id": msg["id"]}, {"$set": {"error": str(exc)[:200]}})
        return ContactOut(ok=True, delivered=False)
