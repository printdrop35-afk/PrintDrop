"""Selected pages only reach the agent; documents + customer identity are erased on pickup/cancel and after 7 days."""

import io
import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

from pypdf import PdfReader

from tests.test_agent_notify import pair_agent
from tests.test_printers import fresh_owner, heartbeat
from tests.test_stage1 import find_order, place_order

load_dotenv("/app/backend/.env")


def test_agent_receives_only_selected_pages(client):
    owner, slug = fresh_owner()
    _, agent = pair_agent(owner, "PC pages")
    heartbeat(agent, [{"name": "Imprimante pages", "is_default": True, "status": "online"}])
    order = place_order(client, slug, page_range="2-3")
    o = find_order(owner, order["code"])
    r = owner.post(f"/orders/{o['id']}/print-direct", json={"dry_check": False})
    assert r.status_code == 200 and r.json()["ok"], r.text
    job = next(j for j in agent.post("/agent/jobs/claim").json()["jobs"] if j["order_code"] == order["code"])
    assert job["pages"] == [1, 2]  # renumbered: the file holds only the 2 selected pages
    f = agent.get(job["download_url"].removeprefix("/api"))
    assert f.status_code == 200 and len(PdfReader(io.BytesIO(f.content)).pages) == 2
    # another agent / wrong lease cannot fetch it
    assert agent.get(job["download_url"].removeprefix("/api").replace("lease=", "lease=x")).status_code == 404
    _, other = pair_agent(owner, "PC autre")
    assert other.get(job["download_url"].removeprefix("/api")).status_code == 404


def test_purge_on_pickup_and_after_retention(client):
    owner, slug = fresh_owner()
    order = place_order(client, slug)
    o = find_order(owner, order["code"])
    owner.post(f"/orders/{o['id']}/pay", json={"method": "cash"})
    for st in ("printing", "ready", "picked_up"):
        assert owner.post(f"/orders/{o['id']}/status", json={"status": st}).status_code == 200
    after = owner.get(f"/orders/{o['id']}").json()
    assert after["purged_at"] and after["customer_name"] == "Client anonymisé" and after["customer_phone"] == ""
    assert after["total_cents"] == o["total_cents"]  # accounting kept
    assert client.post("/public/orders/track", json={"code": order["code"], "phone": "06 12 34 56 78"}).status_code == 404

    # old pending order: erased by the hourly retention cron
    order2 = place_order(client, slug)
    o2 = find_order(owner, order2["code"])
    mongo = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    mongo.orders.update_one({"id": o2["id"]}, {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(days=8)}})
    r = client.post("/cron/retention", headers={"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}"})
    assert r.status_code == 200
    for _ in range(20):
        if owner.get(f"/orders/{o2['id']}").json()["purged_at"]:
            break
        time.sleep(0.5)
    assert owner.get(f"/orders/{o2['id']}").json()["purged_at"]


def test_retention_cron_requires_secret(client):
    assert client.post("/cron/retention").status_code == 401
    assert client.post("/cron/retention", headers={"Authorization": "Bearer wrong"}).status_code == 401
