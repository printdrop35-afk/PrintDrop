"""Dashboard download endpoint must serve the real shipped 0.5.0 installer whose bytes
hash to the published sha256 and to the .sha256 sidecar shipped next to the .exe."""

import hashlib
import pathlib

from tests.test_stage1 import login

AGENT_DIST = pathlib.Path(__file__).resolve().parents[1] / "agent_dist"


def test_owner_agent_download_file_matches_shipped_installer_and_sidecar():
    owner = login("proprio@bastille.fr", "Bastille2026!")
    info = owner.get("/agent-download").json()
    assert info["available"] is True
    assert info["version"] == "0.5.0"

    installer = AGENT_DIST / "PrintDrop-Setup-0.5.0.exe"
    assert installer.exists()
    sidecar = (installer.with_name(installer.name + ".sha256")).read_text().split()[0].strip().lower()

    f = owner.get("/agent-download/file")
    assert f.status_code == 200
    digest = hashlib.sha256(f.content).hexdigest()
    assert digest == info["sha256"] == sidecar
    assert "0.5.0" in f.headers.get("content-disposition", "")


def test_anonymous_cannot_download_agent_file():
    import httpx
    from tests.conftest import API_URL

    anon = httpx.Client(base_url=API_URL, timeout=30.0)
    assert anon.get("/agent-download").status_code == 401
    assert anon.get("/agent-download/file").status_code == 401
