import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, Request

from app.config import settings


ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg"}
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredUpload:
    size_bytes: int
    sha256: str
    path: Path


def sanitize_filename(filename: str) -> str:
    cleaned = SAFE_FILENAME.sub("_", Path(filename).name).strip("._")
    if not cleaned:
        raise HTTPException(422, detail={"code": "INVALID_FILENAME"})
    return cleaned[:180]


def validate_upload_request(content_type: str, size_bytes: int) -> None:
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(415, detail={"code": "UNSUPPORTED_DOCUMENT_TYPE"})
    if size_bytes <= 0 or size_bytes > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail={"code": "DOCUMENT_TOO_LARGE", "max_bytes": settings.MAX_UPLOAD_BYTES})


def issue_upload_token(document_id: str) -> tuple[str, str, datetime]:
    expires = datetime.now(UTC) + timedelta(seconds=settings.UPLOAD_URL_TTL_SECONDS)
    nonce = secrets.token_urlsafe(24)
    body = f"{document_id}:{int(expires.timestamp())}:{nonce}"
    signature = hmac.new(settings.UPLOAD_TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    token = f"{body}:{signature}"
    return token, hashlib.sha256(token.encode()).hexdigest(), expires


def verify_upload_token(token: str, expected_hash: str, document_id: str) -> None:
    if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), expected_hash):
        raise HTTPException(401, detail={"code": "INVALID_UPLOAD_TOKEN"})
    parts = token.split(":")
    if len(parts) != 4 or parts[0] != document_id:
        raise HTTPException(401, detail={"code": "INVALID_UPLOAD_TOKEN"})
    if int(parts[1]) < int(datetime.now(UTC).timestamp()):
        raise HTTPException(401, detail={"code": "UPLOAD_TOKEN_EXPIRED"})
    unsigned = ":".join(parts[:3])
    expected = hmac.new(settings.UPLOAD_TOKEN_SECRET.encode(), unsigned.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(parts[3], expected):
        raise HTTPException(401, detail={"code": "INVALID_UPLOAD_TOKEN"})


def _magic_matches(content_type: str, header: bytes) -> bool:
    return (
        (content_type == "application/pdf" and header.startswith(b"%PDF-"))
        or (content_type == "image/png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
        or (content_type == "image/jpeg" and header.startswith(b"\xff\xd8\xff"))
    )


async def stream_to_quarantine(request: Request, tenant_id: str, document_id: str, content_type: str) -> StoredUpload:
    root = settings.LOCAL_STORAGE_ROOT.resolve() / "quarantine" / tenant_id
    root.mkdir(parents=True, exist_ok=True)
    target = root / document_id
    temporary = root / f".{document_id}.uploading"
    digest = hashlib.sha256()
    size = 0
    header = b""
    try:
        with temporary.open("wb") as output:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > settings.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, detail={"code": "DOCUMENT_TOO_LARGE"})
                if len(header) < 16:
                    header += chunk[: 16 - len(header)]
                digest.update(chunk)
                output.write(chunk)
        if not _magic_matches(content_type, header):
            raise HTTPException(415, detail={"code": "CONTENT_TYPE_MISMATCH"})
        temporary.replace(target)
        return StoredUpload(size_bytes=size, sha256=digest.hexdigest(), path=target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
