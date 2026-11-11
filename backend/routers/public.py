"""Customer portal (no account): shop lookup by QR slug, private upload, server quote,
order creation, tracking by code + phone, and the signed-link file endpoint."""

import re
import secrets
import uuid

from pymongo.errors import DuplicateKeyError
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
import logging

logger = logging.getLogger(__name__)

from lib.authz import audit, now_utc, request_origin
from lib.db import db
from lib.billing import org_can_take_orders, org_printer_label
from lib.platform import shop_vat_bp
from lib.pricing import finalize, price_extras, price_print, price_services, public_pricing
from lib.security import new_secret_token, sha256, verify_file_link
import asyncio
from lib.storage import MEDIA_TYPES, convert_docx, MAX_BYTES, StorageError, count_pages, detect_kind, read_file, save_file
from models.schemas import (
    TrackingConfigOut,
    DocumentUploadOut, OrderCreateIn, OrderPublicOut, PublicShopOut, QuoteIn, QuoteOut, TrackIn,
)

router = APIRouter(tags=["public"])

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


async def get_public_shop(slug: str) -> dict:
    shop = await db.shops.find_one({"slug": slug}, {"_id": 0})
    if shop:
        org = await db.organizations.find_one({"id": shop["org_id"], "status": "active"}, {"_id": 0, "id": 1})
        if org:
            return shop
    raise HTTPException(status_code=404, detail="Boutique introuvable")


