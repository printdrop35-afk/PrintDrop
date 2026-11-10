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
        admin.put("/admin/agent-release", json={"url": before["url"], "version": before["version"], "notes": before["notes"]})


def test_version_compare():
    from lib.agent_release import is_outdated
    assert is_outdated("0.2.0", "0.10.0") and not is_outdated("0.10.0", "0.2.0")
    assert not is_outdated("", "1.0.0") and not is_outdated("?", "1.0.0") and not is_outdated("1.0.0", "1.0.0")
