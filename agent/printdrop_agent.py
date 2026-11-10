#!/usr/bin/env python3
"""PrintDrop Agent pour Windows (v0.2) — relie le PC du comptoir à une boutique PrintDrop.

Lancement :
  PrintDrop.exe                         fenêtre : appairage + état (aucun terminal nécessaire)
  PrintDrop.exe --background            démarrage automatique avec Windows (sans fenêtre)
  python printdrop_agent.py pair --server URL --code CODE   |   run [--dry-run] [--once]   |   printers

Sécurité / confidentialité :
- clé d'appareil chiffrée par DPAPI (Windows) ; jamais de contenu de document dans les journaux ;
- documents téléchargés dans un dossier temporaire privé (%LOCALAPPDATA%\\PrintDrop\\tmp), supprimés après
  envoi au spouleur et nettoyés au démarrage (jamais dans Téléchargements ni sur le Bureau) ;
- un travail n'est jamais imprimé deux fois : journal local écrit AVANT l'appel au spouleur + bail serveur.
"""

import argparse
import base64
import hashlib
import concurrent.futures
import ipaddress
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests

VERSION = "0.4.0"
IS_WINDOWS = sys.platform == "win32"
DEFAULT_SERVER = os.environ.get("PRINTDROP_SERVER", "https://print-drop-6.emergent.host")
DATA_DIR = Path(os.environ.get("PRINTDROP_AGENT_DIR") or (
    Path(os.environ.get("LOCALAPPDATA", "C:/ProgramData")) / "PrintDrop" if IS_WINDOWS else Path.home() / ".printdrop-agent"))
CONFIG_FILE, JOURNAL_FILE, LOG_FILE = DATA_DIR / "config.json", DATA_DIR / "journal.json", DATA_DIR / "agent.log"
TMP_DIR = DATA_DIR / "tmp"
PAPER = {"A4": "A4", "A3": "A3", "A5": "A5", "Letter": "letter", "Legal": "legal"}
MAGIC = {"pdf": b"%PDF-", "png": b"\x89PNG", "jpg": b"\xff\xd8\xff"}
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
log = logging.getLogger("printdrop")


class PrintError(Exception):
    pass


# ---------------------------------------------------------------- local secrets & files
def protect(secret: str) -> str:
    if IS_WINDOWS:
        try:
            import win32crypt
            return "dpapi:" + base64.b64encode(win32crypt.CryptProtectData(secret.encode(), "PrintDrop", None, None, None, 0)).decode()
        except ImportError:
            pass
    return "plain:" + secret


