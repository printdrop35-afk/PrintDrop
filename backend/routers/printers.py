"""Paramètres → Imprimantes et périphériques: discovery & configuration through the Windows agent
(commands channel), assignment rules, « IMPRIMER DIRECTEMENT », print queue, onboarding, agent download.

Nothing here invents hardware: printers only exist once an agent reports them, discovery results
come verbatim from the agent, and every check uses server-side state."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from lib.agent_release import get_release
from lib.authz import Principal, audit, now_utc, require_tenant, tenant_repo
from lib.db import db
from lib.printing import ACTIVE_JOB_STATUSES, check_printer, enqueue_initial_jobs, is_online, pick_printer, shop_printers
from models.schemas import (
    AgentDownloadOut, AgentRefIn, CommandOut, ConnectPrinterIn, DiscoverIn, InstallPrinterIn, ManualPrinterIn, OnboardingStep, PrintCheckLine, PrintCheckOut, PrintDirectIn,
    PrintJobOut, PrinterRulesIO, ReassignIn,
)
from routers.dashboard import get_order_or_404, get_shop_or_404

router = APIRouter()
COMMAND_TTL = timedelta(minutes=3)
DEFAULT_PORTS = {"ipp": 631, "raw9100": 9100, "lpd": 515}


async def _agent_of_shop(p: Principal, shop_id: str, agent_id: str) -> dict:
    agent = await tenant_repo(p).find_one("agents", {"id": agent_id, "shop_id": shop_id, "status": "active"})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent introuvable pour cette boutique")
    if not is_online(agent.get("last_seen_at")):
        raise HTTPException(status_code=409, detail="L'agent Windows est hors ligne — démarrez PrintDrop sur le PC du comptoir")
    return agent


async def _command(p: Principal, agent: dict, ctype: str, payload: dict) -> dict:
    doc = {"id": str(uuid.uuid4()), "agent_id": agent["id"], "shop_id": agent["shop_id"], "type": ctype, "payload": payload,
           "status": "queued", "result": {}, "error": "", "created_at": now_utc(), "requested_by": p.user_id}
    await tenant_repo(p).insert("agent_commands", doc)
    await audit(f"device.{ctype}", principal=p, resource_type="agent", resource_id=agent["id"], details={k: v for k, v in payload.items() if k != "secret"})
    return doc


async def _printer(p: Principal, printer_id: str) -> dict:
    printer = await tenant_repo(p).find_one("printers", {"id": printer_id})
    if not printer:
        raise HTTPException(status_code=404, detail="Imprimante introuvable")
    return printer


@router.post("/shops/{shop_id}/printers/discover", response_model=CommandOut)
async def discover(shop_id: str, body: DiscoverIn, p: Principal = Depends(require_tenant("devices:manage"))):
    await get_shop_or_404(tenant_repo(p), shop_id)
    agent = await _agent_of_shop(p, shop_id, body.agent_id)
    return await _command(p, agent, "discover_usb" if body.kind == "usb" else "discover_network", {})


@router.post("/shops/{shop_id}/printers/discover-all", response_model=CommandOut)
async def discover_all(shop_id: str, body: AgentRefIn, p: Principal = Depends(require_tenant("devices:manage"))):
    """« Ajouter une imprimante »: the agent lists printers installed in Windows, USB devices without a driver and
    printers answering on the local network (with make/model when they report it over IPP)."""
    await get_shop_or_404(tenant_repo(p), shop_id)
    return await _command(p, await _agent_of_shop(p, shop_id, body.agent_id), "discover_all", {})


@router.post("/shops/{shop_id}/printers/install", response_model=CommandOut)
async def install_printer(shop_id: str, body: InstallPrinterIn, p: Principal = Depends(require_tenant("devices:manage"))):
    """One-click install in Windows: network = driverless IPP (Microsoft IPP class driver); USB = Windows driver search.
    Windows may ask the employee for administrator approval. Missing driver => the agent says so (never a fake success)."""
    await get_shop_or_404(tenant_repo(p), shop_id)
    if body.kind == "network" and not body.host:
        raise HTTPException(status_code=422, detail="Adresse de l'imprimante manquante")
    agent = await _agent_of_shop(p, shop_id, body.agent_id)
    return await _command(p, agent, "install_printer", body.model_dump(exclude={"agent_id"}))


@router.post("/shops/{shop_id}/printers/connect", response_model=CommandOut)
async def connect_printer(shop_id: str, body: ConnectPrinterIn, p: Principal = Depends(require_tenant("devices:manage"))):
    """« Connecter cette imprimante »: enables a Windows printer reported by the agent, then verifies it for real."""
    import asyncio
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    agent = await _agent_of_shop(p, shop_id, body.agent_id)
    pr = None
    for _ in range(8):  # a printer installed a moment ago appears at the agent's next signal (≤ 5 s)
        pr = await repo.find_one("printers", {"agent_id": agent["id"], "shop_id": shop_id, "name": body.name})
        if pr:
            break
        await asyncio.sleep(1.5)
    if not pr:
        raise HTTPException(status_code=404, detail="Windows n'a pas encore signalé cette imprimante — patientez quelques secondes puis réessayez")
    await repo.update_one("printers", {"id": pr["id"]}, {"$set": {"enabled": True, "verified_at": None}})
    if not await repo.count("printers", {"shop_id": shop_id, "is_default": True, "enabled": True}):
        await repo.update_one("printers", {"id": pr["id"]}, {"$set": {"is_default": True}})
    await audit("printer.connect", principal=p, resource_type="printer", resource_id=pr["id"], details={"name": pr["name"]})
    return await _command(p, agent, "test_connection", {"printer_name": pr["name"], "ip_address": pr.get("ip_address", "")})


@router.post("/shops/{shop_id}/printers/manual", response_model=CommandOut)
async def add_manual(shop_id: str, body: ManualPrinterIn, p: Principal = Depends(require_tenant("devices:manage"))):
    await get_shop_or_404(tenant_repo(p), shop_id)
    agent = await _agent_of_shop(p, shop_id, body.agent_id)
    payload = body.model_dump(exclude={"agent_id"})
    payload["port"] = body.port or DEFAULT_PORTS[body.protocol]
    return await _command(p, agent, "add_network_printer", payload)


@router.post("/printers/{printer_id}/test-connection", response_model=CommandOut)
async def test_connection(printer_id: str, p: Principal = Depends(require_tenant("devices:manage"))):
    pr = await _printer(p, printer_id)
    agent = await _agent_of_shop(p, pr["shop_id"], pr["agent_id"])
    return await _command(p, agent, "test_connection", {"printer_name": pr["name"], "ip_address": pr.get("ip_address", "")})


@router.post("/printers/{printer_id}/test-page", response_model=CommandOut)
async def test_page(printer_id: str, p: Principal = Depends(require_tenant("devices:manage"))):
    pr = await _printer(p, printer_id)
    agent = await _agent_of_shop(p, pr["shop_id"], pr["agent_id"])
    return await _command(p, agent, "test_page", {"printer_name": pr["name"]})


@router.get("/agent-commands/{command_id}", response_model=CommandOut)
async def command_status(command_id: str, p: Principal = Depends(require_tenant("devices:read"))):
    cmd = await tenant_repo(p).find_one("agent_commands", {"id": command_id})
    if not cmd:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    if cmd["status"] in ("queued", "sent") and now_utc() - cmd["created_at"] > COMMAND_TTL:
        await tenant_repo(p).update_one("agent_commands", {"id": command_id}, {"$set": {"status": "expired", "error": "L'agent n'a pas répondu à temps"}})
        cmd.update(status="expired", error="L'agent n'a pas répondu à temps")
    return cmd


@router.delete("/printers/{printer_id}")
async def delete_printer(printer_id: str, jobs: str = Query(default="", pattern="^(|cancel|reassign)$"),
                         p: Principal = Depends(require_tenant("devices:manage"))):
    """Active jobs block deletion unless the owner explicitly cancels them or sends them back to automatic assignment."""
    repo = tenant_repo(p)
    pr = await _printer(p, printer_id)
    active = await repo.count("print_jobs", {"printer_id": printer_id, "status": {"$in": ACTIVE_JOB_STATUSES}})
    if active and not jobs:
        raise HTTPException(status_code=409, detail=f"{active} travail(aux) en cours sur cette imprimante — annulez-les ou réaffectez-les d'abord")
    if active:
        upd = {"status": "cancelled"} if jobs == "cancel" else {"printer_id": None}
        await repo.update_many("print_jobs", {"printer_id": printer_id, "status": {"$in": ["queued", "retry_wait"]}}, {"$set": {**upd, "updated_at": now_utc()}})
        if await repo.count("print_jobs", {"printer_id": printer_id, "status": {"$in": ["claimed", "spooled", "printing"]}}):
            raise HTTPException(status_code=409, detail="Un travail est en cours d'impression — réessayez quand il sera terminé")
    await db.printers.delete_one({"id": printer_id, "org_id": p.org_id})
    shop = await repo.find_one("shops", {"id": pr["shop_id"]})
    rules = [r for r in (shop or {}).get("printer_rules", []) if r["printer_id"] != printer_id]
    await repo.update_one("shops", {"id": pr["shop_id"]}, {"$set": {"printer_rules": rules}})
    await audit("printer.delete", principal=p, resource_type="printer", resource_id=printer_id, details={"name": pr["name"], "jobs": jobs or "none"})
    return {"ok": True, "note": "Si l'agent détecte encore cette imprimante dans Windows, elle réapparaîtra désactivée."}


@router.get("/shops/{shop_id}/printer-rules", response_model=PrinterRulesIO)
async def get_rules(shop_id: str, p: Principal = Depends(require_tenant("devices:read"))):
    return {"rules": (await get_shop_or_404(tenant_repo(p), shop_id)).get("printer_rules", [])}


@router.put("/shops/{shop_id}/printer-rules", response_model=PrinterRulesIO)
async def put_rules(shop_id: str, body: PrinterRulesIO, p: Principal = Depends(require_tenant("devices:manage"))):
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    ids = {x["id"] for x in await repo.find("printers", {"shop_id": shop_id})}
    rules = []
    for r in body.rules:
        if r.printer_id not in ids:
            raise HTTPException(status_code=422, detail="Règle : imprimante inconnue pour cette boutique")
        rules.append({**r.model_dump(), "id": r.id or uuid.uuid4().hex[:12]})
    await repo.update_one("shops", {"id": shop_id}, {"$set": {"printer_rules": rules}})
    await audit("printer.rules", principal=p, resource_type="shop", resource_id=shop_id, details={"count": len(rules)})
    return {"rules": rules}


async def _plan(p: Principal, order: dict, forced: str | None) -> PrintCheckOut:
    shop = await get_shop_or_404(tenant_repo(p), order["shop_id"])
    printers = await shop_printers(p.org_id or "", order["shop_id"])
    problems: list[str] = []
    if not printers:
        problems.append("Aucune imprimante configurée — ajoutez-en une dans Imprimantes et périphériques")
    if forced and forced not in {x["id"] for x in printers}:
        raise HTTPException(status_code=404, detail="Imprimante introuvable pour cette boutique")
    if order["status"] not in ("pending", "printing"):
        problems.append("Cette commande n'est plus à imprimer")
    if order["payment_status"] == "unpaid" and not shop.get("allow_print_before_payment", True):
        problems.append("Paiement requis avant impression (réglage de la boutique)")
    lines = []
    for idx, line in enumerate(order["lines"]):
        if line["kind"] != "print" or not line.get("document_id"):
            continue
        pr = pick_printer(printers, shop.get("printer_rules", []), line["options"], forced) if printers else None
        lp, lw = check_printer(pr, line["options"]) if pr else (["Aucune imprimante disponible"], [])
        if lp and not forced:
            others = [x.get("display_name") or x["name"] for x in printers if x is not pr and not check_printer(x, line["options"])[0]]
            if others:
                lw.append("Imprimantes compatibles : " + ", ".join(others))
        lines.append(PrintCheckLine(line_index=idx, filename=line.get("filename"), printer_id=pr["id"] if pr else None,
                                    printer_name=(pr.get("display_name") or pr["name"]) if pr else None, problems=lp, warnings=lw))
    if not lines:
        problems.append("Aucun document à imprimer dans cette commande")
    ok = not problems and all(not line.problems for line in lines)
    return PrintCheckOut(ok=ok, problems=problems, lines=lines)


@router.post("/orders/{order_id}/print-direct", response_model=PrintCheckOut)
async def print_direct(order_id: str, body: PrintDirectIn, p: Principal = Depends(require_tenant("orders:update"))):
    """« IMPRIMER DIRECTEMENT »: owner-triggered; checks permissions, order, payment rule, agent, printer, options."""
    repo = tenant_repo(p)
    order = await get_order_or_404(repo, order_id)
    plan = await _plan(p, order, body.printer_id)
    if body.dry_check or not plan.ok:
        return plan
    already = await repo.count("print_jobs", {"order_id": order_id, "kind": "initial"})
    if already:
        raise HTTPException(status_code=409, detail="Déjà envoyée à l'impression — utilisez « Réimprimer » pour un nouvel exemplaire")
    created = await enqueue_initial_jobs(order, p.name, {line.line_index: line.printer_id for line in plan.lines if line.printer_id})
    if order["status"] == "pending":
        now = now_utc()
        await repo.update_one("orders", {"id": order_id, "status": "pending"}, {
            "$set": {"status": "printing", "updated_at": now}, "$push": {"history": {"status": "printing", "at": now, "by": p.name}}})
    await audit("order.print_direct", principal=p, resource_type="order", resource_id=order_id,
                details={"code": order["code"], "jobs": created, "printers": [line.printer_name for line in plan.lines]})
    plan.jobs_created = created
    return plan


@router.post("/print-jobs/{job_id}/reassign", response_model=PrintJobOut)
async def reassign(job_id: str, body: ReassignIn, p: Principal = Depends(require_tenant("orders:update"))):
    repo = tenant_repo(p)
    job = await repo.find_one("print_jobs", {"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Travail introuvable")
    if job["status"] not in ("queued", "retry_wait"):
        raise HTTPException(status_code=409, detail="Seul un travail en attente peut être réaffecté (réimprimez un travail échoué)")
    target = next((x for x in await shop_printers(p.org_id or "", job["shop_id"]) if x["id"] == body.printer_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Imprimante introuvable pour cette boutique")
    problems, _ = check_printer(target, job["options"])
    if problems:
        raise HTTPException(status_code=409, detail=" · ".join(problems))
    await repo.update_one("print_jobs", {"id": job_id, "status": job["status"]},
                          {"$set": {"printer_id": target["id"], "printer_name": None, "status": "queued", "updated_at": now_utc()}})
    await audit("print_job.reassign", principal=p, resource_type="print_job", resource_id=job_id, details={"to": target["name"]})
    return await repo.find_one("print_jobs", {"id": job_id})


@router.get("/shops/{shop_id}/print-queue", response_model=list[PrintJobOut])
async def print_queue(shop_id: str, scope: str = Query(default="active", pattern="^(active|today)$"),
                      p: Principal = Depends(require_tenant("orders:read"))):
    repo = tenant_repo(p)
    await get_shop_or_404(repo, shop_id)
    f: dict = {"shop_id": shop_id}
    if scope == "active":
        f["$or"] = [{"status": {"$in": ACTIVE_JOB_STATUSES + ["failed"]}}, {"updated_at": {"$gte": now_utc() - timedelta(minutes=15)}}]
    else:
        f["created_at"] = {"$gte": now_utc() - timedelta(hours=24)}
    return await repo.find("print_jobs", f, sort=[("created_at", -1)], limit=200)


@router.get("/onboarding", response_model=list[OnboardingStep])
async def onboarding(p: Principal = Depends(require_tenant("shop:read"))):
    """Progress is derived from real data (auto) or saved by the owner (manual) — resumable at any time."""
    repo = tenant_repo(p)
    org = await db.organizations.find_one({"id": p.org_id}, {"_id": 0})
    marks = (org or {}).get("onboarding", {})
    shops = await repo.find("shops", {})
    shop_ids = [s["id"] for s in shops]
    test_jobs = await repo.find("agent_commands", {"type": "test_page", "status": "done"}, limit=1)
    steps = [
        ("company", "Informations de l'entreprise", bool(org and org.get("name")), True, "/dashboard/boutique"),
        ("shop", "Première boutique", bool(shops), True, "/dashboard/boutique"),
        ("prices", "Services et prix vérifiés", bool(marks.get("prices")), False, "/dashboard/tarifs"),
        ("staff", "Employés ajoutés", await repo.count("memberships", {"active": True}) > 1 or bool(marks.get("staff")), False, "/dashboard/equipe"),
        ("payments", "Moyens de paiement au comptoir choisis", bool(marks.get("payments")), False, "/dashboard/boutique"),
        ("agent", "Agent Windows installé et associé", bool(await repo.count("agents", {"status": "active"})), True, "/dashboard/imprimantes"),
        ("printer", "Imprimante configurée", bool(await repo.count("printers", {"enabled": True})), True, "/dashboard/imprimantes"),
        ("qr", "QR code imprimé et affiché", bool(marks.get("qr")), False, "/dashboard/boutique"),
        ("test_order", "Commande de test reçue", bool(await repo.count("orders", {"shop_id": {"$in": shop_ids}})), True, "/dashboard"),
        ("test_print", "Page de test imprimée", bool(test_jobs) or bool(await repo.count("print_jobs", {"status": "printed"})), True, "/dashboard/imprimantes"),
        ("activate", "Boutique ouverte aux commandes", any(s.get("accepting_orders") for s in shops) and bool(marks.get("activate")), False, "/dashboard/boutique"),
    ]
    return [OnboardingStep(key=k, label=lbl, done=d, auto=a, link=lnk) for k, lbl, d, a, lnk in steps]


@router.post("/onboarding/{step}/done", response_model=list[OnboardingStep])
async def onboarding_mark(step: str, done: bool = True, p: Principal = Depends(require_tenant("shop:edit"))):
    if step not in ("prices", "staff", "payments", "qr", "activate"):
        raise HTTPException(status_code=422, detail="Étape validée automatiquement")
    await db.organizations.update_one({"id": p.org_id}, {"$set": {f"onboarding.{step}": done}})
    return await onboarding(p)


@router.get("/agent-download", response_model=AgentDownloadOut)
async def agent_download(_: Principal = Depends(require_tenant("devices:read"))):
    r = await get_release()
    return AgentDownloadOut(available=bool(r["url"]), url=r["url"], version=r["version"], notes=r["notes"])
