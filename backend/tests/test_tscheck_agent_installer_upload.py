"""Windows installer publishing: super-admin uploads/removes the hosted .exe on printdrop.fr,
shops see the download appear/disappear, and non-admins/anonymous users are rejected."""

import hashlib

import httpx

from tests.test_stage1 import login

API_URL = "http://localhost:8001/api"


def super_session():
    return login("printdrop35@gmail.com", "Admin2026!")


def owner_session():
    return login("proprio@bastille.fr", "Bastille2026!")


def make_installer(version: str, size: int = 1024 * 1024 + 500) -> bytes:
    body = b"Inno Setup Windows Installer payload " + b"\x00" * size
    return b"MZ" + body[: size - 2]


def test_installer_lifecycle_publish_download_remove():
    admin = super_session()
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
        owner = owner_session()
        pre = owner.get("/agent-download").json()
        if not before.get("filename") and not before.get("external_url"):
            assert pre["available"] is False  # (with a shipped installer, before["filename"] is set)

        # --- Super-admin publishes the installer (criterion 2) ---
        data = make_installer("0.4.0")
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
            files={"file": ("PrintDrop-Setup-9.9.9.exe", make_installer("9.9.9"), "application/octet-stream")},
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
