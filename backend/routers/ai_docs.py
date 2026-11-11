"""Customer portal « Créer un document avec l'IA »: the finished PDF becomes a normal uploaded document of the
SAME shop (same QR session, pricing, printers and payment flow) — the customer never downloads/re-uploads it."""

import time
import uuid

from fastapi import APIRouter, HTTPException, Request

from lib.ai_docs import PRODOCONLINE_CATALOGUE_URL, TEMPLATES, TEMPLATE_BY_CODE, generate, render_pdf
from lib.authz import audit, now_utc
from lib.billing import org_can_take_orders
from lib.db import db
from lib.security import new_secret_token, sha256
from lib.storage import StorageError, count_pages, save_file
from models.schemas import AiDocCatalogOut, AiDocDraftOut, AiDocFinalizeIn, AiDocGenerateIn, DocumentUploadOut
from routers.public import get_public_shop

router = APIRouter(prefix="/public/shops/{slug}/ai-docs", tags=["ai-docs"])

_HITS: dict[str, list[float]] = {}


def _allow(request: Request, limit: int = 15, window: float = 3600.0) -> None:
    """Free feature: per-IP cap on AI generations to protect the shop's portal from abuse."""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")
    now = time.monotonic()
    hits = [t for t in _HITS.get(ip, []) if now - t < window]
    if len(hits) >= limit:
        _HITS[ip] = hits
        raise HTTPException(status_code=429, detail="Trop de documents générés — réessayez dans une heure")
    _HITS[ip] = hits + [now]


async def _open_shop(slug: str) -> dict:
    shop = await get_public_shop(slug)
    if not shop["accepting_orders"] or not await org_can_take_orders(shop["org_id"]):
        raise HTTPException(status_code=409, detail="Cette boutique n'accepte pas de commandes pour le moment")
    return shop


def _template(code: str) -> dict:
    t = TEMPLATE_BY_CODE.get(code)
    if not t:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    return t


@router.get("/templates", response_model=AiDocCatalogOut)
async def templates(slug: str):
    await get_public_shop(slug)
    return AiDocCatalogOut(templates=TEMPLATES, catalogue_url=PRODOCONLINE_CATALOGUE_URL)  # type: ignore[arg-type]


@router.post("/generate", response_model=AiDocDraftOut)
async def generate_draft(slug: str, body: AiDocGenerateIn, request: Request):
    shop = await _open_shop(slug)
    template = _template(body.template)
    _allow(request)
    draft = await generate(template, body.values)
    await audit("aidoc.generate", org_id=shop["org_id"], resource_type="shop", resource_id=shop["id"], details={"template": template["code"]})
    return AiDocDraftOut(**draft)


@router.post("/finalize", response_model=DocumentUploadOut)
async def finalize(slug: str, body: AiDocFinalizeIn):
    """« Imprimer avec PrintDrop »: approved text -> final A4 PDF stored like an upload of this shop."""
    shop = await _open_shop(slug)
    template = _template(body.template)
    data = render_pdf(body.title.strip() or template["name"], body.body)
    try:
        pages = count_pages(data, "pdf")
    except StorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    key = await save_file(shop["org_id"], shop["id"], data, "pdf")
    token = new_secret_token()
    filename = f"{template['name']}.pdf"
    doc = {
        "id": str(uuid.uuid4()), "org_id": shop["org_id"], "shop_id": shop["id"], "order_id": None,
        "filename": filename, "kind": "pdf", "page_count": pages, "size_bytes": len(data),
        "storage_key": key, "token_hash": sha256(token), "status": "uploaded", "created_at": now_utc(),
        "source": "ai", "ai_template": template["code"],
    }
    await db.documents.insert_one(dict(doc))
    await audit("aidoc.finalize", org_id=shop["org_id"], resource_type="document", resource_id=doc["id"], details={"template": template["code"], "pages": pages})
    return DocumentUploadOut(id=doc["id"], filename=filename, kind="pdf", page_count=pages, size_bytes=len(data), upload_token=token)
