"""Windows installer publishing: the real shipped .exe in backend/agent_dist is a genuine
Windows (NSIS) installer bundling the agent script, SumatraPDF, an embedded Python runtime
with pywin32/Pillow/requests/certifi, and its sha256 matches the published .sha256 sidecar."""

import hashlib
import pathlib
import subprocess

AGENT_DIST = pathlib.Path(__file__).resolve().parents[1] / "agent_dist"
INSTALLER = AGENT_DIST / "PrintDrop-Setup-0.4.0.exe"
SHA_FILE = AGENT_DIST / "PrintDrop-Setup-0.4.0.exe.sha256"


def test_shipped_installer_is_a_real_windows_nsis_exe():
    assert INSTALLER.exists(), f"{INSTALLER} missing"
    size = INSTALLER.stat().st_size
    assert 10 * 1024 * 1024 < size < 60 * 1024 * 1024, f"unexpected size {size}"

    data = INSTALLER.read_bytes()
    assert data[:2] == b"MZ"  # PE header magic

    file_out = subprocess.run(["file", str(INSTALLER)], capture_output=True, text=True, check=True).stdout
    assert "PE32" in file_out and ("Nullsoft Installer" in file_out or "NSIS" in file_out), file_out


def test_shipped_installer_sha256_matches_sidecar_file():
    assert SHA_FILE.exists(), f"{SHA_FILE} missing"
    digest = hashlib.sha256(INSTALLER.read_bytes()).hexdigest()
    sidecar = SHA_FILE.read_text().split()[0].strip().lower()
    assert digest == sidecar, f"{digest} != {sidecar}"


def test_shipped_installer_archive_contains_agent_and_runtime():
    listing = subprocess.run(["7z", "l", str(INSTALLER)], capture_output=True, text=True, check=True).stdout
    required = [
        "printdrop_agent.py",
        "SumatraPDF.exe",
        "python/python.exe",
        "python/pythonw.exe",
        "python/_tkinter.pyd",
        "python/Lib/site-packages/win32/win32print.pyd",
        "python/Lib/site-packages/pywin32_system32/pywintypes312.dll",
        "python/Lib/site-packages/PIL/Image.py",
        "python/Lib/site-packages/requests/__init__.py",
        "python/Lib/site-packages/certifi/__init__.py",
    ]
    missing = [entry for entry in required if entry not in listing]
    assert not missing, f"missing from archive: {missing}"