def unprotect(stored: str) -> str:
    kind, _, value = stored.partition(":")
    if kind == "dpapi":
        import win32crypt
        return win32crypt.CryptUnprotectData(base64.b64decode(value), None, None, None, 0)[1].decode()
    return value


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def clean_tmp() -> int:
    """Removes abandoned PrintDrop temp files (crash, power loss)."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in TMP_DIR.glob("pd_*"):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n


def tcp_open(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def powershell(script: str, timeout: int = 60) -> str:
    res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
    if res.returncode != 0:
        raise PrintError(res.stderr.strip()[:300] or "Commande Windows refusée")
    return res.stdout


# ---------------------------------------------------------------- printer backends
class WindowsBackend:
    """Imprimantes et pilotes installés dans Windows ; impression PDF/images via SumatraPDF."""

    BAD_STATUS = {0x2: "Erreur", 0x8: "Bourrage papier", 0x10: "Plus de papier", 0x80: "Hors ligne",
                  0x400: "Intervention requise", 0x1000: "Indisponible", 0x400000: "Capot ouvert", 0x40000: "Toner vide"}
    VIRTUAL = ("microsoft print to pdf", "microsoft xps", "onenote", "fax", "pdf24", "adobe pdf")

    def __init__(self, sumatra: str | None):
        import win32print  # noqa: F401 — échoue tôt si pywin32 manque
        self.sumatra = sumatra or self._find_sumatra()
        self._ports: dict[str, str] = {}
        self._ports_at = 0.0

    @staticmethod
    def _find_sumatra() -> str:
        here = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        for c in (os.environ.get("SUMATRA_PATH", ""), str(here / "SumatraPDF.exe"), str(Path(sys.executable).parent / "SumatraPDF.exe"),
                  r"C:\Program Files\SumatraPDF\SumatraPDF.exe", shutil.which("SumatraPDF") or ""):
            if c and Path(c).exists():
                return c
        raise SystemExit("SumatraPDF introuvable — réinstallez PrintDrop (il est inclus dans l'installateur)")

    def _port_hosts(self) -> dict[str, str]:
        if time.time() - self._ports_at > 60:
            try:
                rows = json.loads(powershell("Get-PrinterPort | Select-Object Name,PrinterHostAddress | ConvertTo-Json") or "[]")
                rows = rows if isinstance(rows, list) else [rows]
                self._ports = {r["Name"]: r.get("PrinterHostAddress") or "" for r in rows}
            except Exception:
                self._ports = {}
            self._ports_at = time.time()
        return self._ports

    def drivers(self) -> list[str]:
        try:
            rows = json.loads(powershell("Get-PrinterDriver | Select-Object Name | ConvertTo-Json") or "[]")
            return [r["Name"] for r in (rows if isinstance(rows, list) else [rows])]
        except Exception:
            return []

    def printers(self) -> list[dict]:
        import win32print
        default = win32print.GetDefaultPrinter()
        return [self._describe(p, default) for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS, None, 2)]

    def _describe(self, p: dict, default: str) -> dict:
        import win32print
        name, status, attrs, port = p["pPrinterName"], p["Status"], p["Attributes"], p["pPortName"] or ""
        problems = [label for flag, label in self.BAD_STATUS.items() if status & flag]
        if attrs & 0x400:
            problems.append("Utiliser l'imprimante hors connexion")
        caps = {"paper_sizes": [], "color": None, "duplex": None, "orientations": ["portrait", "landscape"], "qualities": []}
        try:
            caps["color"] = bool(win32print.DeviceCapabilities(name, port, 32))       # DC_COLORDEVICE
            caps["duplex"] = bool(win32print.DeviceCapabilities(name, port, 7))       # DC_DUPLEX
            caps["paper_sizes"] = [s.strip() for s in win32print.DeviceCapabilities(name, port, 16) if s.strip()][:60]  # DC_PAPERNAMES
        except Exception:
            pass
        up = port.upper()
        host = self._port_hosts().get(port, "")
        if any(v in name.lower() for v in self.VIRTUAL) or up in ("PORTPROMPT:", "FILE:", "NUL:"):
            conn = "virtual"
        elif up.startswith(("USB", "DOT4")):
            conn = "usb"
        elif host or up.startswith(("IP_", "WSD", "HTTP", "TCP")) or p.get("pServerName"):
            conn = "network"  # Windows ne sait pas si l'imprimante est en Wi-Fi ou Ethernet : le propriétaire le précise
        else:
            conn = "unknown"
        driver = p.get("pDriverName") or ""
        state = "online" if not problems else ("offline" if status & 0x1080 or attrs & 0x400 else "error")
        maker = driver.split()[0] if driver and not driver.lower().startswith(("microsoft", "generic")) else ""
        return {"name": name, "is_default": name == default, "status": state, "detail": ", ".join(problems),
                "supports_color": bool(caps["color"]) if caps["color"] is not None else True, "connection_type": conn,
                "manufacturer": maker, "model": driver, "ip_address": host, "port_name": port, "driver_name": driver,
                "driver_ok": bool(driver), "capabilities": caps}

    def status_of(self, name: str) -> dict | None:
        return next((p for p in self.printers() if p["name"] == name), None)

    def discover_network(self) -> list[dict]:
        """Balayage TCP du réseau local (/24) : 9100 (RAW), 631 (IPP), 515 (LPD). Ne renvoie que ce qui répond."""
        local = socket.gethostbyname(socket.gethostname())
        if local.startswith("127."):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("10.255.255.255", 1))
                local = s.getsockname()[0]
        net = ipaddress.ip_network(f"{local}/24", strict=False)
        known = {p["ip_address"] for p in self.printers() if p["ip_address"]}

        def probe(ip: str):
            ports = [port for port in (9100, 631, 515) if tcp_open(ip, port, 0.35)]
            if not ports:
                return None
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except OSError:
                hostname = ""
            return {"ip_address": ip, "hostname": hostname, "protocols": [{9100: "raw9100", 631: "ipp", 515: "lpd"}[x] for x in ports],
                    "already_installed": ip in known, "manufacturer": "", "model": ""}
        with concurrent.futures.ThreadPoolExecutor(64) as ex:
            found = [r for r in ex.map(probe, [str(h) for h in net.hosts() if str(h) != local]) if r]
        return found

    def add_network_printer(self, pl: dict) -> dict:
        host, port, name = pl["host"], int(pl["port"]), pl["name"]
        if not tcp_open(host, port, 2):
            raise PrintError(f"{host}:{port} injoignable depuis ce PC — vérifiez l'adresse et que l'imprimante est sur le même réseau")
        q = lambda v: "'" + str(v).replace("'", "''") + "'"  # noqa: E731
        if pl["protocol"] == "ipp":
            url = f"http://{host}:{port}/{pl.get('queue') or 'ipp/print'}"
            powershell(f"Add-Printer -Name {q(name)} -IppURL {q(url)}", timeout=120)
        else:
            driver = pl.get("driver_name") or ""
            if not driver:
                raise PrintError("Choisissez un pilote installé pour une imprimante RAW/LPD")
            pname = f"PD_{host}_{port}"
            if pl["protocol"] == "raw9100":
                powershell(f"if (-not (Get-PrinterPort -Name {q(pname)} -ErrorAction SilentlyContinue)) {{ Add-PrinterPort -Name {q(pname)} -PrinterHostAddress {q(host)} -PortNumber {port} }}")
            else:
                powershell(f"if (-not (Get-PrinterPort -Name {q(pname)} -ErrorAction SilentlyContinue)) {{ Add-PrinterPort -Name {q(pname)} -LprHostAddress {q(host)} -LprQueueName {q(pl.get('queue') or 'lp')} }}")
            powershell(f"Add-Printer -Name {q(name)} -DriverName {q(driver)} -PortName {q(pname)}", timeout=120)
        self._ports_at = 0
        return {"installed": name, "connection_type": pl.get("connection_type", "network")}

    def test_connection(self, pl: dict) -> dict:
        p = self.status_of(pl["printer_name"])
        if not p:
            raise PrintError("Imprimante absente de Windows")
        out = {"windows_status": p["status"], "detail": p["detail"], "driver": p["driver_name"]}
        if p["ip_address"]:
            out["network"] = {str(port): tcp_open(p["ip_address"], port, 1.5) for port in (9100, 631, 515)}
            if not any(out["network"].values()):
                raise PrintError(f"Windows connaît l'imprimante mais {p['ip_address']} ne répond pas")
        if p["status"] != "online":
            raise PrintError(f"Windows signale : {p['detail'] or p['status']}")
        return out

    def test_page(self, pl: dict) -> dict:
        # page de test native du pilote Windows (aucun document client)
        subprocess.run(["rundll32", "printui.dll,PrintUIEntry", "/k", "/n", pl["printer_name"]], timeout=60, creationflags=NO_WINDOW, check=False)
        return {"submitted": True, "note": "Page de test transmise au spouleur Windows — vérifiez la sortie papier"}

    def print_file(self, path: Path, job: dict, on_spooled, on_progress=None) -> None:
        o = job["options"]
        settings = [compress_pages(job["pages"]), "duplexlong" if o["duplex"] else "simplex",
                    "color" if o["color"] == "color" else "monochrome", f"{o['copies']}x", f"paper={PAPER[o['paper_size']]}"]
        cmd = [self.sumatra, "-print-to", job["printer_name"], "-print-settings", ",".join(settings), "-silent", "-exit-on-print", str(path)]
        log.info("Impression %s sur « %s » (%s)", job["order_code"], job["printer_name"], ",".join(settings))
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=300, creationflags=NO_WINDOW)
        except subprocess.TimeoutExpired as exc:
            raise PrintError("Délai dépassé lors de l'envoi au spouleur") from exc
        if res.returncode != 0:
            raise PrintError(f"SumatraPDF code {res.returncode}")
        on_spooled()
        self._wait_spool(job["printer_name"], path.name, on_progress=on_progress)

    @staticmethod
    def _wait_spool(printer: str, doc_name: str, timeout: int = 600, on_progress=None) -> None:
        """Attend que le travail quitte la file Windows. Fin = « terminé selon le pilote », pas une preuve papier."""
        import win32print
        h = win32print.OpenPrinter(printer)
        try:
            end = time.time() + timeout
            while time.time() < end:
                mine = [j for j in win32print.EnumJobs(h, 0, 50, 1) if doc_name in (j.get("pDocument") or "")]
                if not mine:
                    return
                if any(j["Status"] & 0x2 or j["Status"] & 0x100 for j in mine):  # JOB_STATUS_ERROR / DELETED
                    raise PrintError("Le spouleur signale une erreur sur ce travail")
                if on_progress:  # pages printed so far, as counted by the Windows spooler / driver
                    on_progress(sum(int(j.get("PagesPrinted") or 0) for j in mine))
                time.sleep(2)
            raise PrintError("Travail toujours en file après 10 min — vérifiez l'imprimante")
        finally:
            win32print.ClosePrinter(h)


class DryRunBackend:
    """SIMULATION UNIQUEMENT — n'imprime jamais. Ne détecte rien de réel."""

    NAME = "PrintDrop-Simulation (aucune impression)"

    def drivers(self) -> list[str]:
        return []

    def printers(self) -> list[dict]:
        return [{"name": self.NAME, "is_default": True, "status": "online", "detail": "Mode simulation", "supports_color": True,
                 "connection_type": "virtual", "manufacturer": "", "model": "Simulation", "ip_address": "", "port_name": "SIMULATION",
                 "driver_name": "", "driver_ok": None,
                 "capabilities": {"paper_sizes": ["A4", "A3", "A5", "Letter", "Legal"], "color": True, "duplex": True,
                                  "orientations": ["portrait", "landscape"], "qualities": []}}]

    def status_of(self, name: str) -> dict | None:
        return self.printers()[0] if name == self.NAME else None

    def discover_network(self) -> list[dict]:
        return []  # jamais d'imprimante inventée

    def add_network_printer(self, pl: dict) -> dict:
        raise PrintError("Mode simulation : aucune imprimante réseau ne peut être installée")

    def test_connection(self, pl: dict) -> dict:
        return {"windows_status": "online", "detail": "Simulation"}

    def test_page(self, pl: dict) -> dict:
        return {"submitted": False, "note": "Mode simulation : aucune page imprimée"}

    def print_file(self, path: Path, job: dict, on_spooled, on_progress=None) -> None:
        log.info("[SIMULATION] %s : %s page(s), aucune impression", job["order_code"], len(job["pages"]))
        on_spooled()


