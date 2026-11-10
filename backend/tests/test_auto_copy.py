"""Automatic photocopy (agent scans then prints), real page count pricing, staff confirmation, no charge on failure,
printer discovery/connect/verify, scan price by colour and duplex capability checks."""

from tests.test_agent_notify import pair_agent
from tests.test_printers import fresh_owner

PRINTERS: dict = {}
SCANNER = {"name": "HP MFP Scan", "flatbed": True, "feeder": True, "duplex": False}


def setup(owner, name="PC copie", printer_status="online"):
    info, agent = pair_agent(owner, name)
    pr = {"name": f"MFP {name}", "is_default": True, "status": printer_status, "detail": "" if printer_status == "online" else "Plus de papier",
          "supports_color": True, "connection_type": "usb", "manufacturer": "HP", "model": "LaserJet MFP", "driver_name": "HP LaserJet MFP",
          "driver_ok": True, "capabilities": {"paper_sizes": ["A4", "A3"], "color": True, "duplex": True}}
    agent.post("/agent/heartbeat", json={"version": "0.4.0", "printers": [pr], "scanners": [SCANNER["name"]], "scanner_caps": [SCANNER]}).raise_for_status()
    agent.headers["X-Test-Printer"] = pr["name"]
    PRINTERS[pr["name"]] = pr
    shop = owner.get("/shops").json()[0]
    printer = next(p for p in owner.get(f"/shops/{shop['id']}/printers").json() if p["name"] == pr["name"])
    return info, agent, shop, printer


def commands(agent, ctype):
    hb = agent.post("/agent/heartbeat", json={"version": "0.4.0", "printers": [PRINTERS[agent.headers["X-Test-Printer"]]], "scanners": [SCANNER["name"]], "scanner_caps": [SCANNER]}).json()
    return [c for c in hb["commands"] if c["type"] == ctype]


def start(owner, shop, printer, **kw):
    body = {"color": "bw", "paper_size": "A4", "duplex": False, "copies": 2, "customer_name": "", "printer_id": printer["id"], "source": "feeder", **kw}
    return owner.post(f"/shops/{shop['id']}/counter/copy", json=body)


def test_auto_copy_confirmed_by_printer_charges_real_pages(client):
    owner, _ = fresh_owner()
    info, agent, shop, printer = setup(owner)
    r = start(owner, shop, printer)
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["copy_job"]["state"] == "running" and o["total_cents"] == 0 and o["status"] == "printing"
    assert start(owner, shop, printer).status_code == 409  # one copy at a time on the same printer
    assert owner.post(f"/orders/{o['id']}/pay", json={"method": "cash"}).status_code == 409  # nothing to charge yet
    cmd = commands(agent, "copy")[0]
    assert cmd["payload"]["copies"] == 2 and cmd["payload"]["printer_name"] == printer["name"] and cmd["payload"]["source"] == "feeder"
    agent.post(f"/agent/commands/{cmd['id']}/result", json={"ok": True, "result": {"scanned_pages": 5, "copies_printed": 2, "spool_confirmed": True}}).raise_for_status()
    done = owner.get(f"/orders/{o['id']}").json()
    unit = shop["pricing"]["photocopy"]["bw"]
    assert done["copy_job"]["state"] == "done" and done["status"] == "ready"
    assert done["lines"][0]["pages"] == 10 and done["total_cents"] == 10 * unit  # 5 pages × 2 copies
    # duplicate agent report is ignored; payment once; completion once
    agent.post(f"/agent/commands/{cmd['id']}/result", json={"ok": True, "result": {"scanned_pages": 9, "copies_printed": 9, "spool_confirmed": True}})
    assert owner.get(f"/orders/{o['id']}").json()["total_cents"] == 10 * unit
    assert owner.post(f"/orders/{o['id']}/pay", json={"method": "card_terminal"}).status_code == 200
    assert owner.post(f"/orders/{o['id']}/pay", json={"method": "cash"}).status_code == 409
    assert owner.post(f"/orders/{o['id']}/status", json={"status": "picked_up"}).status_code == 200
    owner.post(f"/agents/{info['agent_id']}/revoke")


