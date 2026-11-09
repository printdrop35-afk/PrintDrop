"""Alerts, daily report and cron endpoint tests."""

import os

import httpx
from dotenv import load_dotenv

from tests.conftest import API_URL
from tests.test_agent_notify import start_print, drain, pair_agent
from tests.test_stage1 import find_order, login, place_order, shop_id

load_dotenv("/app/backend/.env")


def test_daily_report_counts(client):
    owner = login("proprio@bastille.fr", "Bastille2026!")
    sid = shop_id(owner)
    before = owner.get(f"/shops/{sid}/reports/daily").json()
    order = place_order(client)  # 3 pages x 2 copies, A4 N&B = 0,90 €
    o = find_order(owner, order["code"])
    owner.post(f"/orders/{o['id']}/pay", json={"method": "card_terminal"})
    after = owner.get(f"/shops/{sid}/reports/daily").json()
    assert after["orders_total"] >= before["orders_total"] + 1  # other workers may add orders concurrently
    assert after["pages_bw"] >= before["pages_bw"] + 6
    assert after["revenue_card_cents"] >= before["revenue_card_cents"] + 60
    assert len(after["hours"]) == 24 and after["busiest_hour"] is not None
    assert owner.get(f"/shops/{sid}/reports/daily?day=2999-01-01").status_code == 422
    owner.close()


def test_report_permissions_and_isolation():
    op = login("employe@bastille.fr", "Employe2026!")
    owner_b = login("proprio@copylyon.fr", "Lyon2026!")
    owner_a = login("proprio@bastille.fr", "Bastille2026!")
    assert op.get(f"/shops/{shop_id(op)}/reports/daily").status_code == 403
    assert owner_b.get(f"/shops/{shop_id(owner_a)}/reports/daily").status_code == 404
    assert owner_b.get(f"/shops/{shop_id(owner_a)}/alerts").status_code == 404
    for c in (op, owner_a, owner_b):
        c.close()


def test_alerts_printer_offline_and_failed_job(client):
    owner = login("proprio@copylyon.fr", "Lyon2026!")
    data, agent = pair_agent(owner, "PC alertes")
    drain(agent)
    order = place_order(client, "copyprint-bellecour")
    o = find_order(owner, order["code"])
    start_print(owner, o["id"], data["agent_id"])
    job = next(j for j in agent.post("/agent/jobs/claim").json()["jobs"] if j["order_code"] == order["code"])
    agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "failed", "error": "Bourrage"})
    agent.post("/agent/heartbeat", json={"printers": [{"name": "Imprimante PC alertes", "status": "offline", "detail": "Hors ligne"}]})
    kinds = {a["kind"]: a for a in owner.get(f"/shops/{shop_id(owner)}/alerts").json()}
    assert "printer_offline" in kinds and "job_failed" in kinds
    assert any(a["order_code"] == order["code"] for a in owner.get(f"/shops/{shop_id(owner)}/alerts").json())
    # a reprint clears the failed-job alert
    owner.post(f"/print-jobs/{job['id']}/reprint", json={"reason": "Après bourrage"})
    assert all(a.get("order_code") != order["code"] for a in owner.get(f"/shops/{shop_id(owner)}/alerts").json())
    agent.post("/agent/heartbeat", json={"printers": [{"name": "Imprimante PC alertes", "status": "online"}]})
    drain(agent)
    owner.post(f"/agents/{data['agent_id']}/revoke")
    owner.close()


def test_cron_requires_secret():
    assert httpx.post(f"{API_URL}/cron/daily-report").status_code == 401
    assert httpx.post(f"{API_URL}/cron/daily-report", headers={"Authorization": "Bearer wrong"}).status_code == 401
    secret = os.environ["WEBHOOK_CRON_SECRET"]
    h = {"Authorization": f"Bearer {secret}", "X-Webhook-Id": "pytest-run-" + os.urandom(4).hex()}
    r = httpx.post(f"{API_URL}/cron/daily-report", headers=h, json={"event": "schedule.triggered", "run_id": h["X-Webhook-Id"], "data": None})
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert httpx.post(f"{API_URL}/cron/daily-report", headers=h, json={}).json()["status"] == "duplicate"


def test_paper_stock_low_and_out(client):
    owner = login("proprio@copylyon.fr", "Lyon2026!")
    op = login("employe@bastille.fr", "Employe2026!")
    sid = shop_id(owner)
    # operators may record paper; tenant B cannot touch tenant A's shop
    assert op.put(f"/shops/{shop_id(op)}/paper-stock", json={"stock": {"A3": 500}}).status_code == 200
    op.put(f"/shops/{shop_id(op)}/paper-stock", json={"stock": {"A3": None}})
    assert owner.put(f"/shops/{shop_id(op)}/paper-stock", json={"stock": {"A4": 10}}).status_code == 404
    assert owner.put(f"/shops/{sid}/paper-stock", json={"stock": {"A4": 0}}).status_code == 422
    r = owner.put(f"/shops/{sid}/paper-stock", json={"stock": {"A4": 10}, "alert_pct": 50})
    assert r.status_code == 200 and r.json()["levels"][0]["used_sheets"] == 0
    place_order(client, "copyprint-bellecour")  # 3 pages x 2 copies = 6 sheets A4 -> 60 %
    lv = owner.get(f"/shops/{sid}/paper-stock").json()["levels"][0]
    assert lv["used_sheets"] == 6 and lv["level"] == "low"
    assert any(a["kind"] == "low_paper" for a in owner.get(f"/shops/{sid}/alerts").json())
    place_order(client, "copyprint-bellecour")  # 12 >= 10 -> out
    assert owner.get(f"/shops/{sid}/paper-stock").json()["levels"][0]["level"] == "out"
    # refill resets the count and clears the alert
    owner.put(f"/shops/{sid}/paper-stock", json={"stock": {"A4": 5000}, "alert_pct": 80})
    assert not any(a["kind"] == "low_paper" for a in owner.get(f"/shops/{sid}/alerts").json())
    owner.put(f"/shops/{sid}/paper-stock", json={"stock": {"A4": None}})
    owner.close()
    op.close()
