"""Brief tests A–L: page selection → print-ready PDF, download ≠ print, no automatic printing, optional contact,
deletion of files at pickup (order data kept), old links dead, 4-digit pickup codes, tracking by code."""

import io
import os
import time

import httpx
from dotenv import load_dotenv
from pypdf import PdfReader, PdfWriter

from tests.conftest import API_URL
from tests.test_agent_notify import pair_agent
from tests.test_printers import fresh_owner, heartbeat
from tests.test_stage1 import find_order

load_dotenv("/app/backend/.env")


def pdf_bytes(n: int) -> bytes:
    """n-page PDF whose page k has width 100+k, so extracted pages can be identified."""
    w = PdfWriter()
    for k in range(1, n + 1):
        w.add_blank_page(width=100 + k, height=200)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def page_ids(data: bytes) -> list[int]:
    return [int(float(p.mediabox.width)) - 100 for p in PdfReader(io.BytesIO(data)).pages]


def order_with(client, slug, *, page_range="", phone="", email=None, pages=4):
    up = client.post(f"/public/shops/{slug}/documents", files={"file": ("doc.pdf", pdf_bytes(pages), "application/pdf")})
    assert up.status_code == 200, up.text
    d = up.json()
    body = {"items": [{"document_id": d["id"], "upload_token": d["upload_token"],
                       "options": {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 1, "page_range": page_range}}],
            "customer_name": "Client Brief", "customer_phone": phone, "customer_email": email}
    r = client.post(f"/public/shops/{slug}/orders", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_A_B_C_page_selection_print_ready_pdf(client):
    owner, slug = fresh_owner()
    for spec, expected in (("1-1", [1]), ("1,3", [1, 3]), ("1-4", [1, 2, 3, 4]), ("2,4", [2, 4]), ("1-2,4", [1, 2, 4]), ("3,1", [3, 1])):
        o = find_order(owner, order_with(client, slug, page_range=spec)["code"])
        line = o["lines"][0]
        assert line["document_pages"] == 4 and line["selected_pages"] == expected and line["pages"] == len(expected)
        f = owner.get(f"/orders/{o['id']}/documents/{line['document_id']}/file?variant=print")
        assert f.status_code == 200 and page_ids(f.content) == expected, spec
        assert page_ids(owner.get(f"/orders/{o['id']}/documents/{line['document_id']}/file?variant=original").content) == [1, 2, 3, 4]
    # priced on the selected pages only
    q1 = order_with(client, slug, page_range="1-1")["total_cents"]
    q4 = order_with(client, slug, page_range="")["total_cents"]
    assert q4 > q1
    # invalid selections are rejected server-side
    up = client.post(f"/public/shops/{slug}/documents", files={"file": ("d.pdf", pdf_bytes(4), "application/pdf")}).json()
    for bad in ("5", "0-2", "3-1", "a", "1-9"):
        r = client.post(f"/public/shops/{slug}/quote", json={"items": [{"document_id": up["id"], "upload_token": up["upload_token"],
                        "options": {"paper_size": "A4", "color": "bw", "duplex": False, "copies": 1, "page_range": bad}}]})
        assert r.status_code == 422, (bad, r.text)


def test_D_F_no_automatic_printing_and_agent_gets_only_pages(client):
    owner, slug = fresh_owner()
    data, agent = pair_agent(owner, "PC brief")
    heartbeat(agent, [{"name": "Imprimante PC brief", "is_default": True, "status": "online"}])
    o = find_order(owner, order_with(client, slug, page_range="1-1")["code"])
    doc = o["lines"][0]["document_id"]
    # upload + order + download + status change: still no print job
    assert owner.get(f"/orders/{o['id']}/documents/{doc}/file?variant=print").status_code == 200
    assert owner.post(f"/orders/{o['id']}/status", json={"status": "printing"}).status_code == 200
    assert owner.get(f"/orders/{o['id']}/print-jobs").json() == []
    assert agent.post("/agent/jobs/claim").json()["jobs"] == []
    # explicit print → the agent receives a file with page 1 only
    owner.post(f"/orders/{o['id']}/status", json={"status": "pending"})
    assert owner.post(f"/orders/{o['id']}/print-direct", json={"dry_check": False}).json()["ok"]
    assert owner.post(f"/orders/{o['id']}/print-direct", json={"dry_check": False}).status_code == 409  # no duplicate
    job = agent.post("/agent/jobs/claim").json()["jobs"][0]
    assert page_ids(agent.get(job["download_url"].removeprefix("/api")).content) == [1]
    owner.post(f"/agents/{data['agent_id']}/revoke")


def test_G_optional_contact_four_cases(client):
    owner, slug = fresh_owner()
    for phone, email in (("06 11 22 33 44", None), ("", "client@example.com"), ("0611223344", "c2@example.com"), ("", None)):
        order = order_with(client, slug, phone=phone, email=email, pages=1)
        assert order["code"].isdigit() and len(order["code"]) == 4
        o = find_order(owner, order["code"])
        assert o["customer_phone"] == phone.strip() and o["customer_email"] == email
    assert client.post(f"/public/shops/{slug}/orders", json={"items": [], "customer_name": "X Y", "customer_phone": "12"}).status_code == 422


def test_H_I_J_L_deletion_at_pickup_keeps_order(client):
    owner, slug = fresh_owner()
    order = order_with(client, slug, phone="0612345678", email="keep@example.com", page_range="2")
    o = find_order(owner, order["code"])
    doc = o["lines"][0]["document_id"]
    link = owner.post(f"/orders/{o['id']}/documents/{doc}/link").json()["url"]
    # J: still available while pending / printing / ready
    for st in ("printing", "ready"):
        owner.post(f"/orders/{o['id']}/status", json={"status": st})
        assert owner.get(f"/orders/{o['id']}/documents/{doc}/file").status_code == 200
    owner.post(f"/orders/{o['id']}/pay", json={"method": "cash"})
    assert owner.post(f"/orders/{o['id']}/status", json={"status": "picked_up", "confirm_code": order["code"]}).status_code == 200
    after = owner.get(f"/orders/{o['id']}").json()
    # I: order, contact, payment, history kept
    assert after["purged_at"] and after["customer_phone"] == "0612345678" and after["customer_email"] == "keep@example.com"
    assert after["payment_status"] == "paid_counter" and [h["status"] for h in after["history"]][-1] == "picked_up"
    # H/L: files gone, old links dead
    assert owner.get(link.removeprefix("/api")).status_code == 410
    assert owner.get(f"/orders/{o['id']}/documents/{doc}/file?variant=print").status_code == 410
    # tracking still works, documents flagged deleted
    t = client.post("/public/orders/track", json={"code": order["code"], "phone": "0612345678"}).json()
    assert t["status"] == "picked_up" and t["documents_deleted"] is True


def test_K_pickup_code_tracking_and_validation(client):
    owner, slug = fresh_owner()
    no_phone = order_with(client, slug, pages=1)
    with_phone = order_with(client, slug, phone="0699887766", pages=1)
    assert client.post("/public/orders/track", json={"code": no_phone["code"]}).status_code == 200  # code alone
    assert client.post("/public/orders/track", json={"code": with_phone["code"]}).status_code == 404  # phone required
    assert client.post("/public/orders/track", json={"code": with_phone["code"], "phone": "06 99 88 77 66"}).status_code == 200
    o = find_order(owner, with_phone["code"])
    owner.post(f"/orders/{o['id']}/pay", json={"method": "cash"})
    owner.post(f"/orders/{o['id']}/status", json={"status": "ready"})
    assert owner.post(f"/orders/{o['id']}/status", json={"status": "picked_up", "confirm_code": no_phone["code"]}).status_code == 409


def test_retention_cron_retries_and_requires_secret(client):
    assert client.post("/cron/retention").status_code == 401
    r = client.post("/cron/retention", headers={"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}"})
    assert r.status_code == 200
    time.sleep(0.5)
    assert httpx.get(f"{API_URL}/files/x?exp=9999999999&sig=abc").status_code == 403
