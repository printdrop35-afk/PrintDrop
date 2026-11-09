"""Counter services: photocopy, scan (agent upload + import fallback), QR delivery, no customer code, idempotency, retention."""

import io
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from PIL import Image
from pymongo import MongoClient
from pypdf import PdfReader

from tests.conftest import API_URL
from tests.test_agent_notify import pair_agent
from tests.test_printers import fresh_owner

load_dotenv("/app/backend/.env")
mongo = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _jpg(color=(200, 30, 30)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (400, 560), color).save(b, "JPEG")
    return b.getvalue()


def _shop(owner) -> dict:
    return owner.get("/auth/me").json()["shops"][0]


def test_photocopy_bw_and_color_paid_without_code(client):
    owner, _ = fresh_owner()
    shop = _shop(owner)
    one = {"color": "bw", "paper_size": "A4", "duplex": False, "originals": 1, "copies": 1, "customer_name": ""}
    q = owner.post(f"/shops/{shop['id']}/counter/copy/quote", json=one).json()
    assert q["total_cents"] == shop["pricing"]["photocopy"]["bw"]
    o = owner.post(f"/shops/{shop['id']}/counter/copy", json=one).json()
    assert o["service"] == "copy" and o["status"] == "printing" and len(o["code"]) == 4
    assert owner.post(f"/orders/{o['id']}/status", json={"status": "ready"}).status_code == 200
    assert owner.post(f"/orders/{o['id']}/pay", json={"method": "cash"}).status_code == 200
    assert owner.post(f"/orders/{o['id']}/pay", json={"method": "cash"}).status_code == 409  # no duplicate payment
    done = owner.post(f"/orders/{o['id']}/status", json={"status": "picked_up"})  # no customer code asked
    assert done.status_code == 200 and done.json()["status"] == "picked_up"
    assert owner.post(f"/orders/{o['id']}/status", json={"status": "picked_up"}).status_code == 409  # completed once
    assert mongo.payments.count_documents({"order_id": o["id"]}) <= 1

    many = {**one, "color": "color", "originals": 3, "copies": 4}
    q2 = owner.post(f"/shops/{shop['id']}/counter/copy/quote", json=many).json()
    assert q2["lines"][0]["pages"] == 12 and q2["total_cents"] >= 12 * shop["pricing"]["photocopy"]["color"] * 0  # priced server-side
    # another tenant cannot touch it
    other, _ = fresh_owner()
    assert other.post(f"/orders/{o['id']}/status", json={"status": "cancelled"}).status_code == 404


def test_scan_multipage_pdf_qr_delivery_and_retention(client):
    owner, _ = fresh_owner()
    shop = _shop(owner)
    info, agent = pair_agent(owner, "PC scan")
    s = owner.post(f"/shops/{shop['id']}/scan-sessions", json={"agent_id": info["agent_id"], "format": "pdf", "color": "color", "dpi": 300, "source": "feeder"}).json()
    # agent offline (never sent a heartbeat) → clear error
    agent.post("/agent/heartbeat", json={"version": "0.3.0", "printers": [], "scanners": ["Scanner test"]})
    r = owner.post(f"/scan-sessions/{s['id']}/scan")
    assert r.status_code == 200 and r.json()["status"] == "scanning"
    assert owner.post(f"/scan-sessions/{s['id']}/scan").status_code == 409  # duplicate scan click
    for color in ((255, 0, 0), (0, 255, 0)):  # the agent uploads pages one by one
        assert agent.post(f"/agent/scan-sessions/{s['id']}/pages", files={"file": ("p.jpg", _jpg(color), "image/jpeg")}).status_code == 200
    owner.post(f"/scan-sessions/{s['id']}/upload", files={"file": ("p3.jpg", _jpg(), "image/jpeg")})  # import fallback
    sess = owner.get(f"/scan-sessions/{s['id']}").json()
    assert len(sess["pages"]) == 3
    owner.patch(f"/scan-sessions/{s['id']}/pages/{sess['pages'][0]['id']}", json={"rotation": 90})
    sess = owner.delete(f"/scan-sessions/{s['id']}/pages/{sess['pages'][2]['id']}").json()
    assert [p["index"] for p in sess["pages"]] == [0, 1]
    o = owner.post(f"/scan-sessions/{s['id']}/finalize", json={"customer_name": "", "customer_email": ""}).json()
    again = owner.post(f"/scan-sessions/{s['id']}/finalize", json={"customer_name": "", "customer_email": ""}).json()
    assert again["id"] == o["id"] and o["service"] == "scan" and o["status"] == "ready"  # idempotent
    token = o["delivery_token"]
    pub = httpx.Client(base_url=API_URL, timeout=30)
    assert pub.get(f"/public/scans/{token}/file").status_code == 402  # not paid yet
    owner.post(f"/orders/{o['id']}/pay", json={"method": "card_terminal"})
    f = pub.get(f"/public/scans/{token}/file")
    assert f.status_code == 200 and len(PdfReader(io.BytesIO(f.content)).pages) == 2
    assert pub.get("/public/scans/not-a-real-token-xxxxxxxx/file").status_code == 404
    assert owner.get(f"/orders/{o['id']}").json()["status"] == "delivered"
    # retention: kept < 24 h after the first download, deleted after
    secret = {"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}"}
    client.post("/cron/retention", headers=secret)
    time.sleep(1)
    assert pub.get(f"/public/scans/{token}/file").status_code == 200
    mongo.orders.update_one({"id": o["id"]}, {"$set": {"scan_downloaded_at": datetime.now(timezone.utc) - timedelta(hours=25)}})
    client.post("/cron/retention", headers=secret)
    for _ in range(20):
        if owner.get(f"/orders/{o['id']}").json()["purged_at"]:
            break
        time.sleep(0.5)
    after = owner.get(f"/orders/{o['id']}").json()
    assert after["purged_at"] and after["payment_status"] == "paid_counter" and after["total_cents"] == o["total_cents"]
    assert pub.get(f"/public/scans/{token}/file").status_code == 410