async def build_quote(shop: dict, body: QuoteIn) -> dict:
    lines: list[dict] = []
    for item in body.items:
        doc = await db.documents.find_one(
            {"id": item.document_id, "shop_id": shop["id"], "org_id": shop["org_id"], "status": "uploaded"}, {"_id": 0}
        )
        if not doc or not secrets.compare_digest(doc["token_hash"], sha256(item.upload_token)):
            raise HTTPException(status_code=404, detail="Document introuvable ou expiré — renvoyez le fichier")
        try:
            lines.append(price_print(shop["pricing"], doc["filename"], doc["id"], doc["page_count"], item.options.model_dump()))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{doc['filename']} : {exc}") from exc
    if body.services.photocopy_bw or body.services.photocopy_color:
        raise HTTPException(status_code=422, detail="Les photocopies ne sont pas proposées en ligne : demandez-les directement au comptoir")
    try:
        lines.extend(price_services(shop["pricing"], body.services.model_dump()))
        lines.extend(price_extras(shop["pricing"], [e.model_dump() for e in body.extras]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return finalize(shop["pricing"], lines, body.promo_code, await shop_vat_bp())


@router.get("/public/tracking", response_model=TrackingConfigOut)
async def tracking_config():
    """Google Ads conversion target (set in backend/.env); empty = no conversion event is sent."""
    import os
    return TrackingConfigOut(ads_purchase_send_to=os.environ.get("GOOGLE_ADS_PURCHASE_SEND_TO", "").strip(),
                             ads_signup_send_to=os.environ.get("GOOGLE_ADS_SIGNUP_SEND_TO", "").strip())


@router.get("/public/shops/{slug}", response_model=PublicShopOut)
async def public_shop(slug: str):
    shop = await get_public_shop(slug)
    accepting = shop["accepting_orders"] and await org_can_take_orders(shop["org_id"])
    return {**shop, "accepting_orders": accepting, "pricing": public_pricing(shop["pricing"], await shop_vat_bp())}


@router.post("/public/shops/{slug}/documents", response_model=DocumentUploadOut)
async def upload_document(slug: str, file: UploadFile = File(...)):
    shop = await get_public_shop(slug)
    if not shop["accepting_orders"] or not await org_can_take_orders(shop["org_id"]):
        raise HTTPException(status_code=409, detail="Cette boutique n'accepte pas de commandes pour le moment")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (25 Mo maximum)")
    try:
        kind = detect_kind(data)
        if kind == "docx":
            data = await convert_docx(data)
            kind = "pdf"
        pages = count_pages(data, kind)
    except StorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    key = await save_file(shop["org_id"], shop["id"], data, kind)
    token = new_secret_token()
    filename = re.sub(r"[^\w.\- ()À-ÿ]", "_", (file.filename or f"document.{kind}"))[:120]
    doc = {
        "id": str(uuid.uuid4()), "org_id": shop["org_id"], "shop_id": shop["id"], "order_id": None,
        "filename": filename, "kind": kind, "page_count": pages, "size_bytes": len(data),
        "storage_key": key, "token_hash": sha256(token), "status": "uploaded", "created_at": now_utc(),
    }
    await db.documents.insert_one(dict(doc))
    return DocumentUploadOut(id=doc["id"], filename=filename, kind=kind, page_count=pages, size_bytes=len(data), upload_token=token)


@router.post("/public/shops/{slug}/quote", response_model=QuoteOut)
async def quote(slug: str, body: QuoteIn):
    shop = await get_public_shop(slug)
    return QuoteOut(**await build_quote(shop, body))


@router.post("/public/shops/{slug}/orders", response_model=OrderPublicOut)
async def create_order(slug: str, body: OrderCreateIn, request: Request):
    shop = await get_public_shop(slug)
    if not shop["accepting_orders"] or not await org_can_take_orders(shop["org_id"]):
        raise HTTPException(status_code=409, detail="Cette boutique n'accepte pas de commandes pour le moment")
    digits = phone_digits(body.customer_phone)
    if digits and len(digits) < 6:
        raise HTTPException(status_code=422, detail="Numéro de téléphone invalide (laissez le champ vide si vous ne souhaitez pas le donner)")
    q = await build_quote(shop, body)
    if q["promo_error"] and body.promo_code and not q["promo_code_applied"]:
        raise HTTPException(status_code=422, detail=q["promo_error"])
    lines, total = q["lines"], q["total_cents"]
    if not any(line["kind"] not in ("discount", "minimum") for line in lines):
        raise HTTPException(status_code=422, detail="Ajoutez au moins un document ou un service")
    now = now_utc()
    order_id = str(uuid.uuid4())
    code = await new_pickup_code()
    # Claim each document atomically so an upload can never be attached to two orders.
    claimed: list[str] = []
    for item in body.items:
        res = await db.documents.update_one(
            {"id": item.document_id, "shop_id": shop["id"], "status": "uploaded"},
            {"$set": {"status": "attached", "order_id": order_id}},
        )
        if res.modified_count != 1:
            if claimed:
                await db.documents.update_many({"id": {"$in": claimed}}, {"$set": {"status": "uploaded", "order_id": None}})
            raise HTTPException(status_code=409, detail="Document déjà utilisé dans une autre commande")
        claimed.append(item.document_id)
    order = {
        "id": order_id, "code": code, "org_id": shop["org_id"], "shop_id": shop["id"], "shop_name": shop["name"],
        "shop_slug": shop["slug"], "customer_name": body.customer_name.strip(), "customer_phone": body.customer_phone.strip(),
        "customer_email": body.customer_email.lower() if body.customer_email else None,
        "notify": body.notify and bool(digits or body.customer_email),
        "public_origin": request_origin(request),  # where the customer reached us — used for the tracking link
        "phone_digits": digits, "note": body.note.strip(), "lines": lines, "total_cents": total, "currency": "EUR",
        "total_ht_cents": q["total_ht_cents"], "vat_cents": q["vat_cents"], "vat_rate_bp": q["vat_rate_bp"],
        "discount_cents": q["discount_cents"], "promo_code": q["promo_code_applied"],
        "active_code": code, "status": "pending", "payment_status": "unpaid", "payment_method": None, "paid_at": None,
        "created_at": now, "updated_at": now, "history": [{"status": "pending", "at": now, "by": "Client"}],
        "printer_plan": await org_printer_label(shop["org_id"]),
    }
    for attempt in range(5):  # the unique active_code index settles a race between two orders drawing the same code
        try:
            await db.orders.insert_one(dict(order))
            break
        except DuplicateKeyError:
            if attempt == 4:
                raise HTTPException(status_code=503, detail="Réessayez dans un instant")
            order["code"] = order["active_code"] = await new_pickup_code()
    code = order["code"]
    await audit("order.create", org_id=shop["org_id"], resource_type="order", resource_id=order_id,
                details={"code": code, "total_cents": total, "shop_id": shop["id"]})
    return with_retention(order)


@router.post("/public/orders/track", response_model=OrderPublicOut)
async def track(body: TrackIn, request: Request):
    if not _track_allowed(request):
        raise HTTPException(status_code=429, detail="Trop de recherches — réessayez dans quelques minutes")
    order = await find_by_code(body.code)
    # orders placed with a phone still require it; orders without phone are tracked with the code alone
    if not order or (order.get("phone_digits") and not secrets.compare_digest(order["phone_digits"], phone_digits(body.phone))):
        raise HTTPException(status_code=404, detail="Aucune commande ne correspond à ce code (et à ce numéro, si vous en avez donné un)")
    if not order.get("printer_plan"):
        order["printer_plan"] = await org_printer_label(order["org_id"])
    return with_retention(order)


def with_retention(order: dict) -> dict:
    return {**order, "documents_deleted": bool(order.get("purged_at"))}


ACTIVE_STATUSES = ["pending", "printing", "ready"]


async def new_pickup_code() -> str:
    """4-digit pickup code, unique among orders still in progress (finished orders may reuse it)."""
    for _ in range(200):
        code = f"{secrets.randbelow(9000) + 1000}"
        if not await db.orders.find_one({"code": code, "status": {"$in": ACTIVE_STATUSES}}, {"_id": 1}):
            return code
    raise HTTPException(status_code=503, detail="Trop de commandes en cours — réessayez dans un instant")


async def find_by_code(raw: str) -> dict | None:
    code = raw.strip().upper()
    if code.isdigit():  # 4-digit codes: the in-progress order wins, else the most recent one
        return (await db.orders.find_one({"code": code, "status": {"$in": ACTIVE_STATUSES}}, {"_id": 0})
                or await db.orders.find_one({"code": code}, {"_id": 0}, sort=[("created_at", -1)]))
    return await db.orders.find_one({"code": code}, {"_id": 0})  # legacy PD-XXXXXX codes


_TRACK_HITS: dict[str, list[float]] = {}


def _track_allowed(request: Request, limit: int = 30, window: float = 600.0) -> bool:
    """In-memory per-IP limit: 4-digit codes must not be enumerable."""
    import time
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?"))
    now = time.monotonic()
    hits = [t for t in _TRACK_HITS.get(ip, []) if now - t < window]
    if len(hits) >= limit:
        _TRACK_HITS[ip] = hits
        return False
    hits.append(now)
    _TRACK_HITS[ip] = hits
    return True


@router.get("/files/{doc_id}")
async def signed_file(doc_id: str, exp: int = Query(...), sig: str = Query(..., max_length=128)):
    if not verify_file_link(doc_id, exp, sig):
        raise HTTPException(status_code=403, detail="Lien expiré ou invalide")
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    if doc.get("status") == "purged" or not doc.get("storage_key"):
        raise HTTPException(status_code=410, detail="Document supprimé après le retrait de la commande")
    try:
        data = await read_file(doc["storage_key"])
    except (StorageError, OSError) as exc:
        logger.error("signed_file: stored file missing for document %s (%s)", doc_id, doc["storage_key"])
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur") from exc
    from urllib.parse import quote
    return Response(data, media_type=MEDIA_TYPES[doc["kind"]], headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(doc['filename'])}",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