def compress_pages(pages: list[int]) -> str:
    parts, start, prev = [], None, None
    for p in pages:
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            parts.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = p
    if start is not None:
        parts.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(parts)


# ---------------------------------------------------------------- server API

# ---------- scanning (Windows Image Acquisition: any scanner recognised by Windows) ----------
WIA_JPEG = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
WIA_PAPER_EMPTY = (-2145320957, 0x80210003)  # feeder empty = normal end of a multi-page feed


def list_scanners() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        import win32com.client
        dm = win32com.client.Dispatch("WIA.DeviceManager")
        return [dm.DeviceInfos.Item(i).Properties("Name").Value for i in range(1, dm.DeviceInfos.Count + 1)
                if dm.DeviceInfos.Item(i).Type == 1]  # 1 = scanner
    except Exception as exc:  # WIA absent or no scanner: reported as an empty list, never as a fake device
        log.debug("WIA indisponible : %s", exc)
        return []


def list_scanner_caps() -> list[dict]:
    """WIA_DPS_DOCUMENT_HANDLING_CAPABILITIES (3086): FEED=1, FLAT=2, DUP=4 — only what the driver declares."""
    if sys.platform != "win32":
        return []
    out = []
    try:
        import win32com.client
        dm = win32com.client.Dispatch("WIA.DeviceManager")
        for i in range(1, dm.DeviceInfos.Count + 1):
            info = dm.DeviceInfos.Item(i)
            if info.Type != 1:
                continue
            caps = 2
            try:
                dev = info.Connect()
                for j in range(1, dev.Properties.Count + 1):
                    if dev.Properties.Item(j).PropertyID == 3086:
                        caps = int(dev.Properties.Item(j).Value)
            except Exception:
                pass
            out.append({"name": info.Properties("Name").Value, "flatbed": bool(caps & 2) or not caps & 1, "feeder": bool(caps & 1), "duplex": bool(caps & 4)})
    except Exception as exc:
        log.debug("WIA indisponible : %s", exc)
    return out


