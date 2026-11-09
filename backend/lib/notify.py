"""Customer notifications ("commande prête") — e-mail via Emergent managed Resend, SMS via Twilio.

Jobs are queued in `notification_jobs` and sent by the background worker (server.py) with retries.
Recipients come only from the stored order; bodies are fixed server-side templates (no open relay)."""

import ipaddress
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from pymongo.errors import DuplicateKeyError

from lib.authz import audit, now_utc
from lib.db import db

logger = logging.getLogger(__name__)

# Emergent managed email proxy — a constant, never read from the environment.
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
MAX_ATTEMPTS = 3


class NotifyError(Exception):
    def __init__(self, message: str, retry: bool = True):
        super().__init__(message)
        self.retry = retry


# ---------- e-mail guardrail gate (from the managed-email playbook; do not weaken) ----------
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str) -> str:
    key = os.environ.get("EMERGENT_EMAIL_KEY")
    from_name = os.environ.get("EMAIL_FROM_NAME")
    if not key or not from_name:
        raise NotifyError("E-mail non configuré", retry=False)
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": from_name}
    if os.environ.get("EMAIL_REPLY_TO"):
        payload["contact_email"] = os.environ["EMAIL_REPLY_TO"]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{EMAIL_BASE_URL}/api/v1/email/send", headers={"X-Email-Key": key}, json=payload)
    except httpx.HTTPError as exc:
        raise NotifyError(f"Réseau indisponible : {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        try:
            code = resp.json().get("code", "")
        except ValueError:
            code = ""
        if code in ("insufficient_credits", "integration_disabled", "daily_limit_reached"):
            logger.warning("Email paused: %s (%s)", code, resp.status_code)
            raise NotifyError(f"E-mail suspendu ({code})", retry=False)
        raise NotifyError(f"Échec d'envoi e-mail ({resp.status_code})", retry=resp.status_code >= 500)
    return resp.json().get("id", "")


# ---------- SMS (Twilio Messages REST API) ----------
def twilio_configured() -> bool:
    return all(os.environ.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"))


def to_e164(phone: str, default_cc: str = "33") -> str | None:
    """French-first normalisation: '06 12 34 56 78' -> '+33612345678'; '+44…'/'0044…' kept."""
    raw = phone.strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        e164 = "+" + digits
    elif digits.startswith("00"):
        e164 = "+" + digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        e164 = f"+{default_cc}{digits[1:]}"
    else:
        return None
    return e164 if 8 <= len(e164) <= 16 else None


async def send_sms(*, to: str, body: str) -> str:
    if not twilio_configured():
        raise NotifyError("SMS non configuré (clés Twilio manquantes)", retry=False)
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
                data={"To": to, "From": os.environ["TWILIO_FROM_NUMBER"], "Body": body},
            )
    except httpx.HTTPError as exc:
        raise NotifyError(f"Réseau indisponible : {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("message", "")
        except ValueError:
            msg = ""
        raise NotifyError(f"Twilio {resp.status_code} : {msg[:160]}", retry=resp.status_code >= 500 or resp.status_code == 429)
    return resp.json().get("sid", "")


# ---------- templates ----------
def ready_email(order: dict, link: str) -> tuple[str, str]:
    shop = escape(order["shop_name"])
    code = escape(order["code"])
    total = f"{order['total_cents'] / 100:.2f}".replace(".", ",")
    pay_line = ("Montant à régler au comptoir : <strong>" + total + " €</strong>") if order["payment_status"] == "unpaid" \
        else "Votre commande est déjà réglée."
    subject = f"Votre commande {order['code']} est prête — {order['shop_name']}"
    html = (
        '<table role="presentation" width="100%" style="background:#F8FAFC"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0F172A">'
        '<table role="presentation" width="100%" style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #E2E8F0;border-radius:12px">'
        '<tr><td style="padding:24px">'
        f'<p style="font-size:13px;color:#2563EB;font-weight:bold;letter-spacing:1px">PRINTDROP</p>'
        f'<h1 style="font-size:22px;margin:8px 0">Bonjour {escape(order["customer_name"])}, votre impression est prête !</h1>'
        f'<p>Votre commande <strong>{code}</strong> vous attend chez <strong>{shop}</strong>.</p>'
        f'<p>{pay_line}</p>'
        f'<p style="margin:24px 0"><a href="{escape(link)}" style="background:#2563EB;color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">Suivre ma commande</a></p>'
        '<p style="font-size:12px;color:#64748B">Message envoyé par PrintDrop pour le compte de la boutique. '
        'Nous ne vous demanderons jamais de mot de passe ni de coordonnées bancaires par e-mail.</p>'
        '</td></tr></table></td></tr></table>'
    )
    return subject, html


def ready_sms(order: dict, link: str) -> str:
    total = f"{order['total_cents'] / 100:.2f}".replace(".", ",")
    pay = f" A regler: {total} EUR." if order["payment_status"] == "unpaid" else ""
    return f"PrintDrop: votre commande {order['code']} est prete chez {order['shop_name']}.{pay} Suivi: {link}"


# ---------- queue ----------
async def enqueue_ready(order: dict, origin: str) -> int:
    """Queue one notification per channel for the 'ready' event. Unique index => sent once per order."""
    if not order.get("notify", True):
        return 0
    base = order.get("public_origin") or origin
    link = f"{base.rstrip('/')}/suivi/{order['code']}"
    channels = [("sms", order["customer_phone"])] if order.get("customer_phone") else []
    if order.get("customer_email"):
        channels.append(("email", order["customer_email"]))
    queued = 0
    for channel, recipient in channels:
        try:
            await db.notification_jobs.insert_one({
                "id": str(uuid.uuid4()), "org_id": order["org_id"], "shop_id": order["shop_id"], "order_id": order["id"],
                "event": "ready", "channel": channel, "recipient": recipient, "link": link, "status": "queued",
                "attempts": 0, "last_error": None, "next_attempt_at": now_utc(), "created_at": now_utc(), "sent_at": None,
            })
            queued += 1
        except DuplicateKeyError:
            pass
    return queued


async def _deliver(job: dict, order: dict) -> str:
    if job["channel"] == "email":
        subject, html = ready_email(order, job["link"])
        return await send_email(to=job["recipient"], subject=subject, html=html)
    e164 = to_e164(job["recipient"])
    if not e164:
        raise NotifyError("Numéro de téléphone non reconnu pour l'envoi SMS", retry=False)
    return await send_sms(to=e164, body=ready_sms(order, job["link"]))


async def process_notification_jobs(limit: int = 20) -> int:
    done = 0
    for _ in range(limit):
        job = await db.notification_jobs.find_one_and_update(
            {"status": "queued", "next_attempt_at": {"$lte": now_utc()}},
            {"$set": {"status": "sending"}, "$inc": {"attempts": 1}}, projection={"_id": 0}, return_document=True,
        )
        if not job:
            break
        order = await db.orders.find_one({"id": job["order_id"], "org_id": job["org_id"]}, {"_id": 0})
        try:
            if not order:
                raise NotifyError("Commande introuvable", retry=False)
            provider_id = await _deliver(job, order)
            await db.notification_jobs.update_one({"id": job["id"]}, {"$set": {
                "status": "sent", "sent_at": now_utc(), "provider_id": provider_id, "last_error": None}})
            await audit("notification.sent", org_id=job["org_id"], actor="systeme", resource_type="order",
                        resource_id=job["order_id"], details={"channel": job["channel"]})
        except Exception as exc:  # NotifyError or unexpected — never crash the worker
            retry = isinstance(exc, NotifyError) and exc.retry and job["attempts"] < MAX_ATTEMPTS
            status = "queued" if retry else ("skipped" if isinstance(exc, NotifyError) and not exc.retry else "failed")
            await db.notification_jobs.update_one({"id": job["id"]}, {"$set": {
                "status": status, "last_error": str(exc)[:300],
                "next_attempt_at": now_utc() + timedelta(seconds=30 * job["attempts"])}})
            logger.info("notification %s %s: %s", job["channel"], status, exc)
        done += 1
    return done


async def alert_owner(org_id: str, key: str, subject: str, text: str) -> bool:
    """One e-mail per incident key to the organization owner (printer offline, agent disconnected, print failure)."""
    from pymongo.errors import DuplicateKeyError
    try:
        await db.owner_alerts.insert_one({"key": key, "org_id": org_id, "subject": subject, "at": datetime.now(timezone.utc)})
    except DuplicateKeyError:
        return False
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "owner_id": 1, "demo": 1})
    owner = await db.users.find_one({"id": (org or {}).get("owner_id")}, {"_id": 0, "email": 1}) if org else None
    if not owner or (org or {}).get("demo") or not os.environ.get("EMERGENT_EMAIL_KEY"):
        return False  # demo orgs use fictitious addresses: alert stays visible in the dashboard only
    html = (f'<div style="font-family:Arial,sans-serif;color:#0f172a"><h2 style="color:#e11d48">{subject}</h2>'
            f'<p>{text}</p><p style="color:#64748b;font-size:12px">PrintDrop — alerte automatique.</p></div>')
    try:
        await send_email(to=owner["email"], subject=f"PrintDrop — {subject}", html=html)
    except Exception as exc:  # alert e-mail failure must never break the agent heartbeat
        logger.warning("alert_owner %s: %s", key, exc)
    return True


async def check_agents_offline() -> None:
    """Background job: e-mail the owner once when an active agent stops sending heartbeats."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=180)
    async for ag in db.agents.find({"status": "active", "last_seen_at": {"$lt": cutoff}, "offline_alerted_for": {"$ne": "x"}}, {"_id": 0}):
        if ag.get("offline_alerted_for") == ag["last_seen_at"].isoformat():
            continue
        await db.agents.update_one({"id": ag["id"]}, {"$set": {"offline_alerted_for": ag["last_seen_at"].isoformat()}})
        await alert_owner(ag["org_id"], f"agent-offline:{ag['id']}:{ag['last_seen_at'].isoformat()}",
                          f"Agent Windows « {ag['name']} » déconnecté",
                          "Le PC du comptoir ne répond plus depuis 3 minutes. Les impressions en attente reprendront dès son retour, sans doublon.")
