"""S3 operations for fact-check uploads and worker inputs."""

from __future__ import annotations

from pathlib import Path

from .config import bucket_name, max_media_bytes
from .errors import FactCheckError, UNSUPPORTED_MEDIA, VIDEO_TOO_LARGE

CONTENT_TYPE = "video/mp4"


def _client():
    import boto3

    return boto3.client("s3")


def object_key(fact_check_id: str) -> str:
    return f"fact-checks/{fact_check_id}/source.mp4"


def create_upload_form(key: str, expires_in: int, client=None) -> dict:
    """Create a browser POST policy that enforces type, encryption, and size."""
    return (client or _client()).generate_presigned_post(
        Bucket=bucket_name(),
        Key=key,
        Fields={
            "Content-Type": CONTENT_TYPE,
            "x-amz-server-side-encryption": "AES256",
        },
        Conditions=[
            {"Content-Type": CONTENT_TYPE},
            {"x-amz-server-side-encryption": "AES256"},
            ["content-length-range", 1, max_media_bytes()],
        ],
        ExpiresIn=expires_in,
    )


def validate_uploaded_object(key: str, client=None) -> dict:
    metadata = (client or _client()).head_object(Bucket=bucket_name(), Key=key)
    size = int(metadata.get("ContentLength") or 0)
    if size <= 0:
        raise FactCheckError(UNSUPPORTED_MEDIA, "The uploaded video is empty.")
    if size > max_media_bytes():
        raise FactCheckError(VIDEO_TOO_LARGE, "The uploaded video exceeds the 75 MB limit.")
    if metadata.get("ContentType") != CONTENT_TYPE:
        raise FactCheckError(UNSUPPORTED_MEDIA, "The upload must use the video/mp4 content type.")
    return {"size_bytes": size}


def download_file(key: str, destination: Path, client=None) -> None:
    (client or _client()).download_file(bucket_name(), key, str(destination))


def upload_file(source: Path, key: str, client=None) -> None:
    (client or _client()).upload_file(
        str(source),
        bucket_name(),
        key,
        ExtraArgs={"ContentType": CONTENT_TYPE, "ServerSideEncryption": "AES256"},
    )
