"""S3-compatible storage abstraction (Cloudflare R2)."""

import uuid

import boto3
import structlog
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.core.exceptions import StorageUploadError

log = structlog.get_logger(__name__)
settings = get_settings()

_s3_client = None


def _get_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )
    return _s3_client


def upload_image(image_bytes: bytes, chat_id: int, msg_id: int) -> tuple[str, str]:
    """Upload image bytes to S3. Returns (public_url, object_key)."""
    file_uuid = uuid.uuid4()
    key = f"products/{chat_id}/{msg_id}/{file_uuid}.jpg"

    client = _get_client()
    try:
        client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
            Body=image_bytes,
            ContentType="image/jpeg",
        )
    except (BotoCoreError, ClientError) as exc:
        log.error("s3_upload_failed", key=key, error=str(exc))
        raise StorageUploadError(f"S3 upload failed: {exc}") from exc

    proxy_url = f"{settings.api_base_url}/media/{key}"
    log.info("image_uploaded", key=key)
    return proxy_url, key


def delete_image(key: str) -> None:
    client = _get_client()
    try:
        client.delete_object(Bucket=settings.s3_bucket_name, Key=key)
    except (BotoCoreError, ClientError) as exc:
        log.warning("s3_delete_failed", key=key, error=str(exc))