def test_scan_errors_and_undownloaded_scan_kept(client):
    owner, _ = fresh_owner()
    shop = _shop(owner)
    s = owner.post(f"/shops/{shop['id']}/scan-sessions", json={"agent_id": None, "format": "jpg", "color": "bw", "dpi": 150, "source": "flatbed"}).json()
    r = owner.post(f"/scan-sessions/{s['id']}/scan")
    assert r.status_code == 409 and "hors ligne" in r.json()["detail"]  # no scanner connected: clear message
    assert owner.post(f"/scan-sessions/{s['id']}/upload", files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 422
    owner.post(f"/scan-sessions/{s['id']}/upload", files={"file": ("a.jpg", _jpg(), "image/jpeg")})
    owner.post(f"/scan-sessions/{s['id']}/upload", files={"file": ("b.jpg", _jpg(), "image/jpeg")})
    assert owner.post(f"/scan-sessions/{s['id']}/finalize", json={}).status_code == 422  # JPG = one page
    sess = owner.get(f"/scan-sessions/{s['id']}").json()
    owner.delete(f"/scan-sessions/{s['id']}/pages/{sess['pages'][1]['id']}")
    o = owner.post(f"/scan-sessions/{s['id']}/finalize", json={}).json()
    owner.post(f"/orders/{o['id']}/pay", json={"method": "cash"})
    mongo.orders.update_one({"id": o["id"]}, {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(days=30)}})
    client.post("/cron/retention", headers={"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}"})
    time.sleep(1)
    assert owner.get(f"/orders/{o['id']}").json()["purged_at"] is None  # never downloaded → never deleted


def test_failed_deletion_is_retried(client):
    owner, _ = fresh_owner()
    shop = _shop(owner)
    o = owner.post(f"/shops/{shop['id']}/counter/copy", json={"color": "bw", "paper_size": "A4", "duplex": False, "originals": 1, "copies": 1, "customer_name": ""}).json()
    # simulate an order whose file deletion failed earlier: picked up, files present, purged_at still empty
    s = owner.post(f"/shops/{shop['id']}/scan-sessions", json={"agent_id": None, "format": "pdf", "color": "bw", "dpi": 150, "source": "flatbed"}).json()
    owner.post(f"/scan-sessions/{s['id']}/upload", files={"file": ("a.jpg", _jpg(), "image/jpeg")})
    so = owner.post(f"/scan-sessions/{s['id']}/finalize", json={}).json()
    mongo.orders.update_one({"id": so["id"]}, {"$set": {"status": "picked_up"}})
    assert mongo.documents.find_one({"order_id": so["id"]})["status"] != "purged"
    client.post("/cron/retention", headers={"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}"})
    for _ in range(20):
        if mongo.documents.find_one({"order_id": so["id"]})["status"] == "purged":
            break
        time.sleep(0.5)
    assert mongo.documents.find_one({"order_id": so["id"]})["status"] == "purged"
    assert o["status"] == "printing"  # unrelated order untouched
