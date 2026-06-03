from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Protocol

from app.config import Settings


class DocumentStorage(Protocol):
    def store_upload(self, *, filename: str, data: bytes, content_type: str | None = None) -> str:
        ...


@dataclass(frozen=True)
class LocalDocumentStorage:
    root_dir: Path

    def store_upload(self, *, filename: str, data: bytes, content_type: str | None = None) -> str:
        key = _upload_key(filename=filename, data=data)
        destination = self.root_dir / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return f"local://{key}"


class R2DocumentStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        client=None,
    ) -> None:
        self.bucket = bucket
        self.client = client or _create_s3_client(
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )

    def store_upload(self, *, filename: str, data: bytes, content_type: str | None = None) -> str:
        key = _upload_key(filename=filename, data=data)
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            **extra_args,
        )
        return f"r2://{self.bucket}/{key}"


def create_document_storage(settings: Settings) -> DocumentStorage:
    match settings.document_storage_provider:
        case "local":
            return LocalDocumentStorage(root_dir=Path(settings.local_document_storage_dir))
        case "r2":
            missing = [
                name
                for name, value in {
                    "CLOUDFLARE_R2_ENDPOINT_URL": settings.cloudflare_r2_endpoint_url,
                    "CLOUDFLARE_R2_ACCESS_KEY_ID": settings.cloudflare_r2_access_key_id,
                    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": settings.cloudflare_r2_secret_access_key,
                    "CLOUDFLARE_R2_BUCKET": settings.cloudflare_r2_bucket,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError("Missing R2 storage settings: " + ", ".join(missing))

            return R2DocumentStorage(
                endpoint_url=settings.cloudflare_r2_endpoint_url or "",
                access_key_id=settings.cloudflare_r2_access_key_id or "",
                secret_access_key=settings.cloudflare_r2_secret_access_key or "",
                bucket=settings.cloudflare_r2_bucket or "",
            )
        case unsupported:
            raise ValueError(f"Unsupported DOCUMENT_STORAGE_PROVIDER '{unsupported}'")


def _upload_key(*, filename: str, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()[:16]
    safe_name = _safe_filename(filename)
    return f"uploads/{digest}-{safe_name}"


def _safe_filename(filename: str) -> str:
    name = Path(filename).name or "uploaded-document"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "uploaded-document"


def _create_s3_client(*, endpoint_url: str, access_key_id: str, secret_access_key: str):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )
