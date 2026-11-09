"""Stage 1 security & business tests against the live API: auth, tenant isolation, server pricing,
document token binding, order lifecycle, counter payments, signed links, super-admin scope."""

import io
import uuid

import httpx
import pytest
from pypdf import PdfWriter

from tests.conftest import API_URL

BASTILLE = "cybercafe-bastille"
LYON = "copyprint-bellecour"


def login(email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=API_URL, timeout=30.0)
    r = c.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


def pdf_bytes(pages: int) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def upload(client: httpx.Client, slug: str, pages: int = 3) -> dict:
    r = client.post(f"/public/shops/{slug}/documents", files={"file": ("cours.pdf", pdf_bytes(pages), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def place_order(client: httpx.Client, slug: str = BASTILLE, **opts) -> dict:
    doc = upload(client, slug, 3)
    options = {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 2, "page_range": "", **opts}
    r = client.post(f"/public/shops/{slug}/orders", json={
        "items": [{"document_id": doc["id"], "upload_token": doc["upload_token"], "options": options}],
        "customer_name": "Client Test", "customer_phone": "06 12 34 56 78",
    })
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def owner_a():
    c = login("proprio@bastille.fr", "Bastille2026!")
    yield c
    c.close()


@pytest.fixture
def operator_a():
    c = login("employe@bastille.fr", "Employe2026!")
    yield c
    c.close()


@pytest.fixture
def owner_b():
    c = login("proprio@copylyon.fr", "Lyon2026!")
    yield c
    c.close()


@pytest.fixture
def admin():
    c = login("printdrop35@gmail.com", "Admin2026!")
    yield c
    c.close()


def shop_id(c: httpx.Client) -> str:
    return c.get("/auth/me").json()["shops"][0]["id"]


def find_order(c: httpx.Client, code: str) -> dict:
    orders = c.get(f"/shops/{shop_id(c)}/orders").json()
    return next(o for o in orders if o["code"] == code)


# ---------- auth ----------
def test_me_requires_auth(client):
    assert client.get("/auth/me").status_code == 401


def test_wrong_password(client):
    r = client.post("/auth/login", json={"email": "nobody-" + uuid.uuid4().hex[:6] + "@x.fr", "password": "bad"})
    assert r.status_code == 401


def test_register_creates_isolated_org(client):
    email = f"test-{uuid.uuid4().hex[:8]}@exemple.fr"
    r = client.post("/auth/register", json={"org_name": "Org Test", "shop_name": "Shop Test", "city": "Nice",
                                            "owner_name": "Test Owner", "email": email, "password": "Motdepasse1"})
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["role"] == "owner" and len(me["shops"]) == 1
    assert client.post("/auth/register", json={"org_name": "Org X", "shop_name": "Shop Y", "city": "Z", "owner_name": "Dup",
                                               "email": email, "password": "Motdepasse1"}).status_code == 409


# ---------- pricing ----------
def test_server_quote_bw_and_duplex(client):
    doc = upload(client, BASTILLE, 3)
    base = {"document_id": doc["id"], "upload_token": doc["upload_token"]}
    r = client.post(f"/public/shops/{BASTILLE}/quote", json={"items": [
        {**base, "options": {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 2, "page_range": ""}}]})
    assert r.status_code == 200
    assert r.json()["total_cents"] == 3 * 2 * 10  # 60 (example price A4 N&B 0,10 €)
    r = client.post(f"/public/shops/{BASTILLE}/quote", json={"items": [
        {**base, "options": {"paper_size": "A4", "color": "color", "duplex": True, "copies": 1, "page_range": "1-2"}}],
        "services": {"scan_pages": 2}})
    body = r.json()
    assert body["total_cents"] == round(2 * 50 * 0.9) + 2 * 20  # A4 couleur 0,50 €
    assert body["lines"][0]["sheets"] == 1


def test_invalid_page_range(client):
    doc = upload(client, BASTILLE, 3)
    r = client.post(f"/public/shops/{BASTILLE}/quote", json={"items": [{"document_id": doc["id"], "upload_token": doc["upload_token"],
                    "options": {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 1, "page_range": "2-9"}}]})
    assert r.status_code == 422


def test_client_supplied_price_ignored(client):
    doc = upload(client, BASTILLE, 1)
    r = client.post(f"/public/shops/{BASTILLE}/orders", json={
        "items": [{"document_id": doc["id"], "upload_token": doc["upload_token"],
                   "options": {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 1}}],
        "customer_name": "Hack", "customer_phone": "0611111111", "total_cents": 1, "payment_status": "paid_online",
        "shop_id": "other",
    })
    assert r.status_code == 200
    assert r.json()["total_cents"] == 10 and r.json()["payment_status"] == "unpaid"


# ---------- documents ----------
def test_rejects_non_pdf(client):
    r = client.post(f"/public/shops/{BASTILLE}/documents", files={"file": ("x.pdf", b"MZ\x90\x00 evil", "application/pdf")})
    assert r.status_code == 422


def test_wrong_upload_token_or_shop(client):
    doc = upload(client, BASTILLE, 1)
    opts = {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 1}
    assert client.post(f"/public/shops/{BASTILLE}/quote", json={"items": [
        {"document_id": doc["id"], "upload_token": "forged", "options": opts}]}).status_code == 404
    # document uploaded to shop A cannot be used in shop B
    assert client.post(f"/public/shops/{LYON}/quote", json={"items": [
        {"document_id": doc["id"], "upload_token": doc["upload_token"], "options": opts}]}).status_code == 404


def test_document_cannot_be_reused(client):
    doc = upload(client, BASTILLE, 1)
    payload = {"items": [{"document_id": doc["id"], "upload_token": doc["upload_token"],
                          "options": {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 1}}],
               "customer_name": "Client", "customer_phone": "0612345678"}
    assert client.post(f"/public/shops/{BASTILLE}/orders", json=payload).status_code == 200
    assert client.post(f"/public/shops/{BASTILLE}/orders", json=payload).status_code == 404


# ---------- tracking ----------
def test_tracking_requires_matching_phone(client):
    order = place_order(client)
    assert client.post("/public/orders/track", json={"code": order["code"], "phone": "+33 6 12 34 56 78"}).status_code == 404
    r = client.post("/public/orders/track", json={"code": order["code"], "phone": "0612345678"})
    assert r.status_code == 200 and r.json()["status"] == "pending"


# ---------- tenant isolation ----------
def test_tenant_isolation_orders(client, owner_a, owner_b):
    order = place_order(client)
    order_a = find_order(owner_a, order["code"])
    oid = order_a["id"]
    assert owner_b.get(f"/orders/{oid}").status_code == 404
    assert owner_b.post(f"/orders/{oid}/status", json={"status": "printing"}).status_code == 404
    assert owner_b.post(f"/orders/{oid}/pay", json={"method": "cash"}).status_code == 404
    assert owner_b.get(f"/shops/{order_a['shop_id']}/orders").status_code == 404
    assert owner_b.put(f"/shops/{order_a['shop_id']}/pricing", json=owner_a.get("/shops").json()[0]["pricing"]).status_code == 404
    doc_id = order_a["lines"][0]["document_id"]
    assert owner_b.post(f"/orders/{oid}/documents/{doc_id}/link").status_code == 404
    assert all(o["code"] != order["code"] for o in owner_b.get(f"/shops/{shop_id(owner_b)}/orders").json())


def test_staff_isolation_and_role_limits(owner_a, owner_b, operator_a):
    staff_a = owner_a.get("/staff").json()
    member = next(m for m in staff_a if m["role"] == "operator")
    assert owner_b.patch(f"/staff/{member['membership_id']}", json={"active": False}).status_code == 404
    assert operator_a.get("/staff").status_code == 403
    assert operator_a.put(f"/shops/{shop_id(operator_a)}/pricing", json=owner_a.get("/shops").json()[0]["pricing"]).status_code == 403
    assert operator_a.get("/audit").status_code == 403


# ---------- lifecycle & payment ----------
def test_order_lifecycle_and_counter_payment(client, operator_a):
    order = place_order(client)
    o = find_order(operator_a, order["code"])
    oid = o["id"]
    assert operator_a.post(f"/orders/{oid}/status", json={"status": "printing"}).json()["status"] == "printing"
    assert operator_a.post(f"/orders/{oid}/status", json={"status": "ready"}).json()["status"] == "ready"
    assert operator_a.post(f"/orders/{oid}/status", json={"status": "picked_up"}).status_code == 409  # unpaid
    paid = operator_a.post(f"/orders/{oid}/pay", json={"method": "cash"})
    assert paid.status_code == 200 and paid.json()["payment_status"] == "paid_counter"
    assert operator_a.post(f"/orders/{oid}/pay", json={"method": "cash"}).status_code == 409  # no double payment
    # authenticated staff complete the order directly: no customer code is asked again
    assert operator_a.post(f"/orders/{oid}/status", json={"status": "picked_up"}).json()["status"] == "picked_up"
    assert operator_a.post(f"/orders/{oid}/status", json={"status": "printing"}).status_code == 409  # terminal


def test_document_download_staff_only(client, operator_a):
    order = place_order(client)
    o = find_order(operator_a, order["code"])
    doc_id = o["lines"][0]["document_id"]
    r = operator_a.get(f"/orders/{o['id']}/documents/{doc_id}/file?variant=original")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert httpx.get(f"{API_URL}/orders/{o['id']}/documents/{doc_id}/file").status_code == 401  # no session
    assert httpx.get(f"{API_URL}/files/{doc_id}?exp=9999999999&sig=abc").status_code == 403


# ---------- super-admin ----------
def test_superadmin_scope(admin, owner_a):
    assert admin.get("/admin/stats").status_code == 200
    orgs = admin.get("/admin/organizations").json()
    assert any(o["owner_email"] == "proprio@bastille.fr" for o in orgs)
    # platform admin has no tenant membership -> no tenant data
    assert admin.get("/shops").status_code == 403
    # tenant owner cannot reach platform routes
    assert owner_a.get("/admin/organizations").status_code == 403


def test_suspension_blocks_tenant_and_portal(admin, client):
    email = f"susp-{uuid.uuid4().hex[:8]}@exemple.fr"
    with httpx.Client(base_url=API_URL, timeout=30.0) as owner:
        me = owner.post("/auth/register", json={"org_name": "Org Susp", "shop_name": "Shop Susp", "city": "Lille",
                                                "owner_name": "Owner", "email": email, "password": "Motdepasse1"}).json()
        org_id, slug = me["org"]["id"], me["shops"][0]["slug"]
        assert admin.patch(f"/admin/organizations/{org_id}", json={"status": "suspended"}).status_code == 200
        assert owner.get("/shops").status_code == 403
        assert client.get(f"/public/shops/{slug}").status_code == 404
        admin.patch(f"/admin/organizations/{org_id}", json={"status": "active"})
        assert owner.get("/shops").status_code == 200
