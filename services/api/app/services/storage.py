import hashlib
import hmac
import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from app.config import settings
from fastapi import HTTPException, Request

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


def quarantine_key(tenant_id: str, document_id: str) -> str:
    return f"quarantine/{tenant_id}/{document_id}"


def document_key(tenant_id: str, document_id: str, content_type: str) -> str:
    extension = {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
    }.get(content_type, "")
    return f"documents/{tenant_id}/{document_id}{extension}"


@lru_cache(maxsize=2)
def _s3_client(public: bool = False):
    import boto3
    from botocore.config import Config

    endpoint_url = settings.S3_PUBLIC_ENDPOINT_URL if public else settings.S3_ENDPOINT_URL
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def presigned_upload_url(key: str, content_type: str) -> str:
    return _s3_client(public=True).generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.S3_QUARANTINE_BUCKET,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.UPLOAD_URL_TTL_SECONDS,
    )


def presigned_download_url(key: str, filename: str) -> str:
    return _s3_client(public=True).generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.S3_DOCUMENT_BUCKET,
            "Key": key,
            "ResponseContentDisposition": f'inline; filename="{sanitize_filename(filename)}"',
        },
        ExpiresIn=min(settings.UPLOAD_URL_TTL_SECONDS, 300),
    )


def store_private_export(key: str, payload: bytes) -> None:
    if settings.STORAGE_BACKEND == "s3":
        _s3_client().put_object(
            Bucket=settings.S3_DOCUMENT_BUCKET,
            Key=key,
            Body=payload,
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        return
    target = local_object_path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def inspect_quarantined_object(key: str, content_type: str, expected_size: int) -> tuple[int, str]:
    client = _s3_client()
    try:
        metadata = client.head_object(Bucket=settings.S3_QUARANTINE_BUCKET, Key=key)
        actual_size = int(metadata["ContentLength"])
        actual_type = str(metadata.get("ContentType") or "").split(";", 1)[0].strip()
        if actual_size != expected_size:
            raise HTTPException(
                422,
                detail={
                    "code": "CONTENT_LENGTH_MISMATCH",
                    "expected": expected_size,
                    "actual": actual_size,
                },
            )
        if actual_size <= 0 or actual_size > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(413, detail={"code": "DOCUMENT_TOO_LARGE"})
        if actual_type != content_type:
            raise HTTPException(415, detail={"code": "CONTENT_TYPE_MISMATCH"})
        response = client.get_object(Bucket=settings.S3_QUARANTINE_BUCKET, Key=key)
        digest = hashlib.sha256()
        header = b""
        observed = 0
        body = response["Body"]
        while chunk := body.read(1024 * 1024):
            observed += len(chunk)
            if observed > settings.MAX_UPLOAD_BYTES:
                raise HTTPException(413, detail={"code": "DOCUMENT_TOO_LARGE"})
            if len(header) < 16:
                header += chunk[: 16 - len(header)]
            digest.update(chunk)
        if observed != actual_size:
            raise HTTPException(422, detail={"code": "OBJECT_SIZE_CHANGED"})
        if not _magic_matches(content_type, header):
            raise HTTPException(415, detail={"code": "CONTENT_TYPE_MISMATCH"})
        return actual_size, digest.hexdigest()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(409, detail={"code": "QUARANTINE_OBJECT_UNAVAILABLE"}) from exc


def materialize_object(bucket: str, key: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _s3_client().download_file(bucket, key, str(target))
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise RuntimeError("OBJECT_DOWNLOAD_FAILED") from exc


def promote_clean_object(quarantine_object_key: str, clean_object_key: str, source: Path) -> None:
    try:
        client = _s3_client()
        client.upload_file(
            str(source),
            settings.S3_DOCUMENT_BUCKET,
            clean_object_key,
            ExtraArgs={"ContentType": _content_type_from_key(clean_object_key)},
        )
        client.delete_object(Bucket=settings.S3_QUARANTINE_BUCKET, Key=quarantine_object_key)
    except Exception as exc:
        raise RuntimeError("OBJECT_PROMOTION_FAILED") from exc


def delete_quarantined_object(key: str) -> None:
    if settings.STORAGE_BACKEND == "s3":
        _s3_client().delete_object(Bucket=settings.S3_QUARANTINE_BUCKET, Key=key)
        return
    (settings.LOCAL_STORAGE_ROOT.resolve() / key).unlink(missing_ok=True)


def _content_type_from_key(key: str) -> str:
    if key.endswith(".pdf"):
        return "application/pdf"
    if key.endswith(".png"):
        return "image/png"
    return "image/jpeg"


def copy_local_clean_object(source: Path, destination_key: str) -> None:
    destination = settings.LOCAL_STORAGE_ROOT.resolve() / destination_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(source, destination)


def local_object_path(key: str) -> Path:
    root = settings.LOCAL_STORAGE_ROOT.resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise RuntimeError("INVALID_STORAGE_KEY")
    return path


def probe_storage() -> dict[str, str]:
    if settings.STORAGE_BACKEND == "local":
        root = settings.LOCAL_STORAGE_ROOT.resolve()
        root.mkdir(parents=True, exist_ok=True)
        return {"status": "HEALTHY", "backend": "local"}
    try:
        client = _s3_client()
        client.head_bucket(Bucket=settings.S3_QUARANTINE_BUCKET)
        client.head_bucket(Bucket=settings.S3_DOCUMENT_BUCKET)
        return {"status": "HEALTHY", "backend": "s3"}
    except Exception:
        return {
            "status": "UNAVAILABLE",
            "backend": "s3",
            "error_code": "OBJECT_STORAGE_UNAVAILABLE",
        }


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