def test_auto_copy_partial_needs_staff_confirmation_and_failure_is_free(client):
    owner, _ = fresh_owner()
    info, agent, shop, printer = setup(owner, "PC partiel")
    o = start(owner, shop, printer, copies=3, color="color").json()
    cmd = commands(agent, "copy")[0]
    agent.post(f"/agent/commands/{cmd['id']}/result", json={"ok": True, "result": {"scanned_pages": 4, "copies_printed": None, "spool_confirmed": False,
                                                                                   "error": "Impression interrompue : Bourrage papier"}})
    o2 = owner.get(f"/orders/{o['id']}").json()
    assert o2["copy_job"]["state"] == "needs_confirmation" and "Bourrage" in o2["copy_job"]["error"] and o2["total_cents"] == 0
    assert owner.post(f"/orders/{o['id']}/pay", json={"method": "cash"}).status_code == 409
    c = owner.post(f"/orders/{o['id']}/copy/confirm", json={"originals": 4, "copies": 1})
    assert c.status_code == 200 and c.json()["total_cents"] == 4 * shop["pricing"]["photocopy"]["color"] and c.json()["status"] == "ready"
    assert owner.post(f"/orders/{o['id']}/copy/confirm", json={"originals": 4, "copies": 1}).status_code == 409
    # scan failure: nothing scanned => cancelled, nothing charged
    o3 = start(owner, shop, printer).json()
    cmd = commands(agent, "copy")[0]
    agent.post(f"/agent/commands/{cmd['id']}/result", json={"ok": False, "result": {}, "error": "Le chargeur est vide"})
    o3 = owner.get(f"/orders/{o3['id']}").json()
    assert o3["copy_job"]["state"] == "failed" and o3["status"] == "cancelled" and o3["total_cents"] == 0
    assert owner.post(f"/orders/{o3['id']}/pay", json={"method": "cash"}).status_code == 409
    owner.post(f"/agents/{info['agent_id']}/revoke")


def test_copy_refused_when_printer_offline_or_no_feeder(client):
    owner, _ = fresh_owner()
    info, agent, shop, printer = setup(owner, "PC hors ligne", printer_status="offline")
    r = start(owner, shop, printer)
    assert r.status_code == 409 and "indisponible" in r.json()["detail"]
    PRINTERS[printer["name"]] = {**PRINTERS[printer["name"]], "status": "online", "detail": ""}
    agent.post("/agent/heartbeat", json={"version": "0.4.0", "printers": [PRINTERS[printer["name"]]], "scanners": ["S"],
                                         "scanner_caps": [{"name": "S", "flatbed": True, "feeder": False, "duplex": False}]})
    r = start(owner, shop, printer)
    assert r.status_code == 422 and "chargeur" in r.json()["detail"]
    assert start(owner, shop, printer, source="flatbed").status_code == 200
    owner.post(f"/agents/{info['agent_id']}/revoke")


def test_discover_connect_verify_and_scan_pricing(client):
    owner, _ = fresh_owner()
    info, agent, shop, printer = setup(owner, "PC ajout")
    assert printer["verified_at"] is None
    d = owner.post(f"/shops/{shop['id']}/printers/discover-all", json={"agent_id": info["agent_id"]}).json()
    assert d["type"] == "discover_all" and commands(agent, "discover_all")
    owner.patch(f"/printers/{printer['id']}", json={"enabled": False})
    c = owner.post(f"/shops/{shop['id']}/printers/connect", json={"agent_id": info["agent_id"], "name": printer["name"]})
    assert c.status_code == 200 and c.json()["type"] == "test_connection"
    test = commands(agent, "test_connection")[0]
    agent.post(f"/agent/commands/{test['id']}/result", json={"ok": True, "result": {"windows_status": "online"}}).raise_for_status()
    p = next(x for x in owner.get(f"/shops/{shop['id']}/printers").json() if x["id"] == printer["id"])
    assert p["enabled"] and p["verified_at"]
    assert owner.post(f"/shops/{shop['id']}/printers/install", json={"agent_id": info["agent_id"], "kind": "network", "name": "X"}).status_code == 422
    assert owner.post(f"/shops/{shop['id']}/printers/install", json={"agent_id": info["agent_id"], "kind": "network", "name": "HP Wi-Fi", "host": "192.168.1.30"}).json()["type"] == "install_printer"
    # scan duplex refused when the scanner cannot do it
    r = owner.post(f"/shops/{shop['id']}/scan-sessions", json={"agent_id": info["agent_id"], "format": "pdf", "color": "bw", "dpi": 300, "source": "feeder", "duplex": True})
    assert r.status_code == 422
    # separate colour scan price
    pricing = owner.get(f"/shops/{shop['id']}").json()["pricing"] if owner.get(f"/shops/{shop['id']}").status_code == 200 else shop["pricing"]
    assert pricing.get("scan_color_cents") is not None or "scan_color_cents" in shop["pricing"]
    owner.post(f"/agents/{info['agent_id']}/revoke")


