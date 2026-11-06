"""Daily per-shop report (Europe/Paris business day) and the owner e-mail template."""

from datetime import date, datetime, time, timedelta
from html import escape
from zoneinfo import ZoneInfo

from lib.authz import TenantRepo

TZ = ZoneInfo("Europe/Paris")


def today_paris() -> date:
    return datetime.now(TZ).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=TZ)
    return start, start + timedelta(days=1)


async def build_daily(org_id: str, shop: dict, day: date) -> dict:
    repo = TenantRepo(org_id)
    start, end = day_bounds(day)
    rng = {"$gte": start, "$lt": end}
    orders = await repo.find("orders", {"shop_id": shop["id"], "created_at": rng}, limit=10000)
    payments = await repo.find("payments", {"shop_id": shop["id"], "created_at": rng}, limit=10000)
    hours = [{"hour": h, "orders": 0, "revenue_cents": 0} for h in range(24)]
    pages_bw = pages_color = sheets = photocopies = scans = 0
    for o in orders:
        hours[o["created_at"].astimezone(TZ).hour]["orders"] += 1
        if o["status"] == "cancelled":
            continue
        for line in o["lines"]:
            if line["kind"] == "print":
                n = line["pages"] * line["copies"]
                if (line.get("options") or {}).get("color") == "color":
                    pages_color += n
                else:
                    pages_bw += n
                sheets += line["sheets"]
            elif line["kind"] == "photocopy":
                photocopies += line["pages"]
            else:
                scans += line["pages"]
    for p in payments:
        hours[p["created_at"].astimezone(TZ).hour]["revenue_cents"] += p["amount_cents"]
    revenue = sum(p["amount_cents"] for p in payments)
    busiest = max(hours, key=lambda h: (h["orders"], h["revenue_cents"]))
    return {
        "day": day.isoformat(), "shop_id": shop["id"], "shop_name": shop["name"],
        "orders_total": len(orders),
        "orders_cancelled": sum(o["status"] == "cancelled" for o in orders),
        "orders_picked_up": sum(o["status"] == "picked_up" for o in orders),
        "revenue_cents": revenue,
        "revenue_cash_cents": sum(p["amount_cents"] for p in payments if p["method"] == "cash"),
        "revenue_card_cents": sum(p["amount_cents"] for p in payments if p["method"] != "cash"),
        "payments_count": len(payments),
        "avg_basket_cents": revenue // len(payments) if payments else 0,
        "unpaid_cents": sum(o["total_cents"] for o in orders if o["payment_status"] == "unpaid" and o["status"] != "cancelled"),
        "pages_bw": pages_bw, "pages_color": pages_color, "sheets": sheets, "photocopies": photocopies, "scans": scans,
        "jobs_printed": await repo.count("print_jobs", {"shop_id": shop["id"], "status": "printed", "printed_at": rng}),
        "jobs_failed": await repo.count("print_jobs", {"shop_id": shop["id"], "status": "failed", "updated_at": rng}),
        "busiest_hour": busiest["hour"] if busiest["orders"] else None,
        "hours": hours,
    }


def _eur(cents: int) -> str:
    return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")


def report_email(reports: list[dict], org_name: str, link: str) -> tuple[str, str]:
    day = datetime.fromisoformat(reports[0]["day"]).strftime("%d/%m/%Y")
    total = sum(r["revenue_cents"] for r in reports)
    subject = f"Rapport du {day} — {org_name} : {_eur(total)} encaissés"
    blocks = []
    for r in reports:
        busiest = f"{r['busiest_hour']}h–{r['busiest_hour'] + 1}h" if r["busiest_hour"] is not None else "—"
        rows = [
            ("Chiffre d'affaires encaissé", _eur(r["revenue_cents"])),
            ("dont espèces / carte", f"{_eur(r['revenue_cash_cents'])} / {_eur(r['revenue_card_cents'])}"),
            ("Commandes", f"{r['orders_total']} (retirées : {r['orders_picked_up']}, annulées : {r['orders_cancelled']})"),
            ("Panier moyen", _eur(r["avg_basket_cents"])),
            ("Pages imprimées N&B / couleur", f"{r['pages_bw']} / {r['pages_color']}"),
            ("Feuilles utilisées", str(r["sheets"])),
            ("Photocopies / scans", f"{r['photocopies']} / {r['scans']}"),
            ("Heure la plus chargée", busiest),
            ("Reste à encaisser", _eur(r["unpaid_cents"])),
        ]
        trs = "".join(f'<tr><td style="padding:6px 0;color:#64748B">{escape(k)}</td>'
                      f'<td style="padding:6px 0;text-align:right;font-weight:bold">{escape(v)}</td></tr>' for k, v in rows)
        blocks.append(f'<h2 style="font-size:17px;margin:20px 0 6px">{escape(r["shop_name"])}</h2>'
                      f'<table role="presentation" width="100%" style="font-size:14px">{trs}</table>')
    html = (
        '<table role="presentation" width="100%" style="background:#F8FAFC"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0F172A">'
        '<table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #E2E8F0;border-radius:12px">'
        '<tr><td style="padding:24px">'
        '<p style="font-size:13px;color:#2563EB;font-weight:bold;letter-spacing:1px">PRINTDROP · RAPPORT QUOTIDIEN</p>'
        f'<h1 style="font-size:22px;margin:8px 0">{escape(org_name)} — {escape(day)}</h1>'
        f'{"".join(blocks)}'
        f'<p style="margin:24px 0"><a href="{escape(link)}" style="background:#2563EB;color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">Voir le rapport détaillé</a></p>'
        '<p style="font-size:12px;color:#64748B">Envoyé par PrintDrop. Désactivez cet e-mail depuis la page Rapports de votre tableau de bord.</p>'
        '</td></tr></table></td></tr></table>'
    )
    return subject, html
