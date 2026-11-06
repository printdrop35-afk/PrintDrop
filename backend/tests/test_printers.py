"""Printers & devices: agent command channel (discovery, tests), capability checks, « IMPRIMER DIRECTEMENT »,
printer-bound claims, spooler statuses, retry, delete protection, tenant isolation."""

from tests.test_agent_notify import drain, pair_agent
import uuid

import httpx

from tests.conftest import API_URL
from tests.test_stage1 import find_order, login, place_order, shop_id


def fresh_owner() -> tuple[httpx.Client, str]:
    """Isolated business (own shop) so parallel test modules never share agents or jobs."""
    c = httpx.Client(base_url=API_URL, timeout=30)
    r = c.post("/auth/register", json={"org_name": "Repro Test", "shop_name": "Repro Test", "city": "Marseille",
                                       "owner_name": "Test Owner", "email": f"printers-{uuid.uuid4().hex[:10]}@example.com", "password": "Printers2026!"})
    assert r.status_code == 200, r.text
    return c, r.json()["shops"][0]["slug"]

CAPS_A4_BW = {"paper_sizes": ["A4", "Lettre US"], "color": False, "duplex": True, "orientations": ["portrait", "landscape"], "qualities": []}


def heartbeat(agent, printers, drivers=None):
    r = agent.post("/agent/heartbeat", json={"version": "0.2.0", "printers": printers, "drivers": drivers or []})
    assert r.status_code == 200, r.text
    return r.json()


def printer(name, caps, conn="usb", default=False):
    return {"name": name, "is_default": default, "status": "online", "detail": "", "supports_color": bool(caps.get("color")),
            "connection_type": conn, "manufacturer": "HP", "model": "LaserJet", "ip_address": "" if conn == "usb" else "192.168.1.50",
            "port_name": "USB001" if conn == "usb" else "IP_192.168.1.50", "driver_name": "HP Universal", "driver_ok": True, "capabilities": caps}


def test_command_channel_and_isolation(client):
    owner, _ = fresh_owner()
    other = login("proprio@bastille.fr", "Bastille2026!")
    info, agent = pair_agent(owner, "PC commandes")
    sid = shop_id(owner)
    heartbeat(agent, [printer("HP USB", CAPS_A4_BW, default=True)])
    cmd = owner.post(f"/shops/{sid}/printers/discover", json={"agent_id": info["agent_id"], "kind": "network"})
    assert cmd.status_code == 200 and cmd.json()["status"] == "queued"
    cid = cmd.json()["id"]
    assert other.get(f"/agent-commands/{cid}").status_code == 404  # other tenant cannot read it
    sent = heartbeat(agent, [printer("HP USB", CAPS_A4_BW, default=True)])["commands"]
    assert [c["id"] for c in sent] == [cid] and sent[0]["type"] == "discover_network"
    assert heartbeat(agent, [printer("HP USB", CAPS_A4_BW, default=True)])["commands"] == []  # delivered once
    assert agent.post(f"/agent/commands/{cid}/result", json={"ok": True, "result": {"devices": []}}).status_code == 200
    done = owner.get(f"/agent-commands/{cid}").json()
    assert done["status"] == "done" and done["result"] == {"devices": []}  # nothing invented
    pr = next(x for x in owner.get(f"/shops/{sid}/printers").json() if x["name"] == "HP USB")
    assert pr["connection_type"] == "usb" and pr["capabilities"]["color"] is False and pr["agent_name"] == "PC commandes"
    assert other.delete(f"/printers/{pr['id']}").status_code == 404
    assert other.post(f"/printers/{pr['id']}/test-page").status_code == 404
    # manual network printer: validated input, routed to the agent
    bad = owner.post(f"/shops/{sid}/printers/manual", json={"agent_id": info["agent_id"], "name": "Réseau", "host": "1.2.3.4; rm", "protocol": "ipp"})
    assert bad.status_code == 422
    ok = owner.post(f"/shops/{sid}/printers/manual", json={"agent_id": info["agent_id"], "name": "Réseau", "host": "192.168.1.60", "protocol": "raw9100", "driver_name": "HP Universal"})
    assert ok.status_code == 200 and ok.json()["type"] == "add_network_printer"
    owner.post(f"/agents/{info['agent_id']}/revoke")


def test_print_direct_checks_bound_claim_and_statuses(client):
    owner, LYON = fresh_owner()
    info, agent = pair_agent(owner, "PC direct")
    drain(agent)
    sid = shop_id(owner)
    caps_color = {**CAPS_A4_BW, "color": True, "paper_sizes": ["A4", "A3"]}
    heartbeat(agent, [printer("NB A4", CAPS_A4_BW, default=True), printer("Couleur A3", caps_color, conn="network")])
    prs = {p["name"]: p for p in owner.get(f"/shops/{sid}/printers").json()}
    order = place_order(client, LYON, color="color")
    o = find_order(owner, order["code"])
    forced = owner.post(f"/orders/{o['id']}/print-direct", json={"printer_id": prs["NB A4"]["id"], "dry_check": True}).json()
    assert not forced["ok"] and any("noir et blanc" in p for p in forced["lines"][0]["problems"])
    auto = owner.post(f"/orders/{o['id']}/print-direct", json={"dry_check": True}).json()
    assert auto["ok"] and auto["lines"][0]["printer_name"] == "Couleur A3"  # compatible printer chosen server-side
    assert owner.get(f"/orders/{o['id']}/print-jobs").json() == []  # dry check never prints
    real = owner.post(f"/orders/{o['id']}/print-direct", json={}).json()
    assert real["ok"] and real["jobs_created"] == 1
    assert owner.post(f"/orders/{o['id']}/print-direct", json={}).status_code == 409  # no duplicate
    assert find_order(owner, order["code"])["status"] == "printing"
    job = agent.post("/agent/jobs/claim").json()["jobs"][0]
    assert job["printer_name"] == "Couleur A3"
    assert agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "printing"}).status_code == 200
    assert agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "spooled"}).json()["status"] == "spooled"
    queue = owner.get(f"/shops/{sid}/print-queue").json()
    assert any(j["id"] == job["id"] and j["status"] == "spooled" for j in queue)
    # printer with an active job cannot be deleted silently
    assert owner.delete(f"/printers/{prs['Couleur A3']['id']}").status_code == 409
    assert agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "printed"}).json()["status"] == "printed"
    assert find_order(owner, order["code"])["status"] == "ready"
    owner.post(f"/agents/{info['agent_id']}/revoke")


def test_requeue_goes_to_retry_wait(client):
    owner, LYON = fresh_owner()
    info, agent = pair_agent(owner, "PC retry")
    drain(agent)
    heartbeat(agent, [printer("NB A4", CAPS_A4_BW, default=True)])
    o = find_order(owner, place_order(client, LYON)["code"])
    assert owner.post(f"/orders/{o['id']}/print-direct", json={}).json()["ok"]
    job = agent.post("/agent/jobs/claim").json()["jobs"][0]
    r = agent.post(f"/agent/jobs/{job['id']}/report", json={"lease_id": job["lease_id"], "status": "requeue", "error": "Hors ligne"})
    assert r.json()["status"] == "retry_wait"
    assert agent.post("/agent/jobs/claim").json()["jobs"] == []  # not before the retry delay
    owner.post(f"/agents/{info['agent_id']}/revoke")
