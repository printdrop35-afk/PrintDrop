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
    if data.startswith(b"PK\x03\x04") and b"word/" in data[:65536]:
        return "docx"
    raise StorageError("Format non pris en charge (PDF, Word .docx, PNG ou JPG)")


def docx_to_pdf(data: bytes) -> bytes:
    """Word -> PDF with LibreOffice (headless, isolated temp dir, 60 s timeout). The PDF is what gets priced and printed."""
    import shutil
    import subprocess
    import tempfile
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise StorageError("Conversion Word indisponible sur ce serveur — enregistrez votre document en PDF puis réessayez")
    with tempfile.TemporaryDirectory(prefix="pd_conv_") as tmp:
        src = Path(tmp) / "document.docx"
        src.write_bytes(data)
        try:
            subprocess.run([soffice, "--headless", "--norestore", f"-env:UserInstallation=file://{tmp}/profile",
                            "--convert-to", "pdf", "--outdir", tmp, str(src)], capture_output=True, timeout=60, check=False)
        except subprocess.TimeoutExpired as exc:
            raise StorageError("Conversion Word trop longue — envoyez le document en PDF") from exc
        out = Path(tmp) / "document.pdf"
        if not out.exists():
            raise StorageError("Document Word illisible — enregistrez-le en PDF puis réessayez")
        return out.read_bytes()


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
