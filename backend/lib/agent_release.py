"""Platform-wide Windows agent release (installer link + latest version), editable by the super-admin.
Stored once in db.platform_settings; falls back to AGENT_DOWNLOAD_URL / AGENT_VERSION env values."""

import hashlib
import os
import re
from pathlib import Path

from lib.db import db

RELEASE_ID = "agent_release"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
DOWNLOAD_PATH = "/api/agent-download/file"  # same-origin, served from GridFS


BUNDLED_DIR = Path(__file__).resolve().parent.parent / "agent_dist"  # installer built by agent/installer/build_nsis.sh, shipped with the app
BUNDLED_PREFIX = "bundled:"
_bundled_cache: dict = {}


def bundled_installer() -> dict | None:
    """Newest PrintDrop-Setup-x.y.z.exe shipped in backend/agent_dist (checked: PE + NSIS marker + matching .sha256)."""
    best = None
    for f in BUNDLED_DIR.glob("PrintDrop-Setup-*.exe"):
        m = re.match(r"^PrintDrop-Setup-(\d+\.\d+\.\d+)\.exe$", f.name)
        if m and (best is None or _parts(m.group(1)) > _parts(best[1])):
            best = (f, m.group(1))
    if not best:
        return None
    f, version = best
    key = (str(f), f.stat().st_mtime, f.stat().st_size)
    if _bundled_cache.get("key") != key:
        data = f.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        side = f.with_name(f.name + ".sha256")
        expected = side.read_text().split()[0] if side.exists() else digest
        ok = data[:2] == b"MZ" and b"NullsoftInst" in data and expected == digest
        _bundled_cache.update(key=key, value={"file_key": BUNDLED_PREFIX + f.name, "filename": f.name, "sha256": digest,
                                              "size_bytes": len(data), "version": version} if ok else None)
    return _bundled_cache["value"]


async def read_installer(file_key: str) -> bytes:
    if file_key.startswith(BUNDLED_PREFIX):
        return (BUNDLED_DIR / Path(file_key[len(BUNDLED_PREFIX):]).name).read_bytes()
    from lib.storage import read_file
    return await read_file(file_key)


async def get_release() -> dict:
    doc = await db.platform_settings.find_one({"id": RELEASE_ID}, {"_id": 0}) or {}
    if not doc.get("file_key") and not doc.get("url") and not os.environ.get("AGENT_DOWNLOAD_URL"):
        b = bundled_installer()
        if b:  # shipped installer: used unless the super-admin uploads one or sets an external link
            doc = {**doc, **b}
    has_file = bool(doc.get("file_key"))
    return {
        # an installer uploaded to printdrop.fr wins over an external link
        "url": DOWNLOAD_PATH if has_file else (doc.get("url") or os.environ.get("AGENT_DOWNLOAD_URL", "")),
        "external_url": doc.get("url", ""),
        "file_key": doc.get("file_key", ""),
        "filename": doc.get("filename", ""),
        "sha256": doc.get("sha256", ""),
        "size_bytes": doc.get("size_bytes", 0),
        "version": doc.get("version") or os.environ.get("AGENT_VERSION", "0.2.0"),
        "notes": doc.get("notes", ""),
        "updated_at": doc.get("updated_at"),
    }


def _parts(v: str) -> tuple[int, ...] | None:
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_outdated(installed: str, latest: str) -> bool:
    """True only when both versions are readable and the installed one is older (unknown ≠ outdated)."""
    a, b = _parts(installed), _parts(latest)
    return bool(a and b and a < b)
