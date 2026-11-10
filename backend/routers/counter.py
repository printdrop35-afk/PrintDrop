"""Counter services: walk-in photocopies and scans (agent dashboard), customer delivery of scans.

Hardware honesty: Windows printer drivers do not expose the copier's "copy" function, so a photocopy is made with the
copier's own Copy button; PrintDrop records the order, price and payment and never claims the copy happened by itself.
Scanning goes through the paired Windows agent (WIA, any scanner recognised by Windows) or, as a fallback, by importing
the files saved by the manufacturer's scan software. Scanned pages are stored server-side as they arrive (never lost if
the browser disconnects) and erased once the session is finalised or abandoned (24 h)."""

import io
import logging
import secrets
import uuid
from datetime import timedelta
from urllib.parse import quote as urlquote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps

from lib.authz import Principal, audit, now_utc, request_origin, require_tenant, tenant_repo
from lib.db import db
from lib.pricing import PAPER_LABELS, finalize
from lib.printing import is_online
from lib.platform import shop_vat_bp
from routers.dashboard import get_order_or_404, get_shop_or_404
from lib.storage import MEDIA_TYPES, StorageError, delete_file, read_file, save_file
from models.schemas import CopyConfirmIn, CopyIn, OrderOut, ScanEmailIn, ScanFinalizeIn, ScanPageUpdateIn, ScanPublicOut, ScanSessionIn, ScanSessionOut

logger = logging.getLogger(__name__)
router = APIRouter()
public_router = APIRouter(prefix="/public")

MAX_PAGES = 100
MAX_PAGE_BYTES = 15 * 1024 * 1024
COPY_TIMEOUT = timedelta(minutes=30)  # agent silent this long on a copy => staff must confirm what came out


# ---------- helpers ----------
def _order_doc(shop: dict, service: str, lines: list[dict], q: dict, by: str, status: str, name: str, email: str | None) -> dict:
    now = now_utc()
    return {
        "id": str(uuid.uuid4()), "code": "", "org_id": shop["org_id"], "shop_id": shop["id"], "shop_name": shop["name"],
        "shop_slug": shop["slug"], "service": service, "customer_name": name or "Client comptoir", "customer_phone": "",
        "customer_email": email, "notify": False, "phone_digits": "", "note": "", "lines": lines,
        "total_cents": q["total_cents"], "currency": "EUR", "total_ht_cents": q["total_ht_cents"], "vat_cents": q["vat_cents"],
        "vat_rate_bp": q["vat_rate_bp"], "discount_cents": q["discount_cents"], "promo_code": None,
        "status": status, "payment_status": "unpaid", "payment_method": None, "paid_at": None,
        "created_at": now, "updated_at": now, "history": [{"status": status, "at": now, "by": by}],
    }


async def _insert_order(order: dict) -> dict:
    from routers.public import new_pickup_code
    from pymongo.errors import DuplicateKeyError
    for attempt in range(5):
        order["code"] = order["active_code"] = await new_pickup_code()
        try:
            await db.orders.insert_one(dict(order))
            return order
        except DuplicateKeyError:
            if attempt == 4:
                raise HTTPException(status_code=503, detail="Réessayez dans un instant")
    return order