def _set_prop(props, pid: int, value) -> None:
    for i in range(1, props.Count + 1):
        if props.Item(i).PropertyID == pid:
            props.Item(i).Value = value
            return


def wia_scan(color: str, dpi: int, source: str, out_dir: Path, duplex: bool = False, on_page=None) -> list[Path]:
    """Scans one page (flatbed) or every page of the feeder. Returns JPEG files. Raises with a French message."""
    if sys.platform != "win32":
        raise RuntimeError("Le scan direct nécessite Windows (WIA)")
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    dm = win32com.client.Dispatch("WIA.DeviceManager")
    infos = [dm.DeviceInfos.Item(i) for i in range(1, dm.DeviceInfos.Count + 1) if dm.DeviceInfos.Item(i).Type == 1]
    if not infos:
        raise RuntimeError("Aucun scanner détecté par Windows — vérifiez le câble USB / le réseau et le pilote WIA du fabricant")
    device = infos[0].Connect()
    if source == "feeder":
        _set_prop(device.Properties, 3088, 5 if duplex else 1)  # WIA_DPS_DOCUMENT_HANDLING_SELECT = FEEDER (| DUPLEX)
    item = device.Items(1)
    _set_prop(item.Properties, 6146, 1 if color == "color" else 2)  # current intent: colour / greyscale
    _set_prop(item.Properties, 6147, dpi)  # horizontal resolution
    _set_prop(item.Properties, 6148, dpi)  # vertical resolution
    files: list[Path] = []
    while True:
        try:
            img = item.Transfer(WIA_JPEG)
        except Exception as exc:
            code = getattr(exc, "hresult", None) or (exc.args[0] if exc.args else None)
            if files and code in WIA_PAPER_EMPTY:
                break  # feeder empty after at least one page
            if code in WIA_PAPER_EMPTY:
                raise RuntimeError("Le chargeur est vide — placez le document puis relancez le scan") from exc
            raise RuntimeError(f"Erreur du scanner : {exc}") from exc
        path = out_dir / f"scan-{len(files) + 1:03d}.jpg"
        path.unlink(missing_ok=True)
        img.SaveFile(str(path))
        files.append(path)
        if on_page:
            on_page(len(files))
        if source != "feeder":
            break
    return files

def ipp_make_model(host: str, path: str = "ipp/print", timeout: float = 2.0) -> str:
    """IPP Get-Printer-Attributes → printer-make-and-model (what the printer itself reports, never guessed)."""
    def attr(tag: int, name: bytes, value: bytes) -> bytes:
        return bytes([tag]) + len(name).to_bytes(2, "big") + name + len(value).to_bytes(2, "big") + value
    body = (b"\x02\x00\x00\x0b\x00\x00\x00\x01\x01" + attr(0x47, b"attributes-charset", b"utf-8")
            + attr(0x48, b"attributes-natural-language", b"fr") + attr(0x45, b"printer-uri", f"ipp://{host}/{path}".encode())
            + attr(0x44, b"requested-attributes", b"printer-make-and-model") + b"\x03")
    try:
        r = requests.post(f"http://{host}:631/{path}", data=body, headers={"Content-Type": "application/ipp"}, timeout=timeout)
        data, key = r.content, b"printer-make-and-model"
        i = data.find(key)
        if i < 0:
            return ""
        i += len(key)
        n = int.from_bytes(data[i:i + 2], "big")
        return data[i + 2:i + 2 + n].decode("utf-8", "ignore").strip()
    except Exception:
        return ""


def usb_devices_without_driver() -> list[dict]:
    """USB devices Windows sees but has no working driver for (Device Manager error)."""
    if sys.platform != "win32":
        return []
    try:
        rows = json.loads(powershell("Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 -and "
                                     "($_.PNPDeviceID -like 'USB*' -or $_.PNPDeviceID -like 'USBPRINT*') } | "
                                     "Select-Object Name,PNPDeviceID,Manufacturer,ConfigManagerErrorCode | ConvertTo-Json") or "[]")
        rows = rows if isinstance(rows, list) else [rows]
        return [{"name": r.get("Name") or "Appareil USB inconnu", "device_id": r.get("PNPDeviceID") or "", "manufacturer": r.get("Manufacturer") or "",
                 "error_code": r.get("ConfigManagerErrorCode")} for r in rows]
    except Exception:
        return []