def test_copy_live_progress(client):
    owner, _ = fresh_owner()
    info, agent, shop, printer = setup(owner, "PC progres")
    o = start(owner, shop, printer, copies=3).json()
    cmd = commands(agent, "copy")[0]
    assert agent.post(f"/agent/commands/{cmd['id']}/progress", json={"phase": "scanning", "scanned_pages": 2}).status_code == 200
    j = owner.get(f"/orders/{o['id']}").json()["copy_job"]
    assert j["phase"] == "scanning" and j["progress_scanned"] == 2
    agent.post(f"/agent/commands/{cmd['id']}/progress", json={"phase": "printing", "scanned_pages": 4, "printed_pages": 5, "total_pages": 12}).raise_for_status()
    j = owner.get(f"/orders/{o['id']}").json()["copy_job"]
    assert (j["phase"], j["progress_scanned"], j["progress_printed_pages"], j["total_print_pages"]) == ("printing", 4, 5, 12)
    assert agent.post("/agent/commands/unknown/progress", json={"phase": "printing"}).status_code == 404
    agent.post(f"/agent/commands/{cmd['id']}/result", json={"ok": True, "result": {"scanned_pages": 4, "copies_printed": 3, "spool_confirmed": True}})
    assert agent.post(f"/agent/commands/{cmd['id']}/progress", json={"phase": "printing"}).status_code == 404  # finished
    owner.post(f"/agents/{info['agent_id']}/revoke")


def test_agent_installer_hosted_on_printdrop(client):
    import httpx
    from tests.conftest import API_URL as BASE_URL
    from tests.test_stage1 import login
    admin = login("printdrop35@gmail.com", "Admin2026!")
    before = admin.get("/admin/agent-release").json()
    fake_exe = b"MZ" + b"\0" * 100 + b"Inno Setup Setup Data (6.2.2)" + b"\0" * (1024 * 1024)
    # not an exe / not the PrintDrop installer => refused, nothing published
    assert admin.post("/admin/agent-release/upload", files={"file": ("x.exe", b"hello" * 300000)}).status_code == 422
    assert admin.post("/admin/agent-release/upload", files={"file": ("PrintDrop-Setup-0.4.0.exe", b"MZ" + b"\0" * (1024 * 1024))}).status_code == 422
    r = admin.post("/admin/agent-release/upload", files={"file": ("PrintDrop-Setup-0.4.0.exe", fake_exe)})
    assert r.status_code == 200, r.text
    rel = r.json()
    assert rel["version"] == "0.4.0" and rel["url"] == "/api/agent-download/file" and len(rel["sha256"]) == 64
    owner, _ = fresh_owner()
    dl = owner.get("/agent-download").json()
    assert dl["available"] and dl["url"] == "/api/agent-download/file" and dl["size_bytes"] == len(fake_exe)
    f = owner.get("/agent-download/file")
    assert f.status_code == 200 and f.content == fake_exe and "PrintDrop-Setup-0.4.0.exe" in f.headers["content-disposition"]
    assert httpx.get(f"{BASE_URL}/agent-download/file").status_code == 401  # signed-in shops only
    assert admin.delete("/admin/agent-release/file").status_code == 200
    assert owner.get("/agent-download").json()["available"] is (bool(before.get("external_url")))
    assert owner.get("/agent-download/file").status_code == 404


def test_one_click_agent_update(client):
    import httpx
    from tests.conftest import API_URL as BASE_URL
    from tests.test_stage1 import login
    admin = login("printdrop35@gmail.com", "Admin2026!")
    owner, _ = fresh_owner()
    info, agent, shop, printer = setup(owner, "PC maj")  # heartbeat reports v0.4.0
    try:
        # no hosted installer => refused
        assert owner.post(f"/agents/{info['agent_id']}/update").status_code == 409
        exe = b"MZ" + b"\0" * 100 + b"Inno Setup Setup Data (6.2.2)" + b"\0" * (1024 * 1024)
        rel = admin.post("/admin/agent-release/upload", files={"file": ("PrintDrop-Setup-0.4.1.exe", exe)}).json()
        assert rel["version"] == "0.4.1"
        r = owner.post(f"/agents/{info['agent_id']}/update")
        assert r.status_code == 200, r.text
        assert r.json()["type"] == "self_update"
        assert owner.post(f"/agents/{info['agent_id']}/update").status_code == 409  # already in progress
        cmd = commands(agent, "self_update")[0]
        assert cmd["payload"]["sha256"] == rel["sha256"] and cmd["payload"]["version"] == "0.4.1"
        dl = agent.get("/agent/installer")
        assert dl.status_code == 200 and dl.content == exe
        assert httpx.get(f"{BASE_URL}/agent/installer").status_code == 401
        agent.post(f"/agent/commands/{cmd['id']}/result", json={"ok": True, "result": {"installer_started": True}}).raise_for_status()
        # once the new agent reports 0.4.1 it is up to date
        agent.post("/agent/heartbeat", json={"version": "0.4.1", "printers": [], "scanners": []})
        a = next(x for x in owner.get(f"/shops/{shop['id']}/agents").json() if x["id"] == info["agent_id"])
        assert a["version"] == "0.4.1" and a["update_available"] is False
        assert owner.post(f"/agents/{info['agent_id']}/update").status_code == 409
    finally:
        admin.delete("/admin/agent-release/file")
        admin.put("/admin/agent-release", json={"url": "", "version": "0.2.0", "notes": ""})
        owner.post(f"/agents/{info['agent_id']}/revoke")
