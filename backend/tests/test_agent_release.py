"""Agent release settings: super-admin installer link/version, shop download + update notices."""

import httpx

from tests.test_stage1 import API_URL, login


def super_session():
    return login("printdrop35@gmail.com", "Admin2026!")


def test_release_validation_permissions_and_update_flag():
    admin = super_session()
    before = admin.get("/admin/agent-release").json()
    try:
        # validation: https only, direct .exe link, x.y.z version
        assert admin.put("/admin/agent-release", json={"url": "http://x.com/a.exe", "version": "1.0.0"}).status_code == 422
        assert admin.put("/admin/agent-release", json={"url": "https://x.com/page", "version": "1.0.0"}).status_code == 422
        assert admin.put("/admin/agent-release", json={"url": "", "version": "latest"}).status_code == 422
        url = "https://github.com/demo/printdrop/releases/latest/download/PrintDrop-Setup.exe"
        r = admin.put("/admin/agent-release", json={"url": url, "version": "9.9.0", "notes": "Correctifs"})
        assert r.status_code == 200 and r.json()["url"] == url

        owner = login("proprio@bastille.fr", "Bastille2026!")
        # shop owners cannot change the platform release
        assert owner.put("/admin/agent-release", json={"url": url, "version": "9.9.1"}).status_code in (401, 403)
        anon = httpx.Client(base_url=API_URL, timeout=30.0)
        assert anon.get("/agent-download").status_code == 401

        dl = owner.get("/agent-download").json()
        assert dl == {"available": True, "url": url, "version": "9.9.0", "notes": "Correctifs", "sha256": "", "size_bytes": 0}

        shop = next(s for s in owner.get("/auth/me").json()["shops"] if s["slug"] == "cybercafe-bastille")
        code = owner.post(f"/shops/{shop['id']}/agents/pairing-code").json()["code"]
        paired = httpx.post(f"{API_URL}/agent/pair", json={"code": code, "name": "PC release", "hostname": "pytest", "version": "0.2.0"}).json()
        agents = owner.get(f"/shops/{shop['id']}/agents").json()
        mine = next(a for a in agents if a["id"] == paired["agent_id"])
        assert mine["update_available"] is True and mine["latest_version"] == "9.9.0"
        owner.post(f"/agents/{paired['agent_id']}/revoke")
        revoked = next(a for a in owner.get(f"/shops/{shop['id']}/agents").json() if a["id"] == paired["agent_id"])
        assert revoked["update_available"] is False  # revoked agents never nag
    finally:
        admin.put("/admin/agent-release", json={"url": before.get("external_url", ""), "version": "0.2.0" if before.get("filename", "").startswith("PrintDrop-Setup") and not before.get("external_url") else before["version"], "notes": before["notes"]})


def test_version_compare():
    from lib.agent_release import is_outdated
    assert is_outdated("0.2.0", "0.10.0") and not is_outdated("0.10.0", "0.2.0")
    assert not is_outdated("", "1.0.0") and not is_outdated("?", "1.0.0") and not is_outdated("1.0.0", "1.0.0")


# --- release-mutating tests kept in ONE module (xdist loadscope => same worker, no race on the global release) ---
from tests.test_auto_copy import commands, fresh_owner, pair_agent, setup  # noqa: E402


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
    after = owner.get("/agent-download").json()
    from lib.agent_release import bundled_installer
    b = bundled_installer()
    if b and not before.get("external_url"):  # falls back to the installer shipped with the app
        assert after["available"] and after["version"] == b["version"] and after["sha256"] == b["sha256"]
        assert owner.get("/agent-download/file").status_code == 200
    else:
        assert after["available"] is bool(before.get("external_url"))


def test_one_click_agent_update(client):
    import httpx
    from tests.conftest import API_URL as BASE_URL
    from tests.test_stage1 import login
    admin = login("printdrop35@gmail.com", "Admin2026!")
    owner, _ = fresh_owner()
    info, agent, shop, printer = setup(owner, "PC maj")  # heartbeat reports v0.4.0
    try:
        # nothing newer than the agent => refused (the shipped installer may already be served)
        from lib.agent_release import bundled_installer
        b = bundled_installer()
        if b:
            agent.post("/agent/heartbeat", json={"version": b["version"], "printers": [], "scanners": []})
        assert owner.post(f"/agents/{info['agent_id']}/update").status_code == 409
        agent.post("/agent/heartbeat", json={"version": "0.4.0", "printers": [], "scanners": []})
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


def test_update_all_pcs_of_all_shops(client):
    from tests.test_stage1 import login
    admin = login("printdrop35@gmail.com", "Admin2026!")
    owner, _ = fresh_owner()
    info1, agent1, shop, printer = setup(owner, "PC A")
    info2, agent2 = pair_agent(owner, "PC hors ligne")
    from tests.conftest import API_URL
    try:
        exe = b"MZ" + b"\0" * 100 + b"NullsoftInst" + b"\0" * (1024 * 1024)
        assert admin.post("/admin/agent-release/upload", files={"file": ("PrintDrop-Setup-0.9.0.exe", exe)}).status_code == 200
        agent2.post("/agent/heartbeat", json={"version": "0.3.0", "printers": [], "scanners": []})
        r = owner.post("/agents/update-all")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["version"] == "0.9.0"
        assert [s["agent_id"] for s in out["started"]] == [info1["agent_id"]]
        sk = {s["agent_id"]: s["reason"] for s in out["skipped"]}
        assert "trop ancienne" in sk[info2["agent_id"]]
        assert commands(agent1, "self_update")
        again = owner.post("/agents/update-all").json()  # no duplicate update
        assert again["started"] == [] and "déjà en cours" in {s["agent_id"]: s["reason"] for s in again["skipped"]}[info1["agent_id"]]
        import httpx
        assert httpx.post(f"{API_URL}/agents/update-all").status_code == 401
    finally:
        admin.delete("/admin/agent-release/file")
        owner.post(f"/agents/{info1['agent_id']}/revoke")
        owner.post(f"/agents/{info2['agent_id']}/revoke")