def powershell_admin(script: str, timeout: int = 180) -> None:
    """Runs a script elevated: Windows shows its administrator approval prompt to the employee."""
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    powershell(f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList '-NoProfile','-EncodedCommand','{enc}'", timeout=timeout)


def images_to_pdf(images: list[Path], dest: Path, color: str, dpi: int) -> None:
    from PIL import Image
    pages = [Image.open(p).convert("L" if color == "bw" else "RGB") for p in images]
    pages[0].save(dest, "PDF", save_all=True, append_images=pages[1:], resolution=float(dpi))


class Api:
    def __init__(self, server: str, key: str):
        self.server = server.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {key}", "User-Agent": f"PrintDrop-Agent/{VERSION}"})

    def post(self, path: str, body: dict | None = None) -> requests.Response:
        return self.s.post(f"{self.server}/api{path}", json=body or {}, timeout=30)

    def report(self, job_id: str, lease_id: str, status: str, error: str = "") -> requests.Response:
        return self.post(f"/agent/jobs/{job_id}/report", {"lease_id": lease_id, "status": status, "error": error[:300]})

    def download(self, url: str, dest: Path) -> None:
        with self.s.get(f"{self.server}{url}", timeout=120, stream=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)


# ---------------------------------------------------------------- agent loop
class Agent:
    def __init__(self, api: Api, backend):
        self.api, self.backend = api, backend
        self.current_cmd = ""
        self.journal: dict = load_json(JOURNAL_FILE, {})
        self.status = "Démarrage…"
        self.stop = threading.Event()

    def _journal(self, job: dict, state: str, reported: bool = False, error: str = "") -> None:
        self.journal[job["id"]] = {"state": state, "lease_id": job["lease_id"], "order": job["order_code"],
                                   "reported": reported, "error": error, "at": time.time()}
        save_json(JOURNAL_FILE, self.journal)

    def recover(self) -> None:
        n = clean_tmp()
        if n:
            log.info("%s fichier(s) temporaire(s) abandonné(s) supprimé(s)", n)
        for e in self.journal.values():
            if e["state"] in ("printing", "spooled"):
                e.update(state="failed", reported=False, error="Agent arrêté pendant l'impression — vérifiez avant de réimprimer")
        save_json(JOURNAL_FILE, self.journal)

    def flush_reports(self) -> None:
        for jid, e in list(self.journal.items()):
            if e["reported"] or e["state"] not in ("printed", "failed"):
                continue
            r = self.api.report(jid, e["lease_id"], e["state"], e.get("error", ""))
            if r.status_code in (200, 404, 409):
                e["reported"] = True
                save_json(JOURNAL_FILE, self.journal)
        cutoff = time.time() - 7 * 86400
        self.journal = {k: v for k, v in self.journal.items() if not v["reported"] or v["at"] > cutoff}
        save_json(JOURNAL_FILE, self.journal)

    def heartbeat(self) -> int:
        r = self.api.post("/agent/heartbeat", {"version": VERSION, "printers": self.backend.printers(), "drivers": self.backend.drivers()[:300],
                                               "scanners": list_scanners()[:20], "scanner_caps": list_scanner_caps()[:20]})
        if r.status_code == 401:
            raise SystemExit("Clé refusée : poste révoqué. Ré-associez-le depuis le tableau de bord.")
        r.raise_for_status()
        data = r.json()
        for cmd in data.get("commands", []):
            self.run_command(cmd)
        return int(data.get("poll_seconds", 5))

    def run_command(self, cmd: dict) -> None:
        handlers = {"discover_usb": lambda pl: {"printers": [p for p in self.backend.printers() if p["connection_type"] == "usb"],
                                                "all_installed": [p["name"] for p in self.backend.printers()]},
                    "discover_network": lambda pl: {"devices": self.backend.discover_network(),
                                                    "installed": [p for p in self.backend.printers() if p["connection_type"] == "network"]},
                    "add_network_printer": self.backend.add_network_printer, "test_connection": self.backend.test_connection,
                    "test_page": self.backend.test_page, "scan": self.scan, "discover_all": self.discover_all,
                    "install_printer": self.install_printer, "copy": self.copy, "self_update": self.self_update}
        log.info("Commande reçue : %s", cmd["type"])
        self.current_cmd = cmd["id"]
        try:
            body = {"ok": True, "result": handlers[cmd["type"]](cmd["payload"]), "error": ""}
        except Exception as exc:  # résultat honnête renvoyé au tableau de bord
            body = {"ok": False, "result": {}, "error": str(exc)[:500]}
        self.api.post(f"/agent/commands/{cmd['id']}/result", body)

    def scan(self, pl: dict) -> dict:
        """Scans, then uploads every page immediately (pages already sent are kept even if a later one fails)."""
        work = Path(tempfile.mkdtemp(prefix="scan-", dir=str(TMP_DIR)))
        sent = 0
        try:
            if isinstance(self.backend, DryRunBackend):
                raise RuntimeError("MODE SIMULATION : aucun scanner n'est piloté")
            for f in wia_scan(pl.get("color", "color"), int(pl.get("dpi", 300)), pl.get("source", "flatbed"), work, bool(pl.get("duplex"))):
                with f.open("rb") as fh:
                    r = self.api.s.post(f"{self.api.server}/api/agent/scan-sessions/{pl['session_id']}/pages",
                                        files={"file": (f.name, fh, "image/jpeg")}, timeout=120)
                r.raise_for_status()
                sent += 1
            return {"pages": sent}
        finally:
            shutil.rmtree(work, ignore_errors=True)  # no scanned image stays on the PC

    def discover_all(self, pl: dict) -> dict:
        """Everything « Ajouter une imprimante » can offer: installed queues, network printers, USB devices lacking a driver."""
        installed = self.backend.printers()
        network = []
        if not isinstance(self.backend, DryRunBackend):
            for d in self.backend.discover_network():
                if "ipp" in d["protocols"]:
                    mm = ipp_make_model(d["ip_address"])
                    d["model"] = mm
                    d["manufacturer"] = mm.split()[0] if mm else ""
                network.append(d)
        return {"installed": installed, "network": network, "usb_missing_driver": usb_devices_without_driver(), "scanners": list_scanner_caps()}

    def install_printer(self, pl: dict) -> dict:
        if isinstance(self.backend, DryRunBackend):
            raise PrintError("Mode simulation : aucune imprimante ne peut être installée")
        q = lambda v: "'" + str(v).replace("'", "''") + "'"  # noqa: E731
        before = {p["name"] for p in self.backend.printers()}
        if pl["kind"] == "network":
            host, name = pl["host"], pl["name"]
            if not tcp_open(host, 631, 2):
                raise PrintError(f"L'imprimante {host} ne répond pas en IPP : vérifiez qu'elle est allumée et sur le même Wi-Fi/réseau que ce PC")
            script = f"Add-Printer -Name {q(name)} -IppURL {q(f'http://{host}:631/' + (pl.get('ipp_path') or 'ipp/print'))}"
            try:
                powershell(script, timeout=120)
            except PrintError:
                powershell_admin(script)  # Windows asks for administrator approval
            self.backend._ports_at = 0
            if name not in {p["name"] for p in self.backend.printers()}:
                raise PrintError("Windows n'a pas pu installer cette imprimante sans pilote (IPP). Installez le pilote officiel du fabricant puis relancez la recherche.")
            return {"installed": name}
        powershell_admin("pnputil /scan-devices")  # USB: Windows looks for the driver (Windows Update / installed packages)
        for _ in range(15):
            time.sleep(2)
            new = [p["name"] for p in self.backend.printers() if p["name"] not in before]
            if new:
                return {"installed": new[0]}
        if pl.get("device_id") and any(d["device_id"] == pl["device_id"] for d in usb_devices_without_driver()):
            raise PrintError("Windows n'a pas trouvé de pilote pour cet appareil USB. Installez le pilote officiel du fabricant puis relancez la recherche.")
        raise PrintError("Aucune nouvelle imprimante n'est apparue dans Windows. Débranchez/rebranchez le câble USB puis relancez la recherche.")

    def self_update(self, pl: dict) -> dict:
        """One-click update: download the installer from printdrop.fr, verify its SHA-256, run it silently.
        Windows shows its administrator prompt; the installer closes this agent and restarts the new one."""
        if sys.platform != "win32" or isinstance(self.backend, DryRunBackend):
            raise RuntimeError("Mise à jour automatique disponible uniquement sur Windows")
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        dest = TMP_DIR / f"PrintDrop-Setup-{pl['version']}.exe"
        try:
            self.api.download("/api/agent/installer", dest)
        except requests.RequestException as exc:
            raise RuntimeError(f"Téléchargement de la mise à jour impossible : {exc}") from exc
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        if pl.get("sha256") and digest != pl["sha256"]:
            dest.unlink(missing_ok=True)
            raise RuntimeError("Fichier de mise à jour corrompu (empreinte SHA-256 différente) : réessayez")
        import ctypes
        params = f'/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /LOG="{TMP_DIR / "update.log"}"'
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(dest), params, None, 0)
        if rc <= 32:
            raise RuntimeError("Mise à jour annulée : l'autorisation administrateur de Windows a été refusée" if rc == 5
                               else f"Windows n'a pas pu lancer l'installateur (code {rc})")
        return {"installer_started": True, "version": pl["version"], "sha256": digest}

    def copy(self, pl: dict) -> dict:
        """Automatic photocopy: WIA scan of the original, then print of the copies through the Windows spooler.
        Raises only if nothing was scanned (=> no charge). Any doubt on printing is reported, never hidden."""
        if isinstance(self.backend, DryRunBackend):
            raise RuntimeError("MODE SIMULATION : aucun scanner ni copieur n'est piloté")
        printer = self.backend.status_of(pl["printer_name"])
        if not printer or printer["status"] != "online":
            raise RuntimeError(f"Imprimante indisponible : {(printer or {}).get('detail') or 'introuvable dans Windows'}")
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="copy-", dir=str(TMP_DIR)))
        try:
            cid = self.current_cmd

            def progress(phase: str, scanned: int, printed: int = 0, total: int = 0) -> None:
                try:  # best effort: a lost progress update never interrupts the copy
                    self.api.post(f"/agent/commands/{cid}/progress", {"phase": phase, "scanned_pages": scanned, "printed_pages": printed, "total_pages": total})
                except requests.RequestException:
                    pass
            progress("scanning", 0)
            scans = wia_scan(pl["color"], int(pl.get("dpi", 300)), pl.get("source", "flatbed"), work, on_page=lambda n: progress("scanning", n))
            total = len(scans) * int(pl["copies"])
            last = {"t": 0.0}

            def printed(n: int) -> None:
                if time.time() - last["t"] >= 2:
                    last["t"] = time.time()
                    progress("printing", len(scans), min(n, total), total)
            progress("printing", len(scans), 0, total)
            pdf = work / f"copie-{int(time.time())}.pdf"
            images_to_pdf(scans, pdf, pl["color"], int(pl.get("dpi", 300)))
            job = {"order_code": "photocopie", "printer_name": pl["printer_name"], "pages": list(range(1, len(scans) + 1)),
                   "options": {"duplex": bool(pl.get("duplex")), "color": pl["color"], "copies": int(pl["copies"]), "paper_size": pl["paper_size"]}}
            try:
                self.backend.print_file(pdf, job, lambda: None, on_progress=printed)
            except PrintError as exc:
                return {"scanned_pages": len(scans), "copies_printed": None, "spool_confirmed": False, "error": f"Impression interrompue : {exc}"}
            after = self.backend.status_of(pl["printer_name"])
            if after and after["status"] != "online":
                return {"scanned_pages": len(scans), "copies_printed": None, "spool_confirmed": False,
                        "error": f"L'imprimante signale : {after['detail'] or after['status']} — vérifiez les copies sorties"}
            return {"scanned_pages": len(scans), "copies_printed": int(pl["copies"]), "spool_confirmed": True, "error": ""}
        finally:
            shutil.rmtree(work, ignore_errors=True)  # no copy of the customer's original stays on the PC

    def handle(self, job: dict) -> None:
        if job["id"] in self.journal:
            log.warning("Travail %s déjà traité localement — aucune réimpression automatique", job["order_code"])
            return
        printer = self.backend.status_of(job["printer_name"])
        if not printer or printer["status"] != "online":
            detail = printer["detail"] if printer else "imprimante introuvable"
            self.api.report(job["id"], job["lease_id"], "requeue", f"Imprimante indisponible : {detail}")
            return
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="pd_", suffix="." + job["file_kind"], dir=TMP_DIR)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            try:
                self.api.download(job["download_url"], tmp)
                if not tmp.read_bytes()[:8].startswith(MAGIC[job["file_kind"]]):
                    raise PrintError("Fichier téléchargé invalide")
            except (requests.RequestException, PrintError) as exc:
                self.api.report(job["id"], job["lease_id"], "requeue", f"Téléchargement impossible : {exc}")
                return
            if self.api.report(job["id"], job["lease_id"], "printing").status_code != 200:
                log.warning("Bail perdu pour %s — abandon sans impression", job["order_code"])
                return
            self._journal(job, "printing")  # écrit AVANT l'appel au spouleur
            try:
                def spooled():
                    self._journal(job, "spooled")
                    self.api.report(job["id"], job["lease_id"], "spooled")
                self.backend.print_file(tmp, job, spooled)
                self._journal(job, "printed")
            except PrintError as exc:
                log.error("Échec %s : %s", job["order_code"], exc)
                self._journal(job, "failed", error=str(exc))
            self.flush_reports()
        finally:
            tmp.unlink(missing_ok=True)

    def run(self, once: bool = False) -> None:
        self.recover()
        backoff = 5
        while not self.stop.is_set():
            try:
                self.flush_reports()
                poll = self.heartbeat()
                r = self.api.post("/agent/jobs/claim")
                r.raise_for_status()
                data = r.json()
                self.status = data.get("message") or f"Connecté — {time.strftime('%H:%M:%S')}"
                for job in data["jobs"]:
                    self.handle(job)
                backoff = 5
                if once:
                    return
                self.stop.wait(poll)
            except requests.RequestException as exc:
                self.status = "Serveur injoignable — nouvel essai…"
                log.warning("Serveur injoignable (%s)", exc.__class__.__name__)
                if once:
                    raise
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 120)