def copy_line(pricing: dict, body: CopyIn) -> dict:
    photocopy = pricing["photocopy"]
    if not photocopy.get("active", True):
        raise HTTPException(status_code=422, detail="La photocopie n'est pas activée dans vos tarifs")
    if body.paper_size == "A4":
        unit = photocopy[body.color]
    else:
        size = pricing["print"].get(body.paper_size)
        if not size or not size.get("active", True):
            raise HTTPException(status_code=422, detail=f"Le format {body.paper_size} n'est pas proposé dans vos tarifs")
        unit = size[body.color]
    pages = body.originals * body.copies
    gross = pages * unit
    subtotal = round(gross * (100 - pricing["duplex_discount_pct"]) / 100) if body.duplex and body.originals > 1 else gross
    sheets = (-(-body.originals // 2) if body.duplex else body.originals) * body.copies
    label = f"Photocopie {PAPER_LABELS.get(body.paper_size, body.paper_size)} {'couleur' if body.color == 'color' else 'N&B'} · {'Recto-verso' if body.duplex else 'Recto'}"
    return {"kind": "photocopy", "label": label, "document_id": None, "filename": None,
            "options": {"paper_size": body.paper_size, "color": body.color, "duplex": body.duplex, "copies": body.copies, "page_range": ""},
            "pages": pages, "copies": body.copies, "sheets": sheets, "unit_cents": unit, "subtotal_cents": subtotal,
            "document_pages": body.originals, "selected_pages": None}


# ---------- photocopy ----------
@router.post("/shops/{shop_id}/counter/copy/quote")
async def copy_quote(shop_id: str, body: CopyIn, p: Principal = Depends(require_tenant("orders:read"))):
    shop = await get_shop_or_404(tenant_repo(p), shop_id)
    return finalize(shop["pricing"], [copy_line(shop["pricing"], body)], None, await shop_vat_bp())


@router.post("/shops/{shop_id}/counter/copy", response_model=OrderOut)
async def start_copy(shop_id: str, body: CopyIn, p: Principal = Depends(require_tenant("orders:update"))):
    """« Démarrer la photocopie ». With printer_id: automatic copy — the counter PC's agent scans the original (WIA) and
    prints the copies (Windows spooler); the price is computed from the pages really scanned × copies really printed.
    Without printer_id: manual copy made with the copier's own Copy button (fallback, unchanged)."""
    shop = await get_shop_or_404(tenant_repo(p), shop_id)
    if body.printer_id:
        return await _start_auto_copy(p, shop, body)
    line = copy_line(shop["pricing"], body)
    q = finalize(shop["pricing"], [line], None, await shop_vat_bp())
    order = await _insert_order(_order_doc(shop, "copy", q["lines"], q, p.name, "printing", body.customer_name.strip(), None))
    await audit("order.copy_start", principal=p, resource_type="order", resource_id=order["id"],
                details={"pages": line["pages"], "color": body.color, "paper": body.paper_size})
    return order


async def _reprice(shop: dict, opts: dict, originals: int, copies: int) -> dict:
    body = CopyIn(color=opts["color"], paper_size=opts["paper_size"], duplex=opts["duplex"], originals=originals, copies=copies)
    q = finalize(shop["pricing"], [copy_line(shop["pricing"], body)], None, await shop_vat_bp())
    return {"lines": q["lines"], "total_cents": q["total_cents"], "total_ht_cents": q["total_ht_cents"], "vat_cents": q["vat_cents"],
            "vat_rate_bp": q["vat_rate_bp"], "discount_cents": q["discount_cents"]}


async def _start_auto_copy(p: Principal, shop: dict, body: CopyIn) -> dict:
    repo = tenant_repo(p)
    pr = await repo.find_one("printers", {"id": body.printer_id, "shop_id": shop["id"]})
    if not pr:
        raise HTTPException(status_code=404, detail="Imprimante introuvable")
    if not pr.get("enabled", True):
        raise HTTPException(status_code=409, detail="Cette imprimante est désactivée dans PrintDrop — activez-la dans Imprimantes et périphériques")
    agent = await repo.find_one("agents", {"id": pr["agent_id"], "status": "active"})
    if not agent or not is_online(agent.get("last_seen_at")):
        raise HTTPException(status_code=409, detail="Le PC du comptoir est déconnecté : démarrez PrintDrop sur ce PC et vérifiez sa connexion Internet")
    if pr["status"] != "online":
        raise HTTPException(status_code=409, detail=f"Imprimante indisponible ({pr.get('status_detail') or 'hors ligne'}) : vérifiez qu'elle est allumée, branchée et sans message d'erreur")
    if not agent.get("scanners"):
        raise HTTPException(status_code=409, detail="Aucun scanner détecté sur le PC du comptoir : installez la fonction scan de l'imprimante (pilote officiel du fabricant) puis réessayez")
    caps = agent.get("scanner_caps") or []
    if body.source == "feeder" and caps and not any(c.get("feeder") for c in caps):
        raise HTTPException(status_code=422, detail="Ce scanner n'a pas de chargeur automatique : placez l'original sur la vitre")
    if body.color == "color" and pr.get("supports_color") is False:
        raise HTTPException(status_code=422, detail="Cette imprimante imprime uniquement en noir et blanc")
    if await repo.count("orders", {"copy_job.printer_id": pr["id"], "copy_job.state": "running"}):
        raise HTTPException(status_code=409, detail="Une photocopie est déjà en cours sur cette imprimante — attendez la fin")
    line = copy_line(shop["pricing"], body.model_copy(update={"originals": 1}))  # validates the tariff; real count comes later
    line = {**line, "pages": 0, "sheets": 0, "subtotal_cents": 0, "document_pages": 0}
    q = {"lines": [line], "total_cents": 0, "total_ht_cents": 0, "vat_cents": 0, "vat_rate_bp": await shop_vat_bp(), "discount_cents": 0}
    order = _order_doc(shop, "copy", q["lines"], q, p.name, "printing", body.customer_name.strip(), None)
    cmd = {"id": str(uuid.uuid4()), "agent_id": agent["id"], "shop_id": shop["id"], "type": "copy",
           "payload": {"order_id": order["id"], "printer_name": pr["name"], "color": body.color, "paper_size": body.paper_size,
                       "duplex": body.duplex, "copies": body.copies, "source": body.source, "dpi": 300},
           "status": "queued", "result": {}, "error": "", "created_at": now_utc(), "requested_by": p.user_id}
    order["copy_job"] = {"state": "running", "command_id": cmd["id"], "printer_id": pr["id"], "printer_name": pr.get("display_name") or pr["name"],
                         "source": body.source, "copies_requested": body.copies, "scanned_pages": 0, "copies_printed": None, "error": "",
                         "confirmed_by": "", "options": {"color": body.color, "paper_size": body.paper_size, "duplex": body.duplex}}
    order = await _insert_order(order)
    await repo.insert("agent_commands", cmd)
    await audit("order.copy_auto_start", principal=p, resource_type="order", resource_id=order["id"],
                details={"printer": pr["name"], "copies": body.copies, "color": body.color, "source": body.source})
    return order


async def apply_copy_result(cmd: dict, ok: bool, result: dict, error: str) -> None:
    """Agent report for an automatic copy. Charged only on what really came out; anything uncertain => staff confirm."""
    order = await db.orders.find_one({"id": cmd["payload"]["order_id"], "org_id": cmd["org_id"]}, {"_id": 0})
    if not order or (order.get("copy_job") or {}).get("state") != "running":
        return  # idempotent: already resolved
    job, now = order["copy_job"], now_utc()
    scanned = int(result.get("scanned_pages") or 0)
    printed = result.get("copies_printed")
    printed = int(printed) if isinstance(printed, int) else None
    err = (error or result.get("error") or "")[:300]
    base = {"id": order["id"], "copy_job.state": "running"}
    if not ok and scanned == 0:  # nothing scanned => nothing printed, nothing charged
        await db.orders.update_one(base, {"$set": {"copy_job.state": "failed", "copy_job.error": err or "Échec du scan", "status": "cancelled", "updated_at": now},
                                          "$unset": {"active_code": ""},
                                          "$push": {"history": {"status": "cancelled", "at": now, "by": "Système (photocopie échouée, rien facturé)"}}})
        return
    if ok and result.get("spool_confirmed") and not err and scanned > 0 and printed == job["copies_requested"]:
        shop = await db.shops.find_one({"id": order["shop_id"]}, {"_id": 0})
        totals = await _reprice(shop, job["options"], scanned, printed)
        await db.orders.update_one(base, {"$set": {**totals, "copy_job.state": "done", "copy_job.scanned_pages": scanned, "copy_job.copies_printed": printed,
                                                   "status": "ready", "updated_at": now},
                                          "$push": {"history": {"status": "ready", "at": now, "by": f"Agent (photocopie : {scanned} p. × {printed})"}}})
        return
    await db.orders.update_one(base, {"$set": {
        "copy_job.state": "needs_confirmation", "copy_job.scanned_pages": scanned, "copy_job.copies_printed": printed, "updated_at": now,
        "copy_job.error": err or "Windows n'a pas confirmé la fin de l'impression : comptez les copies sorties"}})


async def expire_copy_commands() -> None:
    """Background: a copy the agent never answered. Never delivered => cancelled (no charge); delivered => staff confirm."""
    async for cmd in db.agent_commands.find({"type": "copy", "status": {"$in": ["queued", "sent"]}, "created_at": {"$lt": now_utc() - COPY_TIMEOUT}}, {"_id": 0}):
        res = await db.agent_commands.update_one({"id": cmd["id"], "status": cmd["status"]}, {"$set": {"status": "expired", "error": "L'agent n'a pas répondu"}})
        if res.modified_count:
            delivered = cmd["status"] == "sent"
            await apply_copy_result(cmd, delivered, {}, "Le PC du comptoir n'a pas donné de nouvelles : vérifiez les copies sorties" if delivered
                                    else "Le PC du comptoir n'a jamais reçu la photocopie (déconnecté)")


@router.post("/orders/{order_id}/copy/confirm", response_model=OrderOut)
async def confirm_copy(order_id: str, body: CopyConfirmIn, p: Principal = Depends(require_tenant("orders:update"))):
    """Staff state what really came out when the printer could not confirm it. 0 => cancelled, nothing charged."""
    repo = tenant_repo(p)
    order = await get_order_or_404(repo, order_id)
    job = order.get("copy_job")
    if not job or job["state"] != "needs_confirmation":
        raise HTTPException(status_code=409, detail="Rien à confirmer pour cette photocopie")
    now, f = now_utc(), {"id": order_id, "copy_job.state": "needs_confirmation"}
    if body.originals == 0 or body.copies == 0:
        n = await repo.update_one("orders", f, {"$set": {"copy_job.state": "failed", "copy_job.confirmed_by": p.name, "status": "cancelled", "updated_at": now},
                                              "$unset": {"active_code": ""},
                                              "$push": {"history": {"status": "cancelled", "at": now, "by": f"{p.name} (aucune copie, rien facturé)"}}})
    else:
        shop = await get_shop_or_404(repo, order["shop_id"])
        totals = await _reprice(shop, job["options"], body.originals, body.copies)
        n = await repo.update_one("orders", f, {"$set": {**totals, "copy_job.state": "done", "copy_job.scanned_pages": body.originals,
                                                     "copy_job.copies_printed": body.copies, "copy_job.confirmed_by": p.name, "status": "ready", "updated_at": now},
                                              "$push": {"history": {"status": "ready", "at": now, "by": f"{p.name} (confirmé : {body.originals} p. × {body.copies})"}}})
    if not n:
        raise HTTPException(status_code=409, detail="Cette photocopie a déjà été confirmée")
    await audit("order.copy_confirm", principal=p, resource_type="order", resource_id=order_id, details=body.model_dump())
    return await get_order_or_404(repo, order_id)


# ---------- scan sessions ----------
async def _session(p: Principal, session_id: str) -> dict:
    s = await tenant_repo(p).find_one("scan_sessions", {"id": session_id})
    if not s:
        raise HTTPException(status_code=404, detail="Session de scan introuvable")
    return s


async def _session_out(p: Principal, s: dict) -> dict:
    if s.get("command_id") and s["status"] == "scanning":
        cmd = await tenant_repo(p).find_one("agent_commands", {"id": s["command_id"]})
        if cmd and (cmd["status"] in ("done", "failed") or (cmd["status"] in ("queued", "sent") and now_utc() - cmd["created_at"] > timedelta(minutes=5))):
            if cmd["status"] == "done":
                err = ""
            elif cmd["status"] == "failed":
                err = cmd.get("error") or "Échec du scan"
            else:
                err = "Le scanner n'a pas répondu — vérifiez qu'il est allumé et que le PC du comptoir est connecté"
            s = {**s, "status": "open", "error": err}
            await tenant_repo(p).update_one("scan_sessions", {"id": s["id"]}, {"$set": {"status": "open", "error": err}})
    pages = await db.scan_pages.find({"session_id": s["id"], "org_id": s["org_id"]}, {"_id": 0, "storage_key": 0}).sort("index", 1).to_list(MAX_PAGES)
    agent = await db.agents.find_one({"id": s.get("agent_id"), "org_id": s["org_id"], "status": "active"}, {"_id": 0}) if s.get("agent_id") else None
    return {**s, "pages": pages, "agent_online": bool(agent and is_online(agent.get("last_seen_at"))),
            "scanners": (agent or {}).get("scanners", []), "scanner_caps": (agent or {}).get("scanner_caps", [])}


@router.post("/shops/{shop_id}/scan-sessions", response_model=ScanSessionOut)
async def create_session(shop_id: str, body: ScanSessionIn, p: Principal = Depends(require_tenant("orders:update"))):
    await get_shop_or_404(tenant_repo(p), shop_id)
    agent = await tenant_repo(p).find_one("agents", {"id": body.agent_id, "shop_id": shop_id, "status": "active"}) if body.agent_id else None
    if body.agent_id and not agent:
        raise HTTPException(status_code=404, detail="Poste du comptoir introuvable")
    caps = (agent or {}).get("scanner_caps") or []
    if caps and body.source == "feeder" and not any(c.get("feeder") for c in caps):
        raise HTTPException(status_code=422, detail="Ce scanner n'a pas de chargeur automatique : utilisez la vitre")
    if caps and body.duplex and not any(c.get("duplex") for c in caps):
        raise HTTPException(status_code=422, detail="Ce scanner ne numérise pas en recto-verso")
    s = {"id": str(uuid.uuid4()), "org_id": p.org_id, "shop_id": shop_id, "agent_id": body.agent_id, "format": body.format, "color": body.color,
         "dpi": body.dpi, "source": body.source, "duplex": body.duplex and body.source == "feeder", "status": "open", "error": "", "command_id": None, "order_id": None,
         "created_at": now_utc(), "created_by": p.user_id}
    await tenant_repo(p).insert("scan_sessions", s)
    return await _session_out(p, s)


@router.get("/scan-sessions/{session_id}", response_model=ScanSessionOut)
async def get_session(session_id: str, p: Principal = Depends(require_tenant("orders:read"))):
    return await _session_out(p, await _session(p, session_id))


@router.post("/scan-sessions/{session_id}/scan", response_model=ScanSessionOut)
async def start_scan(session_id: str, p: Principal = Depends(require_tenant("orders:update"))):
    """« Lancer le scan »: asks the counter PC's agent to scan with the paired scanner (WIA)."""
    s = await _session(p, session_id)
    if s["status"] == "finalized":
        raise HTTPException(status_code=409, detail="Cette session est terminée")
    if s["status"] == "scanning":
        raise HTTPException(status_code=409, detail="Un scan est déjà en cours")  # duplicate click
    agent = await tenant_repo(p).find_one("agents", {"id": s.get("agent_id"), "status": "active"}) if s.get("agent_id") else None
    if not agent or not is_online(agent.get("last_seen_at")):
        raise HTTPException(status_code=409, detail="Agent Windows hors ligne : démarrez PrintDrop sur le PC du comptoir, ou importez les fichiers du logiciel du scanner")
    cmd = {"id": str(uuid.uuid4()), "agent_id": agent["id"], "shop_id": s["shop_id"], "type": "scan",
           "payload": {"session_id": s["id"], "color": s["color"], "dpi": s["dpi"], "source": s["source"], "duplex": s.get("duplex", False)},
           "status": "queued", "result": {}, "error": "", "created_at": now_utc(), "requested_by": p.user_id}
    await tenant_repo(p).insert("agent_commands", cmd)
    await tenant_repo(p).update_one("scan_sessions", {"id": s["id"]}, {"$set": {"status": "scanning", "error": "", "command_id": cmd["id"]}})
    return await _session_out(p, {**s, "status": "scanning", "error": "", "command_id": cmd["id"]})


def _normalise_image(data: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Fichier image illisible (JPG ou PNG attendu)") from exc
    img = ImageOps.exif_transpose(img).convert("RGB")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


async def add_page(s: dict, data: bytes, by: str) -> dict:
    if s["status"] == "finalized":
        raise HTTPException(status_code=409, detail="Cette session est terminée")
    if len(data) > MAX_PAGE_BYTES:
        raise HTTPException(status_code=413, detail="Page trop lourde (15 Mo max)")
    count = await db.scan_pages.count_documents({"session_id": s["id"]})
    if count >= MAX_PAGES:
        raise HTTPException(status_code=422, detail=f"{MAX_PAGES} pages maximum par scan")
    jpg = _normalise_image(data)
    key = await save_file(s["org_id"], s["shop_id"], jpg, "jpg")
    w, h = Image.open(io.BytesIO(jpg)).size
    page = {"id": str(uuid.uuid4()), "session_id": s["id"], "org_id": s["org_id"], "storage_key": key, "index": count,
            "rotation": 0, "width": w, "height": h, "created_at": now_utc(), "by": by}
    await db.scan_pages.insert_one(dict(page))
    return page


@router.post("/scan-sessions/{session_id}/upload", response_model=ScanSessionOut)
async def import_page(session_id: str, file: UploadFile = File(...), p: Principal = Depends(require_tenant("orders:update"))):
    """Fallback: import a JPG/PNG saved by the scanner's own software (one file per call)."""
    s = await _session(p, session_id)
    await add_page(s, await file.read(MAX_PAGE_BYTES + 1), f"import:{p.name}")
    return await _session_out(p, s)


def _render(data: bytes, rotation: int, color: str, max_side: int | None = None) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    if rotation:
        img = img.rotate(-rotation, expand=True)
    img = img.convert("L") if color == "bw" else img.convert("RGB")
    if max_side:
        img.thumbnail((max_side, max_side))
    return img


@router.get("/scan-sessions/{session_id}/pages/{page_id}/image")
async def page_image(session_id: str, page_id: str, thumb: bool = True, p: Principal = Depends(require_tenant("orders:read"))):
    s = await _session(p, session_id)
    pg = await db.scan_pages.find_one({"id": page_id, "session_id": s["id"], "org_id": p.org_id}, {"_id": 0})
    if not pg:
        raise HTTPException(status_code=404, detail="Page introuvable")
    out = io.BytesIO()
    _render(await read_file(pg["storage_key"]), pg["rotation"], s["color"], 900 if thumb else None).save(out, "JPEG", quality=80)
    return Response(out.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.patch("/scan-sessions/{session_id}/pages/{page_id}", response_model=ScanSessionOut)
async def update_page(session_id: str, page_id: str, body: ScanPageUpdateIn, p: Principal = Depends(require_tenant("orders:update"))):
    s = await _session(p, session_id)
    res = await db.scan_pages.update_one({"id": page_id, "session_id": s["id"], "org_id": p.org_id}, {"$set": {"rotation": body.rotation % 360}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Page introuvable")
    return await _session_out(p, s)


@router.delete("/scan-sessions/{session_id}/pages/{page_id}", response_model=ScanSessionOut)
async def delete_page(session_id: str, page_id: str, p: Principal = Depends(require_tenant("orders:update"))):
    s = await _session(p, session_id)
    pg = await db.scan_pages.find_one_and_delete({"id": page_id, "session_id": s["id"], "org_id": p.org_id})
    if pg:
        await delete_file(pg["storage_key"])
        async for i, other in _aenumerate(db.scan_pages.find({"session_id": s["id"]}, {"_id": 0, "id": 1}).sort("index", 1)):
            await db.scan_pages.update_one({"id": other["id"]}, {"$set": {"index": i}})
    return await _session_out(p, s)


async def _aenumerate(cursor):
    i = 0
    async for x in cursor:
        yield i, x
        i += 1


@router.post("/scan-sessions/{session_id}/finalize", response_model=OrderOut)
async def finalize_scan(session_id: str, body: ScanFinalizeIn, p: Principal = Depends(require_tenant("orders:update"))):
    """Builds the delivered file (one PDF, or one JPG for a single page), creates the scan order. Idempotent."""
    s = await _session(p, session_id)
    if s.get("order_id"):
        return await tenant_repo(p).find_one("orders", {"id": s["order_id"]})  # double click: same order
    pages = await db.scan_pages.find({"session_id": s["id"], "org_id": p.org_id}, {"_id": 0}).sort("index", 1).to_list(MAX_PAGES)
    if not pages:
        raise HTTPException(status_code=422, detail="Aucune page scannée")
    if s["format"] == "jpg" and len(pages) > 1:
        raise HTTPException(status_code=422, detail="Le format JPG ne contient qu'une page : choisissez PDF pour un document de plusieurs pages")
    imgs = [_render(await read_file(pg["storage_key"]), pg["rotation"], s["color"]) for pg in pages]
    out = io.BytesIO()
    if s["format"] == "pdf":
        imgs[0].save(out, "PDF", save_all=True, append_images=imgs[1:], resolution=float(s["dpi"]))
    else:
        imgs[0].save(out, "JPEG", quality=92, dpi=(s["dpi"], s["dpi"]))
    shop = await get_shop_or_404(tenant_repo(p), s["shop_id"])
    key = await save_file(p.org_id, shop["id"], out.getvalue(), s["format"])
    stamp = now_utc().strftime("%Y%m%d-%H%M")
    doc = {"id": str(uuid.uuid4()), "org_id": p.org_id, "shop_id": shop["id"], "storage_key": key, "kind": s["format"],
           "filename": f"scan-{stamp}.{s['format']}", "page_count": len(pages), "size_bytes": out.tell(), "sha256": "",
           "status": "attached", "order_id": None, "created_at": now_utc(), "source": "scan"}
    pr_ = shop["pricing"]
    unit = (pr_.get("scan_color_cents") if pr_.get("scan_color_cents") is not None else pr_["scan_cents"]) if s["color"] == "color" else pr_["scan_cents"]
    line = {"kind": "scan", "label": f"Numérisation {'couleur' if s['color'] == 'color' else 'N&B'} · {s['dpi']} ppp · {s['format'].upper()}",
            "document_id": doc["id"], "filename": doc["filename"], "options": None, "pages": len(pages), "copies": 1, "sheets": 0,
            "unit_cents": unit, "subtotal_cents": unit * len(pages), "document_pages": len(pages), "selected_pages": None}
    q = finalize(shop["pricing"], [line], None, await shop_vat_bp())
    email = body.customer_email.lower() if body.customer_email else None
    order = _order_doc(shop, "scan", q["lines"], q, p.name, "ready", body.customer_name.strip(), email)
    order["delivery_token"] = secrets.token_urlsafe(24)
    # claim the session first so two concurrent finalize calls cannot create two orders
    claimed = await db.scan_sessions.update_one({"id": s["id"], "order_id": None}, {"$set": {"order_id": order["id"], "status": "finalized"}})
    if not claimed.modified_count:
        await delete_file(key)
        fresh = await _session(p, session_id)
        return await tenant_repo(p).find_one("orders", {"id": fresh["order_id"]})
    doc["order_id"] = order["id"]
    await db.documents.insert_one(dict(doc))
    order = await _insert_order(order)
    for pg in pages:  # raw pages are temporary files: erased as soon as the deliverable exists
        await delete_file(pg["storage_key"])
    await db.scan_pages.delete_many({"session_id": s["id"]})
    await audit("order.scan_create", principal=p, resource_type="order", resource_id=order["id"], details={"pages": len(pages), "format": s["format"]})
    return order


@router.post("/orders/{order_id}/scan-email")
async def email_scan(order_id: str, body: ScanEmailIn, request: Request, p: Principal = Depends(require_tenant("orders:update"))):
    from lib.notify import send_email
    order = await tenant_repo(p).find_one("orders", {"id": order_id, "service": "scan"})
    if not order or not order.get("delivery_token"):
        raise HTTPException(status_code=404, detail="Commande de scan introuvable")
    if order["payment_status"] == "unpaid":
        raise HTTPException(status_code=409, detail="Encaissez la commande avant d'envoyer le scan")
    link = f"{request_origin_https(request)}/scan/{order['delivery_token']}"
    try:
        await send_email(to=body.email, subject=f"Votre scan — {order['shop_name']}", html=(
            f"<p>Bonjour,</p><p>Votre document numérisé chez <strong>{order['shop_name']}</strong> est prêt.</p>"
            f'<p><a href="{link}">Télécharger mon scan</a></p><p>Le lien est valable 24 heures après le premier téléchargement.</p>'))
    except Exception as exc:
        logger.warning("scan email failed for %s: %s", order_id, exc)
        raise HTTPException(status_code=502, detail="L'e-mail n'a pas pu être envoyé — montrez le QR code au client") from exc
    await tenant_repo(p).update_one("orders", {"id": order_id}, {"$set": {"customer_email": body.email.lower()}})
    await audit("order.scan_email", principal=p, resource_type="order", resource_id=order_id)
    return {"ok": True}


def request_origin_https(request: Request) -> str:
    origin = request_origin(request) or ""
    return origin if origin.startswith("https://") else origin.replace("http://", "https://", 1)


# ---------- customer delivery (no account, no code: the unguessable link is the credential) ----------
async def _scan_by_token(token: str) -> tuple[dict, dict | None]:
    order = await db.orders.find_one({"delivery_token": token, "service": "scan"}, {"_id": 0})
    if not order or len(token) < 20:
        raise HTTPException(status_code=404, detail="Lien de scan invalide")
    doc = await db.documents.find_one({"order_id": order["id"], "org_id": order["org_id"]}, {"_id": 0})
    return order, doc


@public_router.get("/scans/{token}", response_model=ScanPublicOut)
async def scan_info(token: str):
    order, doc = await _scan_by_token(token)
    available = bool(doc and doc.get("storage_key") and doc.get("status") != "purged")
    return ScanPublicOut(shop_name=order["shop_name"], filename=(doc or {}).get("filename") or "scan", pages=(doc or {}).get("page_count") or 0,
                         kind=(doc or {}).get("kind") or "pdf", paid=order["payment_status"] != "unpaid", available=available,
                         first_download_at=order.get("scan_downloaded_at"))


@public_router.get("/scans/{token}/file")
async def scan_file(token: str):
    order, doc = await _scan_by_token(token)
    if order["payment_status"] == "unpaid":
        raise HTTPException(status_code=402, detail="Le scan sera disponible dès le paiement au comptoir")
    if not doc or doc.get("status") == "purged" or not doc.get("storage_key"):
        raise HTTPException(status_code=410, detail="Ce scan a été supprimé (24 h après le premier téléchargement)")
    try:
        data = await read_file(doc["storage_key"])
    except (StorageError, OSError) as exc:
        raise HTTPException(status_code=410, detail="Ce scan n'est plus disponible") from exc
    now = now_utc()
    first = await db.orders.update_one({"id": order["id"], "scan_downloaded_at": None}, {"$set": {
        "scan_downloaded_at": now, "status": "delivered", "updated_at": now}, "$unset": {"active_code": ""},
        "$push": {"history": {"status": "delivered", "at": now, "by": "Client (téléchargement)"}}})
    if first.modified_count:
        await audit("order.scan_delivered", org_id=order["org_id"], resource_type="order", resource_id=order["id"], actor="client")
        from lib.retention import purge_order
        await purge_order(order["id"])  # shop rule: the scan is erased right after the first download (bytes already in memory)
    return Response(data, media_type=MEDIA_TYPES[doc["kind"]], headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{urlquote(doc['filename'])}",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