import hashlib  # noqa: E402
from tests.test_stage1 import login  # noqa: E402


def _ts_super_session():
    return login("printdrop35@gmail.com", "Admin2026!")


def _ts_owner_session():
    return login("proprio@bastille.fr", "Bastille2026!")


def _ts_make_installer(version: str, size: int = 1024 * 1024 + 500) -> bytes:
    body = b"Inno Setup Windows Installer payload " + b"\x00" * size
    return b"MZ" + body[: size - 2]


def test_installer_lifecycle_publish_download_remove():
    admin = _ts_super_session()
    before = admin.get("/admin/agent-release").json()

    try:
        # --- Invalid files are refused (criterion 3) ---
        not_mz = b"PK" + b"\x00" * (1024 * 1024 + 10)
        r = admin.post("/admin/agent-release/upload?version=0.4.0", files={"file": ("PrintDrop-Setup-0.4.0.exe", not_mz, "application/octet-stream")})
        assert r.status_code == 422 and "detail" in r.json()

        mz_no_marker = b"MZ" + b"\x00" * (1024 * 1024 + 10)
        r = admin.post("/admin/agent-release/upload?version=0.4.0", files={"file": ("PrintDrop-Setup-0.4.0.exe", mz_no_marker, "application/octet-stream")})
        assert r.status_code == 422

        too_small = b"MZ" + b"Inno Setup" + b"\x00" * 10
        r = admin.post("/admin/agent-release/upload?version=0.4.0", files={"file": ("PrintDrop-Setup-0.4.0.exe", too_small, "application/octet-stream")})
        assert r.status_code == 422

        after_bad = admin.get("/admin/agent-release").json()
        assert after_bad["version"] == before["version"] and after_bad["filename"] == before.get("filename", "")

        # --- Before publishing: owner should see unavailable ---
        owner = _ts_owner_session()
        pre = owner.get("/agent-download").json()
        if not before.get("filename") and not before.get("external_url"):
            assert pre["available"] is False  # (with a shipped installer, before["filename"] is set)

        # --- Super-admin publishes the installer (criterion 2) ---
        data = _ts_make_installer("0.4.0")
        r = admin.post(
            "/admin/agent-release/upload?version=0.4.0",
            files={"file": ("PrintDrop-Setup-0.4.0.exe", data, "application/octet-stream")},
        )
        assert r.status_code == 200, r.text
        published = r.json()
        assert published["version"] == "0.4.0"
        assert published["url"] == "/api/agent-download/file"
        assert len(published["sha256"]) == 64
        assert published["sha256"] == hashlib.sha256(data).hexdigest()
        assert published["filename"] == "PrintDrop-Setup-0.4.0.exe"

        # --- Shop cannot publish (criterion 6) ---
        r = owner.post(
            "/admin/agent-release/upload?version=9.9.9",
            files={"file": ("PrintDrop-Setup-9.9.9.exe", _ts_make_installer("9.9.9"), "application/octet-stream")},
        )
        assert r.status_code in (401, 403)
        r = owner.delete("/admin/agent-release/file")
        assert r.status_code in (401, 403)
        # publication unaffected by the rejected owner calls
        assert admin.get("/admin/agent-release").json()["version"] == "0.4.0"

        # --- Shop downloads the installer (criterion 4) ---
        dl = owner.get("/agent-download").json()
        assert dl["available"] is True
        assert dl["version"] == "0.4.0"
        assert dl["url"] == "/api/agent-download/file"
        assert dl["sha256"] == hashlib.sha256(data).hexdigest()

        f = owner.get("/agent-download/file")
        assert f.status_code == 200
        assert f.content == data
        assert "PrintDrop-Setup-0.4.0.exe" in f.headers.get("content-disposition", "")

        anon = httpx.Client(base_url=API_URL, timeout=30.0)
        assert anon.get("/agent-download/file").status_code == 401
        assert anon.get("/agent-download").status_code == 401

        # --- Removing the hosted installer (criterion 5) ---
        r = admin.delete("/admin/agent-release/file")
        assert r.status_code == 200
        removed = r.json()
        from lib.agent_release import bundled_installer
        bundled = bundled_installer()
        dl_after = owner.get("/agent-download").json()
        if bundled and not before.get("external_url"):
            # falls back to the real installer shipped with the app (backend/agent_dist), never to the removed upload
            assert removed["filename"] == bundled["filename"] and dl_after["sha256"] == bundled["sha256"]
            assert owner.get("/agent-download/file").status_code == 200
        else:
            assert removed["filename"] == ""
            assert owner.get("/agent-download/file").status_code == 404
            if not before.get("external_url"):
                assert dl_after["available"] is False
    finally:
        # restore original release state
        admin.delete("/admin/agent-release/file")
        admin.put("/admin/agent-release", json={"url": before.get("external_url", ""), "version": before.get("version", "0.2.0"), "notes": before.get("notes", "")})