# ---------------------------------------------------------------- pairing, GUI, CLI
def pair(server: str, code: str, name: str) -> str:
    if not code.strip():
        raise SystemExit("Saisissez le code d'appairage affiché dans PrintDrop › Imprimantes et périphériques")
    try:
        r = requests.post(f"{server.rstrip('/')}/api/agent/pair", timeout=30,
                          json={"code": code.strip().upper(), "name": name, "hostname": socket.gethostname(), "version": VERSION})
    except requests.exceptions.SSLError:
        raise SystemExit("Connexion sécurisée impossible : vérifiez la date et l'heure de Windows, puis réessayez")
    except requests.RequestException:
        raise SystemExit(f"Impossible de joindre {server} : vérifiez la connexion Internet ou le pare-feu / antivirus de ce PC")
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", "")
        except ValueError:
            detail = ""
        raise SystemExit(f"Appairage refusé : {detail or f'erreur serveur {r.status_code}'} — générez un nouveau code dans PrintDrop et réessayez")
    data = r.json()
    save_json(CONFIG_FILE, {"server": server.rstrip("/"), "agent_id": data["agent_id"], "key": protect(data["api_key"]), "shop": data["shop_name"]})
    return data["shop_name"]


def self_test(out: str, server: str = "") -> int:
    """Installer check used by the GitHub Windows build (and by support): writes a JSON report, exit 0 only if
    everything PrintDrop needs to print is present. Scanner (WIA) is reported but not required."""
    res: dict = {"version": VERSION, "platform": sys.platform, "checks": {}}

    def chk(name: str, fn, required: bool = True) -> None:
        try:
            res["checks"][name] = {"ok": True, "required": required, "detail": str(fn())[:300]}
        except BaseException as exc:  # noqa: BLE001 - report everything
            res["checks"][name] = {"ok": False, "required": required, "detail": str(exc)[:300]}

    chk("requests", lambda: requests.__version__)
    chk("pillow", lambda: __import__("PIL").__version__)
    chk("win32print", lambda: __import__("win32print").GetDefaultPrinter() or "ok")
    chk("sumatra", WindowsBackend._find_sumatra)
    chk("printers", lambda: ", ".join(p["name"] for p in WindowsBackend(None).printers()) or "aucune")
    chk("wia_scanner", lambda: len(list_scanner_caps()), required=False)
    if server:
        def pairing() -> str:
            r = requests.post(f"{server.rstrip('/')}/api/agent/pair", timeout=30, json={"code": "XXXXXXXX", "name": "self-test", "hostname": "ci", "version": VERSION})
            if r.status_code not in (400, 401, 404, 409, 410, 422, 429):
                raise RuntimeError(f"réponse inattendue {r.status_code}")
            return f"code invalide refusé proprement ({r.status_code})"
        chk("server_pairing", pairing)
    res["ok"] = all(c["ok"] for c in res["checks"].values() if c["required"])
    Path(out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if res["ok"] else 1


def make_backend(dry_run: bool, sumatra: str | None = None):
    if dry_run:
        log.warning("MODE SIMULATION : aucune impression réelle ne sera effectuée")
        return DryRunBackend()
    if not IS_WINDOWS:
        raise SystemExit("L'impression réelle nécessite Windows. Utilisez --dry-run pour tester ailleurs.")
    return WindowsBackend(sumatra)


def start_agent(dry_run: bool = False) -> Agent:
    cfg = load_json(CONFIG_FILE, None)
    if not cfg:
        raise SystemExit("Poste non associé")
    agent = Agent(Api(cfg["server"], unprotect(cfg["key"])), make_backend(dry_run))
    threading.Thread(target=agent.run, daemon=True).start()
    return agent


def gui() -> None:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.title(f"PrintDrop pour Windows — v{VERSION}")
    root.geometry("460x300")
    state = {"agent": None}
    cfg = load_json(CONFIG_FILE, None)
    title = tk.Label(root, font=("Segoe UI", 13, "bold"))
    title.pack(pady=(16, 4))
    status = tk.Label(root, fg="#334155", wraplength=420)
    status.pack()
    frm = tk.Frame(root)
    server_var, code_var = tk.StringVar(value=DEFAULT_SERVER), tk.StringVar()

    def do_pair():
        try:
            shop = pair(server_var.get(), code_var.get(), socket.gethostname())
        except SystemExit as exc:
            messagebox.showerror("PrintDrop", str(exc))
            return
        frm.pack_forget()
        launch(shop)

    def launch(shop: str):
        title.config(text=f"Associé à « {shop} »")
        state["agent"] = start_agent()
        tick()

    def tick():
        if state["agent"]:
            status.config(text=state["agent"].status)
        root.after(2000, tick)

    if cfg:
        launch(cfg.get("shop", ""))
    else:
        title.config(text="Associer ce PC à votre boutique")
        status.config(text="Dans PrintDrop : Imprimantes et périphériques → « Générer un code d'appairage »")
        tk.Label(frm, text="Adresse PrintDrop").pack(anchor="w")
        tk.Entry(frm, textvariable=server_var, width=48).pack()
        tk.Label(frm, text="Code d'appairage (8 caractères)").pack(anchor="w", pady=(8, 0))
        tk.Entry(frm, textvariable=code_var, width=20, font=("Consolas", 14)).pack(anchor="w")
        tk.Button(frm, text="Associer", command=do_pair).pack(pady=12)
        frm.pack(pady=8)
    root.protocol("WM_DELETE_WINDOW", root.iconify)  # reste actif en arrière-plan
    root.mainloop()


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if sys.stderr:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    if len(sys.argv) == 1:
        return gui()
    if sys.argv[1] == "--self-test":  # PrintDrop.exe --self-test report.json [server]
        raise SystemExit(self_test(sys.argv[2] if len(sys.argv) > 2 else str(DATA_DIR / "self-test.json"), sys.argv[3] if len(sys.argv) > 3 else ""))
    if sys.argv[1] == "--background":
        if not load_json(CONFIG_FILE, None):
            return gui()  # started with Windows but not paired yet: show the pairing window instead of exiting silently
        start_agent()
        while True:
            time.sleep(3600)
    ap = argparse.ArgumentParser(description="PrintDrop Agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_pair = sub.add_parser("pair")
    p_pair.add_argument("--server", default=DEFAULT_SERVER)
    p_pair.add_argument("--code", required=True)
    p_pair.add_argument("--name", default=socket.gethostname())
    p_run = sub.add_parser("run")
    p_run.add_argument("--once", action="store_true")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--sumatra")
    p_pr = sub.add_parser("printers")
    p_pr.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "pair":
        print(f"Poste associé à « {pair(args.server, args.code, args.name)} ». Configuration : {CONFIG_FILE}")
    elif args.cmd == "printers":
        for p in make_backend(args.dry_run).printers():
            print(f"{'*' if p['is_default'] else ' '} {p['name']} [{p['connection_type']}] {p['status']} {p['detail']}")
    else:
        cfg = load_json(CONFIG_FILE, None)
        if not cfg:
            raise SystemExit("Poste non associé : lancez d'abord « pair »")
        Agent(Api(cfg["server"], unprotect(cfg["key"])), make_backend(args.dry_run, args.sumatra)).run(once=args.once)


if __name__ == "__main__":
    main()
