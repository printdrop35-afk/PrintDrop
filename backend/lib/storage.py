"""Private document storage on local disk (Stage 1). Paths are always generated server-side;
files are never served statically — only through HMAC-signed, short-lived links."""

import os
import uuid
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", "/app/backend/storage_private")).resolve()
MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 500


class StorageError(ValueError):
    pass


def detect_kind(data: bytes) -> str:
    """Magic-number sniffing — the browser's Content-Type is never trusted."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    raise StorageError("Format non pris en charge (PDF, PNG ou JPG uniquement)")


def count_pages(data: bytes, kind: str) -> int:
    if kind != "pdf":
        return 1
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise StorageError("PDF protégé par mot de passe — impossible à imprimer")
        n = len(reader.pages)
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError("PDF illisible ou corrompu") from exc
    if n < 1:
        raise StorageError("PDF vide")
    if n > MAX_PAGES:
        raise StorageError(f"Document trop long (max {MAX_PAGES} pages)")
    return n


def save_file(org_id: str, shop_id: str, data: bytes, kind: str) -> str:
    key = f"{org_id}/{shop_id}/{uuid.uuid4().hex}.{kind}"
    path = resolve(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, 0o600)
    return key


def resolve(key: str) -> Path:
    path = (STORAGE_DIR / key).resolve()
    if STORAGE_DIR not in path.parents:
        raise StorageError("Chemin invalide")
    return path


def delete_file(key: str) -> None:
    try:
        resolve(key).unlink(missing_ok=True)
    except StorageError:
        pass
