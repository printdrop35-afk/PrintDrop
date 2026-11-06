#!/usr/bin/env python3
"""PrintDrop Local Agent — Windows print agent for one PrintDrop shop.

Commands:
  python printdrop_agent.py pair --server https://votre-domaine --code ABCD2345 [--name "Comptoir 1"]
  python printdrop_agent.py printers            # list detected printers and their status
  python printdrop_agent.py run [--once]        # main loop (install as a Windows service, see README)
  python printdrop_agent.py run --dry-run       # SIMULATION: no printer is used, files are copied to disk

Safety rules implemented here (server enforces them too):
  * only jobs leased to THIS agent are printed; every report carries the lease id;
  * a local journal is written BEFORE printing: a job already printed (or interrupted mid-print)
    is never printed again automatically — it is reported, and a human decides on a reprint;
  * a printer that is offline / in error is checked right before printing; the job is handed
    back to the queue untouched ("requeue") instead of being lost.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

VERSION = "0.1.0"
IS_WINDOWS = sys.platform == "win32"
DATA_DIR = Path(os.environ.get("PRINTDROP_AGENT_DIR") or (
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "PrintDrop" if IS_WINDOWS else Path.home() / ".printdrop-agent"))
CONFIG_FILE = DATA_DIR / "config.json"
JOURNAL_FILE = DATA_DIR / "journal.json"
LOG_FILE = DATA_DIR / "agent.log"
PAPER = {"A4": "A4", "A3": "A3", "A5": "A5", "Letter": "letter", "Legal": "legal"}
MAGIC = {"pdf": b"%PDF-", "png": b"\x89PNG", "jpg": b"\xff\xd8\xff"}

log = logging.getLogger("printdrop-agent")


class PrintError(Exception):
    pass


# ---------------------------------------------------------------- secrets at rest
def protect(secret: str) -> str:
    if IS_WINDOWS:
        import win32crypt  # pywin32 — DPAPI, bound to the machine account
        blob = win32crypt.CryptProtectData(secret.encode(), "PrintDrop", None, None, None, 0x4)  # LOCAL_MACHINE
        return "dpapi:" + base64.b64encode(blob).decode()
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic on NTFS and POSIX
    if not IS_WINDOWS:
        os.chmod(path, 0o600)


# ---------------------------------------------------------------- printer backends
class WindowsBackend:
    """Uses the printers and drivers installed in Windows. PDF/images are printed with SumatraPDF."""

    BAD_STATUS = {0x2: "Erreur", 0x8: "Bourrage papier", 0x10: "Plus de papier", 0x80: "Hors ligne",
                  0x400: "Intervention requise", 0x1000: "Indisponible", 0x400000: "Capot ouvert", 0x40000: "Toner vide"}

    def __init__(self, sumatra: str | None):
        import win32print  # noqa: F401 — fail early if pywin32 is missing
        self.sumatra = sumatra or self._find_sumatra()

    @staticmethod
    def _find_sumatra() -> str:
        for c in (os.environ.get("SUMATRA_PATH", ""), r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
                  str(Path(os.environ.get("LOCALAPPDATA", "")) / "SumatraPDF" / "SumatraPDF.exe"), shutil.which("SumatraPDF") or ""):
            if c and Path(c).exists():
                return c
        raise SystemExit("SumatraPDF introuvable — installez-le ou définissez SUMATRA_PATH (voir README)")

    def printers(self) -> list[dict]:
        import win32print
        default = win32print.GetDefaultPrinter()
        out = []
        for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS, None, 2):
            out.append(self._describe(p, default))
        return out

    def _describe(self, p: dict, default: str) -> dict:
        import win32print
        name, status, attrs = p["pPrinterName"], p["Status"], p["Attributes"]
        problems = [label for flag, label in self.BAD_STATUS.items() if status & flag]
        if attrs & 0x400:  # PRINTER_ATTRIBUTE_WORK_OFFLINE
            problems.append("Utiliser l'imprimante hors connexion")
        try:
            color = bool(win32print.DeviceCapabilities(name, p["pPortName"], 32))  # DC_COLORDEVICE
        except Exception:
            color = True
        state = "online" if not problems else ("offline" if status & 0x1080 or attrs & 0x400 else "error")
        return {"name": name, "is_default": name == default, "status": state, "detail": ", ".join(problems), "supports_color": color}

    def status_of(self, name: str) -> dict | None:
        return next((p for p in self.printers() if p["name"] == name), None)

    def print_file(self, path: Path, job: dict) -> None:
        o = job["options"]
        settings = [compress_pages(job["pages"]), "duplexlong" if o["duplex"] else "simplex",
                    "color" if o["color"] == "color" else "monochrome", f"{o['copies']}x", f"paper={PAPER[o['paper_size']]}"]
        cmd = [self.sumatra, "-print-to", job["printer_name"], "-print-settings", ",".join(settings), "-silent", "-exit-on-print", str(path)]
        log.info("Impression %s sur « %s » (%s)", job["order_code"], job["printer_name"], ",".join(settings))
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired as exc:
            raise PrintError("Délai dépassé lors de l'envoi au spouleur") from exc
        if res.returncode != 0:
            raise PrintError(f"SumatraPDF code {res.returncode}: {res.stderr.decode(errors='ignore')[:150]}")


class DryRunBackend:
    """SIMULATION ONLY — never prints. Copies each job to DATA_DIR/dryrun_output for inspection."""

    NAME = "PrintDrop-Simulation (aucune impression)"

    def printers(self) -> list[dict]:
        return [{"name": self.NAME, "is_default": True, "status": "online", "detail": "Mode simulation", "supports_color": True}]

    def status_of(self, name: str) -> dict | None:
        return self.printers()[0] if name == self.NAME else None

    def print_file(self, path: Path, job: dict) -> None:
        out = DATA_DIR / "dryrun_output"
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, out / f"{job['order_code']}_{job['id'][:8]}{path.suffix}")
        log.info("[SIMULATION] %s : %s pages %s, options %s", job["order_code"], job["filename"], job["pages"], job["options"])


def compress_pages(pages: list[int]) -> str:
    """[1,2,3,5] -> '1-3,5' (SumatraPDF page-range syntax)."""
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
        self.journal: dict = load_json(JOURNAL_FILE, {})

    def _journal(self, job: dict, state: str, reported: bool = False, error: str = "") -> None:
        self.journal[job["id"]] = {"state": state, "lease_id": job["lease_id"], "order": job["order_code"],
                                   "reported": reported, "error": error, "at": time.time()}
        save_json(JOURNAL_FILE, self.journal)

    def recover(self) -> None:
        """At startup: anything that was printing when the agent stopped is NOT reprinted."""
        for jid, e in self.journal.items():
            if e["state"] == "printing":
                e.update(state="failed", reported=False, error="Agent arrêté pendant l'impression — vérifiez avant de réimprimer")
        save_json(JOURNAL_FILE, self.journal)

    def flush_reports(self) -> None:
        for jid, e in list(self.journal.items()):
            if e["reported"] or e["state"] not in ("printed", "failed"):
                continue
            r = self.api.report(jid, e["lease_id"], e["state"], e.get("error", ""))
            if r.status_code in (200, 404, 409):  # 404/409: server already decided — keep local record only
                e["reported"] = True
                save_json(JOURNAL_FILE, self.journal)
        cutoff = time.time() - 7 * 86400  # keep one week of history
        self.journal = {k: v for k, v in self.journal.items() if not v["reported"] or v["at"] > cutoff}
        save_json(JOURNAL_FILE, self.journal)

    def heartbeat(self) -> int:
        r = self.api.post("/agent/heartbeat", {"version": VERSION, "printers": self.backend.printers()})
        r.raise_for_status()
        return int(r.json().get("poll_seconds", 5))

    def handle(self, job: dict) -> None:
        if job["id"] in self.journal:  # duplicate delivery — never print twice
            log.warning("Travail %s déjà traité localement — pas de réimpression automatique", job["id"])
            return
        printer = self.backend.status_of(job["printer_name"])
        if not printer or printer["status"] != "online":
            detail = printer["detail"] if printer else "imprimante introuvable"
            log.warning("Imprimante indisponible (%s) — travail %s remis en file", detail, job["order_code"])
            self.api.report(job["id"], job["lease_id"], "requeue", f"Imprimante indisponible : {detail}")
            return
        suffix = "." + job["file_kind"]
        fd, tmp_name = tempfile.mkstemp(prefix="pd_", suffix=suffix)
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
            self._journal(job, "printing")  # written BEFORE the spooler is called
            try:
                self.backend.print_file(tmp, job)
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
        while True:
            try:
                self.flush_reports()
                poll = self.heartbeat()
                r = self.api.post("/agent/jobs/claim")
                if r.status_code == 401:
                    raise SystemExit("Clé refusée : agent révoqué. Ré-appairez ce poste depuis le tableau de bord.")
                r.raise_for_status()
                data = r.json()
                if data.get("message"):
                    log.info(data["message"])
                for job in data["jobs"]:
                    self.handle(job)
                backoff = 5
                if once:
                    return
                time.sleep(poll)
            except requests.RequestException as exc:
                log.warning("Serveur injoignable (%s) — nouvel essai dans %ss", exc.__class__.__name__, backoff)
                if once:
                    raise
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)


# ---------------------------------------------------------------- CLI
def make_backend(dry_run: bool, sumatra: str | None):
    if dry_run:
        log.warning("MODE SIMULATION : aucune impression réelle ne sera effectuée")
        return DryRunBackend()
    if not IS_WINDOWS:
        raise SystemExit("L'impression réelle nécessite Windows. Utilisez --dry-run pour tester ailleurs.")
    return WindowsBackend(sumatra)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")])
    ap = argparse.ArgumentParser(description="PrintDrop Local Agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_pair = sub.add_parser("pair", help="Associer ce poste à une boutique")
    p_pair.add_argument("--server", required=True)
    p_pair.add_argument("--code", required=True)
    p_pair.add_argument("--name", default=socket.gethostname())
    p_run = sub.add_parser("run", help="Démarrer l'agent")
    p_run.add_argument("--once", action="store_true")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--sumatra")
    p_pr = sub.add_parser("printers", help="Lister les imprimantes")
    p_pr.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.cmd == "pair":
        server = args.server.rstrip("/")
        r = requests.post(f"{server}/api/agent/pair", timeout=30, json={
            "code": args.code, "name": args.name, "hostname": socket.gethostname(), "version": VERSION})
        if r.status_code != 200:
            raise SystemExit(f"Appairage refusé : {r.json().get('detail', r.text)}")
        data = r.json()
        save_json(CONFIG_FILE, {"server": server, "agent_id": data["agent_id"], "shop_name": data["shop_name"], "key": protect(data["api_key"])})
        print(f"Poste associé à « {data['shop_name']} ». Configuration : {CONFIG_FILE}")
        return
    if args.cmd == "printers":
        for p in make_backend(args.dry_run, None).printers():
            print(f"{'*' if p['is_default'] else ' '} {p['name']:<50} {p['status']:<8} {'couleur' if p['supports_color'] else 'N&B'} {p['detail']}")
        return
    cfg = load_json(CONFIG_FILE, None)
    if not cfg:
        raise SystemExit("Poste non associé. Lancez d'abord : printdrop_agent.py pair --server … --code …")
    log.info("PrintDrop Agent %s — boutique « %s »", VERSION, cfg["shop_name"])
    Agent(Api(cfg["server"], unprotect(cfg["key"])), make_backend(args.dry_run, args.sumatra)).run(once=args.once)


if __name__ == "__main__":
    main()
