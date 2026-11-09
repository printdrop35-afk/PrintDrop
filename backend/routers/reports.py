"""Dashboard reports, printer/print alerts, and the platform cron endpoint for the 21h owner e-mail."""

import asyncio
import hmac
import logging
import os
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pymongo.errors import DuplicateKeyError

from lib.authz import Principal, TenantRepo, audit, now_utc, request_origin, require_tenant, tenant_repo
from lib.db import db
from lib.notify import NotifyError, send_email
from lib.paper import paper_levels
from lib.printing import is_online
from lib.reports import build_daily, report_email, today_paris
from models.schemas import AlertOut, CashSummaryOut, DailyReportOut, PaperStockIn, PaperStockOut, ReportSettingsIn, ReportSettingsOut
from routers.dashboard import get_shop_or_404

router = APIRouter(tags=["reports"])
logger = logging.getLogger(__name__)


# ---------- alerts ----------
@router.get("/shops/{shop_id}/alerts", response_model=list[AlertOut])
async def shop_alerts(shop_id: str, p: Principal = Depends(require_tenant("orders:read"))):
    repo = tenant_repo(p)
    shop = await get_shop_or_404(repo, shop_id)
    alerts: list[AlertOut] = []
    for lv in await paper_levels(p.org_id or "", shop):
        if lv["level"] != "ok":
            what = "épuisé" if lv["level"] == "out" else f"bientôt épuisé ({lv['pct_used']} % utilisé)"
            alerts.append(AlertOut(kind="low_paper", since=lv["set_at"],
                                   message=f"Papier {lv['paper_size']} {what} : {lv['remaining_sheets']} feuille(s) restante(s) sur {lv['stock_sheets']}"))
    agents = await repo.find("agents", {"shop_id": shop_id, "status": "active"})
    online_agents = set()
    for a in agents:
        if is_online(a.get("last_seen_at")):
            online_agents.add(a["id"])
        else:
            alerts.append(AlertOut(kind="agent_offline", message=f"Agent « {a['name']} » déconnecté — aucune impression automatique possible",
                                   since=a.get("last_seen_at") or a["created_at"]))
    for pr in await repo.find("printers", {"shop_id": shop_id, "enabled": True, "agent_id": {"$in": list(online_agents)}}):
        if pr["status"] != "online":
            label = "en erreur" if pr["status"] == "error" else "hors ligne"
            alerts.append(AlertOut(kind="printer_offline", printer_name=pr["name"], since=pr.get("last_seen_at") or now_utc(),
                                   message=f"Imprimante « {pr['name']} » {label}{' : ' + pr['status_detail'] if pr['status_detail'] else ''}"))
    since = now_utc() - timedelta(hours=24)
    failed = await repo.find("print_jobs", {"shop_id": shop_id, "status": "failed", "updated_at": {"$gte": since}}, sort=[("updated_at", -1)])
    seen: set[tuple[str, int]] = set()
    for j in failed:
        key = (j["order_id"], j["line_index"])
        if key in seen:
            continue
        seen.add(key)
        newer = await repo.count("print_jobs", {"order_id": j["order_id"], "line_index": j["line_index"],
                                                "created_at": {"$gt": j["created_at"]}, "status": {"$ne": "cancelled"}})
        order = await repo.find_one("orders", {"id": j["order_id"]})
        if newer or not order or order["status"] in ("picked_up", "cancelled"):
            continue
        alerts.append(AlertOut(kind="job_failed", order_id=j["order_id"], order_code=j["order_code"], since=j["updated_at"],
                               message=f"Échec d'impression {j['order_code']} ({j['filename']}) : {j['error'] or 'erreur inconnue'}"))
    return alerts


# ---------- paper stock ----------
@router.get("/shops/{shop_id}/paper-stock", response_model=PaperStockOut)
async def get_paper(shop_id: str, p: Principal = Depends(require_tenant("orders:read"))):
    shop = await get_shop_or_404(tenant_repo(p), shop_id)
    return PaperStockOut(alert_pct=shop.get("paper_alert_pct", 80), levels=await paper_levels(p.org_id or "", shop))


@router.put("/shops/{shop_id}/paper-stock", response_model=PaperStockOut)
async def put_paper(shop_id: str, body: PaperStockIn, p: Principal = Depends(require_tenant("paper:manage"))):
    repo = tenant_repo(p)
    shop = await get_shop_or_404(repo, shop_id)
    stock = dict(shop.get("paper_stock") or {})
    now = now_utc()
    for size, sheets in body.stock.items():
        if sheets is None:
            stock.pop(size, None)
        else:
            stock[size] = {"sheets": sheets, "set_at": now}
    await repo.update_one("shops", {"id": shop_id}, {"$set": {"paper_stock": stock, "paper_alert_pct": body.alert_pct}})
    await audit("paper.stock", principal=p, resource_type="shop", resource_id=shop_id,
                details={"stock": {k: v for k, v in body.stock.items()}, "alert_pct": body.alert_pct})
    return await get_paper(shop_id, p)


# ---------- reports ----------
def parse_day(day: str | None) -> date:
    today = today_paris()
    if not day:
        return today
    try:
        d = date.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Date invalide (AAAA-MM-JJ)") from exc
    if d > today:
        raise HTTPException(status_code=422, detail="Date dans le futur")
    return d


@router.get("/shops/{shop_id}/reports/daily", response_model=DailyReportOut)
async def daily(shop_id: str, day: str | None = Query(default=None), p: Principal = Depends(require_tenant("reports:read"))):
    repo = tenant_repo(p)
    shop = await get_shop_or_404(repo, shop_id)
    return await build_daily(p.org_id or "", shop, parse_day(day))


