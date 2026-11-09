"""Private document storage on local disk (Stage 1). Paths are always generated server-side;
files are never served statically — only through HMAC-signed, short-lived links."""

import os
import uuid
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", "/app/backend/storage_private")).resolve()
MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 500


MEDIA_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg"}


class StorageError(ValueError):
    pass


def extract_pages(data: bytes, pages: list[int]) -> bytes:
    """New PDF containing only the given 1-based pages, in order (in memory, no temp file)."""
    reader = PdfReader(BytesIO(data))
    writer = PdfWriter()
    for n in pages:
        writer.add_page(reader.pages[n - 1])
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


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


def _convertapi_token() -> str:
    """CONVERTAPI_TOKEN may be the bare token or a full ConvertAPI request URL copied from their dashboard (…?auth=TOKEN)."""
    raw = os.environ.get("CONVERTAPI_TOKEN", "").strip().strip('"').strip("'")
    if raw.lower().startswith("http"):
        from urllib.parse import parse_qs, urlparse
        q = {k.lower(): v[0] for k, v in parse_qs(urlparse(raw).query).items() if v}
        return q.get("auth") or q.get("secret") or q.get("token") or ""
    return raw


async def convert_docx(data: bytes, filename: str = "document.docx") -> bytes:
    """Word -> PDF. Production: ConvertAPI (EU endpoint, in-memory, StoreFile=false). Fallback: local LibreOffice (preview)."""
    import asyncio
    import httpx
    token = _convertapi_token()
    if not token:
        return await asyncio.to_thread(docx_to_pdf, data)
    base = os.environ.get("CONVERTAPI_BASE_URL", "https://eu-v2.convertapi.com").rstrip("/")
    timeout = httpx.Timeout(connect=10.0, read=140.0, write=60.0, pool=10.0)
    for delay in (0, 5, 10):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{base}/convert/docx/to/pdf",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/octet-stream"},
                    data={"StoreFile": "false", "Timeout": "120"},
                    files={"File": ("document.docx", data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                )
        except httpx.HTTPError as exc:
            raise StorageError("Service de conversion Word momentanément indisponible — réessayez ou envoyez un PDF") from exc
        if r.status_code == 503:
            continue
        if r.status_code in (401, 402, 403):
            raise StorageError("Conversion Word indisponible pour le moment — enregistrez votre document en PDF puis réessayez")
        if r.is_error:
            code = 0
            try:
                code = int(r.json().get("Code", 0))
            except (ValueError, TypeError, AttributeError):
                pass
            if code == 5003:
                raise StorageError("Ce document Word est protégé par un mot de passe")
            raise StorageError("Ce document Word n'a pas pu être converti — enregistrez-le en PDF puis réessayez")
        if not r.content.startswith(b"%PDF-"):
            raise StorageError("Réponse de conversion invalide — réessayez ou envoyez un PDF")
        return r.content
    raise StorageError("Service de conversion Word occupé — réessayez dans un instant")
