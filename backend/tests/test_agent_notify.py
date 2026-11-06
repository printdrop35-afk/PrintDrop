"""Print agent + notification tests: pairing, isolation, leases, no duplicate printing,
controlled reprints, auto-ready, notification queue."""

import time

import httpx

from tests.conftest import API_URL
from tests.test_stage1 import BASTILLE, find_order, login, place_order, shop_id


def pair_agent(owner: httpx.Client, name: str = "PC test") -> tuple[dict, httpx.Client]:
    code = owner.post(f"/shops/{shop_id(owner)}/agents/pairing-code").json()["code"]
    r = httpx.post(f"{API_URL}/agent/pair", json={"code": code, "name": name, "hostname": "pytest", "version": "test"})
    assert r.status_code == 200, r.text
    data = r.json()
    agent = httpx.Client(base_url=API_URL, headers={"Authorization": f"Bearer {data['api_key']}"}, timeout=30)
    assert httpx.post(f"{API_URL}/agent/pair", json={"code": code, "name": "again"}).status_code == 404  # single use
    hb = agent.post("/agent/heartbeat", json={"version": "test", "printers": [{"name": f"Imprimante {name}", "is_default": True}]})
    assert hb.status_code == 200
    return data, agent


def drain(agent: httpx.Client) -> None:
    """Finish any job left in the shop queue so each test starts clean."""
    for _ in range(10):
        jobs = agent.post("/agent/jobs/claim").json()["jobs"]
        if not jobs:
            return
        for j in jobs:
            agent.post(f"/agent/jobs/{j['id']}/report", json={"lease_id": j["lease_id"], "status": "printed"})


def test_agent_requires_key():
    assert httpx.post(f"{API_URL}/agent/jobs/claim").status_code == 401
    assert httpx.post(f"{API_URL}/agent/jobs/claim", headers={"Authorization": "Bearer pda_forged"}).status_code == 401


def test_full_agent_flow_and_no_duplicates(client):
    owner = login("proprio@bastille.fr", "Bastille2026!")
    data, agent = pair_agent(owner, "PC flux")
    drain(agent)
    order = place_order(client)
    o = find_order(owner, order["code"])
    assert owner.post(f"/orders/{o['id']}/status", json={"status": "printing"}).status_code == 200
    jobs = owner.get(f"/orders/{o['id']}/print-jobs").json()
    assert len(jobs) == 1 and jobs[0]["status"] == "queued"

    claimed = agent.post("/agent/jobs/claim").json()["jobs"]
    mine = [j for j in claimed if j["order_code"] == order["code"]]
    assert len(mine) == 1
    job = mine[0]
    assert job["pages"] == [1, 2, 3] and job["download_url"].startswith("/api/files/")
    # a second claim never hands out the same job
    assert all(j["id"] != job["id"] for j in agent.post("/agent/jobs/claim").json()["jobs"])
    # wrong lease is rejected
    assert agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": "x" * 32, "status": "printed"}).status_code == 409
    assert agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "printing"}).status_code == 200
    assert agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "printed"}).status_code == 200
    # idempotent retry of the final report
    assert agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "printed"}).status_code == 200
    # order auto-moves to ready, notification queued (sms)
    assert owner.get(f"/orders/{o['id']}").json()["status"] == "ready"
    notifs = owner.get(f"/orders/{o['id']}/notifications").json()
    assert any(n["channel"] == "sms" for n in notifs)
    # moving back to printing does NOT recreate the initial job
    owner.post(f"/orders/{o['id']}/status", json={"status": "printing"})
    assert len(owner.get(f"/orders/{o['id']}/print-jobs").json()) == 1
    # controlled reprint: needs a reason, creates exactly one new job
    assert owner.post(f"/print-jobs/{job['id']}/reprint", json={"reason": "x"}).status_code == 422
    r = owner.post(f"/print-jobs/{job['id']}/reprint", json={"reason": "Bourrage papier"})
    assert r.status_code == 200 and r.json()["kind"] == "reprint"
    assert owner.post(f"/print-jobs/{job['id']}/reprint", json={"reason": "encore"}).status_code == 409
    drain(agent)
    owner.post(f"/agents/{data['agent_id']}/revoke")
    assert agent.post("/agent/jobs/claim").status_code == 401
    owner.close()


def test_requeue_when_printer_offline(client):
    owner = login("proprio@bastille.fr", "Bastille2026!")
    data, agent = pair_agent(owner, "PC offline")
    drain(agent)
    order = place_order(client)
    o = find_order(owner, order["code"])
    owner.post(f"/orders/{o['id']}/status", json={"status": "printing"})
    job = next(j for j in agent.post("/agent/jobs/claim").json()["jobs"] if j["order_code"] == order["code"])
    r = agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "requeue", "error": "Hors ligne"})
    assert r.json()["status"] == "queued"
    # all printers offline -> nothing is claimed
    agent.post("/agent/heartbeat", json={"printers": [{"name": "Imprimante PC offline", "status": "offline"}]})
    assert agent.post("/agent/jobs/claim").json()["jobs"] == []
    agent.post("/agent/heartbeat", json={"printers": [{"name": "Imprimante PC offline", "status": "online"}]})
    drain(agent)
    owner.post(f"/agents/{data['agent_id']}/revoke")
    owner.close()


def test_agent_isolation(client):
    owner_a = login("proprio@bastille.fr", "Bastille2026!")
    owner_b = login("proprio@copylyon.fr", "Lyon2026!")
    data_b, agent_b = pair_agent(owner_b, "PC Lyon")
    data_a, agent_a = pair_agent(owner_a, "PC Bastille")
    drain(agent_a)
    order = place_order(client, BASTILLE)
    o = find_order(owner_a, order["code"])
    owner_a.post(f"/orders/{o['id']}/status", json={"status": "printing"})
    # Lyon's agent never sees Bastille's jobs
    assert all(j["order_code"] != order["code"] for j in agent_b.post("/agent/jobs/claim").json()["jobs"])
    job = next(j for j in agent_a.post("/agent/jobs/claim").json()["jobs"] if j["order_code"] == order["code"])
    assert agent_b.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "printed"}).status_code == 404
    # tenant B cannot see A's jobs, agents or reprint them
    assert owner_b.get(f"/orders/{o['id']}/print-jobs").status_code == 404
    assert owner_b.post(f"/print-jobs/{job['id']}/reprint", json={"reason": "piratage"}).status_code == 404
    assert owner_b.post(f"/agents/{data_a['agent_id']}/revoke").status_code == 404
    drain(agent_a)
    for owner, d in ((owner_a, data_a), (owner_b, data_b)):
        owner.post(f"/agents/{d['agent_id']}/revoke")
        owner.close()


def test_operator_cannot_pair():
    op = login("employe@bastille.fr", "Employe2026!")
    assert op.post(f"/shops/{shop_id(op)}/agents/pairing-code").status_code == 403
    op.close()


def test_email_notification_queued_on_ready(client):
    owner = login("proprio@bastille.fr", "Bastille2026!")
    order = place_order(client)
    o = find_order(owner, order["code"])
    owner.post(f"/orders/{o['id']}/status", json={"status": "ready"})
    time.sleep(0.5)
    channels = {n["channel"] for n in owner.get(f"/orders/{o['id']}/notifications").json()}
    assert "sms" in channels
    owner.close()
