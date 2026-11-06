"""Pricing v2 (services, rules, discounts, minimum, VAT), price export, tenant isolation of prices,
SaaS plans/settings administration, checkout refusal without provider, webhook verification, migrations."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from lib.billing import add_months, effective_status
from lib.pricing import default_pricing, finalize, parse_page_range, price_extras, price_print
from tests.conftest import api_url

API = api_url("")
SLUG_LYON = "copyprint-bellecour"


def login(email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=API.rstrip("/"), timeout=20)
    r = c.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


def lyon_shop(c: httpx.Client) -> dict:
    return next(s for s in c.get("/auth/me").json()["shops"] if s["slug"] == SLUG_LYON)


def upload(client: httpx.Client, slug: str) -> dict:
    from pypdf import PdfWriter
    import io
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    r = client.post(f"/public/shops/{slug}/documents", files={"file": ("t.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- pure engine ----------
def test_engine_examples_and_vat():
    p = default_pricing()
    assert p["print"]["A4"] == {"bw": 10, "color": 50, "active": True}
    assert p["print"]["A3"]["bw"] == 25 and p["print"]["A3"]["color"] == 100 and p["scan_cents"] == 20
    names = {s["name"]: s for s in p["services"]}
    assert names["Saisie de document"]["price_cents"] == 300 and names["Plastification A4"]["price_cents"] == 200
    assert names["Reliure"]["price_from"] is True
    line = price_print(p, "a.pdf", "d", 10, {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 2, "page_range": ""})
    q = finalize(p, [line], None, 2000)
    assert q["total_cents"] == 200 and q["total_ht_cents"] == 167 and q["vat_cents"] == 33


def test_engine_rules_discounts_minimum():
    p = default_pricing()
    p["rules"] = [{"id": "r", "name": "Volume", "min_pages": 100, "discount_pct": 20, "active": True}]
    p["discounts"] = [
        {"id": "a", "name": "Auto", "code": None, "kind": "fixed", "value": 50, "min_order_cents": 0, "active": True},
        {"id": "b", "name": "Etudiant", "code": "ETU10", "kind": "percent", "value": 10, "min_order_cents": 0, "active": True},
    ]
    p["min_order_cents"] = 300
    line = price_print(p, "a.pdf", "d", 100, {"paper_size": "A4", "color": "color", "duplex": False, "copies": 1, "page_range": ""})
    q = finalize(p, [line], "etu10", 2000)  # 5000 -> rule -1000 -> 4000 -> best of 50c / 10 % (400) = code
    assert q["total_cents"] == 3600 and q["promo_code_applied"] == "ETU10" and q["discount_cents"] == 1400
    small = finalize(p, [price_print(p, "a.pdf", "d", 1, {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 1, "page_range": ""})], None, 2000)
    assert small["total_cents"] == 300 and small["lines"][-1]["kind"] == "minimum"
    bad = finalize(p, [line], "NOPE", 2000)
    assert bad["promo_error"] and bad["promo_code_applied"] is None


def test_engine_inactive_and_ranges():
    p = default_pricing()
    with pytest.raises(ValueError):
        price_print(p, "a.pdf", "d", 3, {"paper_size": "A5", "color": "bw", "duplex": False, "copies": 1, "page_range": ""})
    p["services"][0]["active"] = False
    with pytest.raises(ValueError):
        price_extras(p, [{"service_id": p["services"][0]["id"], "quantity": 1}])
    assert parse_page_range("1-2,4", 5) == [1, 2, 4]


def test_subscription_dates():
    now = datetime(2026, 1, 31, tzinfo=timezone.utc)
    assert add_months(now, 1).day == 28 and add_months(now, 12).year == 2027
    assert effective_status({"status": "trialing", "trial_ends_at": now + timedelta(days=1)}, 7, now) == "trialing"
    assert effective_status({"status": "trialing", "trial_ends_at": now - timedelta(days=1)}, 7, now) == "expired"
    assert effective_status({"status": "active", "current_period_end": now - timedelta(days=2)}, 7, now) == "past_due"
    assert effective_status({"status": "active", "current_period_end": now - timedelta(days=9)}, 7, now) == "expired"


# ---------- API ----------
def test_owner_manages_catalog_and_customer_quote(client):
    owner = login("proprio@copylyon.fr", "Lyon2026!")
    shop = lyon_shop(owner)
    pricing = shop["pricing"]
    before = dict(pricing)
    pricing["services"].append({"name": "Carte de visite", "category": "custom", "unit": "unit", "price_cents": 150, "active": True})
    pricing["discounts"] = [{"name": "Rentrée", "code": "rentree", "kind": "percent", "value": 10, "min_order_cents": 0, "active": True}]
    pricing["min_order_cents"] = 100
    r = owner.put(f"/shops/{shop['id']}/pricing", json=pricing)
    assert r.status_code == 200, r.text
    saved = r.json()["pricing"]
    card = next(s for s in saved["services"] if s["name"] == "Carte de visite")
    assert card["id"] and saved["discounts"][0]["code"] == "RENTREE"
    # public view never leaks promo codes
    pub = client.get(f"/public/shops/{SLUG_LYON}").json()["pricing"]
    assert pub["has_promo_codes"] is True and "discounts" not in pub and "RENTREE" not in str(pub)
    doc = upload(client, SLUG_LYON)
    body = {"items": [{"document_id": doc["id"], "upload_token": doc["upload_token"],
                       "options": {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 1, "page_range": ""}}],
            "extras": [{"service_id": card["id"], "quantity": 2}], "promo_code": "rentree"}
    q = client.post(f"/public/shops/{SLUG_LYON}/quote", json=body).json()
    assert q["total_cents"] == round((30 + 300) * 0.9) and q["promo_code_applied"] == "RENTREE"
    assert q["total_ht_cents"] + q["vat_cents"] == q["total_cents"] and q["vat_rate_bp"] == 2000
    # browser-supplied price fields are ignored
    o = client.post(f"/public/shops/{SLUG_LYON}/orders", json={**body, "total_cents": 1, "customer_name": "Prix Test",
                                                              "customer_phone": "0600000000"}).json()
    assert o["total_cents"] == q["total_cents"] and o["vat_cents"] == q["vat_cents"]
    # invalid promo code refuses the order
    doc2 = upload(client, SLUG_LYON)
    body2 = {**body, "items": [{**body["items"][0], "document_id": doc2["id"], "upload_token": doc2["upload_token"]}], "promo_code": "FAUX"}
    assert client.post(f"/public/shops/{SLUG_LYON}/orders", json={**body2, "customer_name": "X Y", "customer_phone": "0600000000"}).status_code == 422
    # export CSV
    csv = owner.get(f"/shops/{shop['id']}/pricing/export")
    assert csv.status_code == 200 and "Prix TTC" in csv.text and "Carte de visite" in csv.text
    owner.put(f"/shops/{shop['id']}/pricing", json=before)
    owner.close()


def test_pricing_tenant_isolation():
    bastille = login("proprio@bastille.fr", "Bastille2026!")
    lyon = login("proprio@copylyon.fr", "Lyon2026!")
    lshop = lyon_shop(lyon)
    bshop = bastille.get("/auth/me").json()["shops"][0]
    assert bastille.put(f"/shops/{lshop['id']}/pricing", json=lshop["pricing"]).status_code == 404
    assert bastille.get(f"/shops/{lshop['id']}/pricing/export").status_code == 404
    assert bastille.post(f"/shops/{bshop['id']}/pricing/copy-from/{lshop['id']}").status_code == 404
    op = login("employe@bastille.fr", "Employe2026!")
    assert op.put(f"/shops/{bshop['id']}/pricing", json=bshop["pricing"]).status_code == 403
    assert op.get("/billing").status_code == 403  # billing is owner-only
    for c in (bastille, lyon, op):
        c.close()


def test_billing_overview_and_no_simulated_payment():
    owner = login("proprio@copylyon.fr", "Lyon2026!")
    ov = owner.get("/billing").json()
    codes = {p["code"]: p for p in ov["plans"]}
    assert codes["starter"]["prices_ht"]["monthly"] == 1900 and codes["pro"]["prices_ht"]["monthly"] == 3900
    assert codes["business"]["prices_ttc"]["monthly"] == 7900 + 1580
    if not ov["payment_configured"]:
        r = owner.post("/billing/checkout", json={"plan_code": "starter", "period": "monthly"})
        assert r.status_code == 503
        assert all(i["status"] != "paid" for i in owner.get("/billing").json()["invoices"])
    owner.close()


def _sync_db():
    import os
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def test_webhook_cannot_mark_paid(client):
    # forged webhook with a random id: nothing changes, 200 returned, no paid invoice appears
    db = _sync_db()
    before = db.invoices.count_documents({"status": "paid"})
    assert client.post("/billing/mollie/webhook", data={"id": "tr_forged123"}).status_code == 200
    assert db.invoices.count_documents({"status": "paid"}) == before


def test_admin_plans_settings_subscription():
    admin = login("printdrop35@gmail.com", "Admin2026!")
    owner = login("proprio@copylyon.fr", "Lyon2026!")
    plans = admin.get("/admin/plans").json()
    starter = next(p for p in plans if p["code"] == "starter")
    body = {k: starter[k] for k in ("name", "description", "prices_ht", "features", "max_shops", "max_staff", "active", "sort")}
    r = admin.put("/admin/plans/starter", json={**body, "prices_ht": {"monthly": 2100, "yearly": None}})
    assert r.status_code == 200 and r.json()["prices_ht"]["yearly"] is None
    assert owner.put("/admin/plans/starter", json=body).status_code == 403
    admin.put("/admin/plans/starter", json=body)
    s = admin.get("/admin/settings").json()
    assert s["shop_vat_rate_bp"] == 2000 and s["payment_provider"] == "Mollie"
    org_id = owner.get("/auth/me").json()["org"]["id"]
    sub = admin.patch(f"/admin/organizations/{org_id}/subscription", json={"status": "canceled"}).json()
    assert sub["status"] == "canceled"
    c = httpx.Client(base_url=API.rstrip("/"))
    assert c.get(f"/public/shops/{SLUG_LYON}").json()["accepting_orders"] is False
    end = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    sub = admin.patch(f"/admin/organizations/{org_id}/subscription", json={"status": "active", "plan_code": "pro", "period_end": end}).json()
    assert sub["status"] == "active" and sub["granted_by_admin"] is True
    assert c.get(f"/public/shops/{SLUG_LYON}").json()["accepting_orders"] is True
    for x in (admin, owner, c):
        x.close()


def test_register_starts_trial_and_plan_limit():
    c = httpx.Client(base_url=API.rstrip("/"))
    email = f"trial-{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/auth/register", json={"org_name": "Essai SARL", "shop_name": "Essai Shop", "city": "Nantes",
                                       "owner_name": "Eva Essai", "email": email, "password": "Essai2026!"})
    sub = r.json()["org"]["subscription"]
    assert sub["status"] == "trialing" and sub["days_left"] >= 13
    admin = login("printdrop35@gmail.com", "Admin2026!")
    admin.patch(f"/admin/organizations/{r.json()['org']['id']}/subscription", json={"plan_code": "starter"})
    assert c.post("/shops", json={"name": "Deuxième", "city": "Nantes"}).status_code == 402
    c.close()
    admin.close()


def test_migrations_idempotent():
    import subprocess
    out = subprocess.run(["python", "-m", "migrations.runner"], cwd="/app/backend", capture_output=True, text=True, timeout=60)
    assert "none (up to date)" in out.stdout
    assert {m["id"] for m in _sync_db().migrations.find()} >= {"001_pricing_v2", "002_subscriptions"}
