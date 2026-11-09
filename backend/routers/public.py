"""Customer portal (no account): shop lookup by QR slug, private upload, server quote,
order creation, tracking by code + phone, and the signed-link file endpoint."""

import re
import secrets
import uuid

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from lib.authz import audit, now_utc, request_origin
from lib.db import db
from lib.billing import org_can_take_orders
from lib.platform import shop_vat_bp
from lib.pricing import finalize, price_extras, price_print, price_services, public_pricing
from lib.security import new_secret_token, sha256, verify_file_link
import asyncio
import math
from datetime import timedelta

from lib.authz import now_utc
from lib.retention import RETENTION_DAYS
from lib.storage import MEDIA_TYPES, convert_docx, MAX_BYTES, StorageError, count_pages, detect_kind, resolve, save_file
from models.schemas import (
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
    try:
        lines.extend(price_services(shop["pricing"], body.services.model_dump()))
        lines.extend(price_extras(shop["pricing"], [e.model_dump() for e in body.extras]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return finalize(shop["pricing"], lines, body.promo_code, await shop_vat_bp())


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
    key = save_file(shop["org_id"], shop["id"], data, kind)
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
    if len(digits) < 6:
        raise HTTPException(status_code=422, detail="Numéro de téléphone invalide")
    q = await build_quote(shop, body)
    if q["promo_error"] and body.promo_code and not q["promo_code_applied"]:
        raise HTTPException(status_code=422, detail=q["promo_error"])
    lines, total = q["lines"], q["total_cents"]
    if not any(line["kind"] not in ("discount", "minimum") for line in lines):
        raise HTTPException(status_code=422, detail="Ajoutez au moins un document ou un service")
    now = now_utc()
    order_id = str(uuid.uuid4())
    while True:
        code = "PD-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not await db.orders.find_one({"code": code}, {"_id": 1}):
            break
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
        "customer_email": body.customer_email.lower() if body.customer_email else None, "notify": body.notify,
        "public_origin": request_origin(request),  # where the customer reached us — used for the tracking link
        "phone_digits": digits, "note": body.note.strip(), "lines": lines, "total_cents": total, "currency": "EUR",
        "total_ht_cents": q["total_ht_cents"], "vat_cents": q["vat_cents"], "vat_rate_bp": q["vat_rate_bp"],
        "discount_cents": q["discount_cents"], "promo_code": q["promo_code_applied"],
        "status": "pending", "payment_status": "unpaid", "payment_method": None, "paid_at": None,
        "created_at": now, "updated_at": now, "history": [{"status": "pending", "at": now, "by": "Client"}],
    }
    await db.orders.insert_one(dict(order))
    await audit("order.create", org_id=shop["org_id"], resource_type="order", resource_id=order_id,
                details={"code": code, "total_cents": total, "shop_id": shop["id"]})
    return with_retention(order)


@router.post("/public/orders/track", response_model=OrderPublicOut)
async def track(body: TrackIn):
    order = await db.orders.find_one({"code": body.code.strip().upper()}, {"_id": 0})
    if not order or not secrets.compare_digest(order["phone_digits"], phone_digits(body.phone)):
        raise HTTPException(status_code=404, detail="Aucune commande ne correspond à ce code et ce numéro")
    return with_retention(order)


def with_retention(order: dict) -> dict:
    """Adds the date/days left before the customer's documents are erased (server clock, see lib/retention.py)."""
    delete_at = order["created_at"] + timedelta(days=RETENTION_DAYS)
    left = (delete_at - now_utc()).total_seconds() / 86400
    return {**order, "documents_delete_at": delete_at, "documents_days_left": max(0, math.ceil(left))}


@router.get("/files/{doc_id}")
async def signed_file(doc_id: str, exp: int = Query(...), sig: str = Query(..., max_length=128)):
    if not verify_file_link(doc_id, exp, sig):
        raise HTTPException(status_code=403, detail="Lien expiré ou invalide")
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    try:
        path = resolve(doc["storage_key"])
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Document introuvable") from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Fichier supprimé")
    return FileResponse(
        path, media_type=MEDIA_TYPES[doc["kind"]], filename=doc["filename"], content_disposition_type="inline",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
