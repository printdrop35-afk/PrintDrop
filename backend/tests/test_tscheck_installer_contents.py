"""Windows installer publishing: the real shipped .exe in backend/agent_dist is a genuine
Windows (NSIS) installer bundling the agent script, SumatraPDF, an embedded Python runtime
with pywin32/Pillow/requests/certifi, and its sha256 matches the published .sha256 sidecar."""

import hashlib
import pathlib
import subprocess

AGENT_DIST = pathlib.Path(__file__).resolve().parents[1] / "agent_dist"
INSTALLER = sorted(AGENT_DIST.glob("PrintDrop-Setup-*.exe"))[-1]
SHA_FILE = INSTALLER.with_name(INSTALLER.name + ".sha256")


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
        "printdrop_gui.py",
        "printdrop-logo.png",
        "SumatraPDF.exe",
        "python/pythonw.exe",
        "python/_tkinter.pyd",
        "python/Lib/site-packages/PIL/ImageTk.py",
        "python/Lib/site-packages/win32/win32print.pyd",
        "python/Lib/site-packages/pywin32_system32/pywintypes312.dll",
    ]
    missing = [entry for entry in required if entry not in listing]
    assert not missing, f"missing from archive: {missing}"


def test_shipped_installer_is_version_0_5_1():
    agent_py = (pathlib.Path(__file__).resolve().parents[2] / "agent" / "printdrop_agent.py").read_text()
    assert 'VERSION = "0.5.1"' in agent_py
    assert INSTALLER.name == "PrintDrop-Setup-0.5.1.exe"
    assert not list(AGENT_DIST.glob("PrintDrop-Setup-0.4*.exe")), "stale 0.4.0 installer should not be shipped"


def test_shipped_installer_pth_fix_and_agent_sys_path_insert():
    """Root-cause fix for the 0.5.0 'double-click does nothing': python312._pth must add
    the script folder ('..' relative to python/) to sys.path, and printdrop_agent.py must
    also defensively insert its own directory, so `import printdrop_gui` succeeds under the
    embeddable interpreter."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["7z", "x", f"-o{tmp}", str(INSTALLER)], capture_output=True, text=True, check=True)
        pth = pathlib.Path(tmp) / "python" / "python312._pth"
        assert pth.exists(), "python/python312._pth missing from extracted archive"
        lines = [l.strip() for l in pth.read_text().splitlines()]
        assert ".." in lines, f"python312._pth does not add the script folder via '..': {lines}"

        agent_py = (pathlib.Path(tmp) / "printdrop_agent.py").read_text()
        assert 'VERSION = "0.5.1"' in agent_py
        assert "sys.path.insert" in agent_py and "sys.path" in agent_py

        gui_py = pathlib.Path(tmp) / "printdrop_gui.py"
        logo = pathlib.Path(tmp) / "printdrop-logo.png"
        assert gui_py.exists() and logo.exists()


def test_shipped_installer_version_info_has_printdrop_company_name():
    pefile = __import__("pefile")
    pe = pefile.PE(str(INSTALLER))
    props = {}
    for fi in pe.FileInfo:
        for entry in fi:
            if entry.Key == b"StringFileInfo":
                for st in entry.StringTable:
                    for k, v in st.entries.items():
                        props[k.decode()] = v.decode()
    assert props.get("CompanyName") == "PrintDrop", props
    assert props.get("FileVersion", "").startswith("0.5.1"), props
