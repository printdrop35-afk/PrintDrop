"""Platform-wide Windows agent release (installer link + latest version), editable by the super-admin.
Stored once in db.platform_settings; falls back to AGENT_DOWNLOAD_URL / AGENT_VERSION env values."""

import os
import re

from lib.db import db

RELEASE_ID = "agent_release"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
DOWNLOAD_PATH = "/api/agent-download/file"  # same-origin, served from GridFS


async def get_release() -> dict:
    doc = await db.platform_settings.find_one({"id": RELEASE_ID}, {"_id": 0}) or {}
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