@router.get("/reports/settings", response_model=ReportSettingsOut)
async def get_settings(p: Principal = Depends(require_tenant("reports:read"))):
    org = await db.organizations.find_one({"id": p.org_id}, {"_id": 0})
    owner = await db.users.find_one({"id": org["owner_id"]}, {"_id": 0, "email": 1}) if org else None
    return ReportSettingsOut(daily_email=bool(org and org.get("report_email", True)), recipient=owner["email"] if owner else "")


@router.put("/reports/settings", response_model=ReportSettingsOut)
async def put_settings(body: ReportSettingsIn, p: Principal = Depends(require_tenant("reports:manage"))):
    await db.organizations.update_one({"id": p.org_id}, {"$set": {"report_email": body.daily_email}})
    await audit("reports.settings", principal=p, resource_type="organization", resource_id=p.org_id or "", details=body.model_dump())
    return await get_settings(p)


async def send_org_report(org: dict, day: date, origin: str, force: bool = False) -> bool:
    """One e-mail per organization per day (all shops), to the owner's account address."""
    if not force:
        try:
            await db.report_emails.insert_one({"org_id": org["id"], "day": day.isoformat(), "at": now_utc()})
        except DuplicateKeyError:
            return False
    owner = await db.users.find_one({"id": org["owner_id"], "active": True}, {"_id": 0, "email": 1})
    shops = await TenantRepo(org["id"]).find("shops", sort=[("created_at", 1)])
    if not owner or not shops:
        return False
    reports = [await build_daily(org["id"], s, day) for s in shops]
    subject, html = report_email(reports, org["name"], f"{origin.rstrip('/')}/dashboard/rapports")
    await send_email(to=owner["email"], subject=subject, html=html)
    await audit("reports.emailed", org_id=org["id"], actor="systeme", resource_type="organization", resource_id=org["id"],
                details={"day": day.isoformat()})
    return True


@router.post("/reports/email-now")
async def email_now(request: Request, p: Principal = Depends(require_tenant("reports:manage"))):
    org = await db.organizations.find_one({"id": p.org_id}, {"_id": 0})
    assert org
    try:
        await send_org_report(org, today_paris(), request_origin(request), force=True)
    except NotifyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    owner = await db.users.find_one({"id": org["owner_id"]}, {"_id": 0, "email": 1})
    return {"sent_to": owner["email"] if owner else ""}


# ---------- platform cron ----------
async def _run_daily_reports(origin: str) -> None:
    day = today_paris()
    async for org in db.organizations.find({"status": "active", "report_email": {"$ne": False}}, {"_id": 0}):
        try:
            await send_org_report(org, day, origin)
        except Exception as exc:  # one org failing must not stop the others
            logger.warning("daily report %s: %s", org["id"], exc)


@router.post("/cron/daily-report")
async def cron_daily_report(request: Request, authorization: str = Header(default=""), x_webhook_id: str = Header(default="")):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        envelope = await request.json()
    except ValueError:
        envelope = None
    if envelope is not None and not isinstance(envelope, dict):
        raise HTTPException(status_code=400, detail="Invalid body")
    run_id = x_webhook_id or (envelope or {}).get("run_id") or ""
    if run_id:
        try:
            await db.cron_runs.insert_one({"run_id": run_id, "name": "daily-report", "at": now_utc()})
        except DuplicateKeyError:
            return {"status": "duplicate"}
    asyncio.create_task(_run_daily_reports(request_origin(request)))
    return {"status": "accepted"}


@router.post("/cron/retention")
async def cron_retention(authorization: str = Header(default="")):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    """Hourly: erase documents + customer identity of collected/cancelled orders and of orders older than 7 days (idempotent)."""
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    from lib.retention import run_retention
    asyncio.create_task(run_retention())
    return {"status": "accepted"}


@router.get("/shops/{shop_id}/reports/cash", response_model=CashSummaryOut)
async def cash_summary(shop_id: str, day: str | None = Query(default=None), p: Principal = Depends(require_tenant("reports:read"))):
    """Clôture de caisse: payments recorded that day (Europe/Paris), split Espèce / Carte / autre. Read-only."""
    from lib.authz import now_utc
    from lib.reports import day_bounds
    repo = tenant_repo(p)
    shop = await get_shop_or_404(repo, shop_id)
    d = parse_day(day)
    start, end = day_bounds(d)
    pays = await repo.find("payments", {"shop_id": shop_id, "created_at": {"$gte": start, "$lt": end}}, sort=[("created_at", 1)], limit=5000)
    orders = {o["id"]: o for o in await repo.find("orders", {"id": {"$in": [x["order_id"] for x in pays]}}, limit=5000)} if pays else {}
    tot = {"cash": [0, 0], "card_terminal": [0, 0], "other": [0, 0]}
    rows = []
    for x in pays:
        k = x["method"] if x["method"] in ("cash", "card_terminal") else "other"
        tot[k][0] += x["amount_cents"]
        tot[k][1] += 1
        o = orders.get(x["order_id"], {})
        rows.append({"at": x["created_at"], "order_code": o.get("code", "?"), "service": o.get("service", "print"),
                     "method": x["method"], "amount_cents": x["amount_cents"]})
    return {"day": d.isoformat(), "shop_id": shop_id, "shop_name": shop["name"], "shop_address": shop.get("address", ""),
            "cash_cents": tot["cash"][0], "cash_count": tot["cash"][1], "card_cents": tot["card_terminal"][0], "card_count": tot["card_terminal"][1],
            "other_cents": tot["other"][0], "other_count": tot["other"][1],
            "total_cents": sum(v[0] for v in tot.values()), "total_count": len(pays), "payments": rows, "generated_at": now_utc()}
