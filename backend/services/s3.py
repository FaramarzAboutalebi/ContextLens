"""S3 upload and download operations for ContextLens analyses."""

from settings import ALLOWED_CONTENT_TYPES, bucket_name, max_upload_bytes


def _client():
    import boto3

    return boto3.client("s3")


def object_keys(analysis_id):
    prefix = f"analyses/{analysis_id}"
    return {
        "original": f"{prefix}/original.mp4",
        "clip": f"{prefix}/clip.mp4",
        "original_poster": f"{prefix}/original-poster.jpg",
        "clip_poster": f"{prefix}/clip-poster.jpg",
    }


def create_upload_url(key, content_type, expires_in, client=None):
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("Only video/mp4 uploads are supported.")

    s3 = client or _client()
    return s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket_name(),
            "Key": key,
            "ContentType": content_type,
            "ServerSideEncryption": "AES256",
        },
        ExpiresIn=expires_in,
        HttpMethod="PUT",
    )


def create_playback_url(key, expires_in, client=None):
    """Create a short-lived URL that streams one private MP4 object."""
    s3 = client or _client()
    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket_name(),
            "Key": key,
            "ResponseContentType": "video/mp4",
            "ResponseContentDisposition": "inline",
        },
        ExpiresIn=expires_in,
        HttpMethod="GET",
    )


def create_poster_url(key, expires_in, client=None):
    """Create a short-lived URL for one private JPEG video poster."""
    s3 = client or _client()
    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket_name(),
            "Key": key,
            "ResponseContentType": "image/jpeg",
            "ResponseContentDisposition": "inline",
        },
        ExpiresIn=expires_in,
        HttpMethod="GET",
    )


def object_exists(key, client=None):
    """Return whether a private S3 object exists without exposing its contents."""
    s3 = client or _client()
    try:
        s3.head_object(Bucket=bucket_name(), Key=key)
        return True
    except Exception as error:
        response = getattr(error, "response", {})
        code = str(response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def validate_uploaded_object(key, client=None):
    s3 = client or _client()
    metadata = s3.head_object(Bucket=bucket_name(), Key=key)
    size = metadata.get("ContentLength", 0)
    content_type = metadata.get("ContentType", "")

    if size <= 0:
        raise ValueError("Uploaded video is empty.")
    if size > max_upload_bytes():
        raise ValueError("Uploaded video exceeds the configured size limit.")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("Uploaded object must use the video/mp4 content type.")

    return {"key": key, "size": size, "content_type": content_type}


def download_file(key, destination, client=None):
    s3 = client or _client()
    s3.download_file(bucket_name(), key, str(destination))


def upload_poster(key, source, client=None):
    """Upload a generated poster as a private, encrypted JPEG object."""
    s3 = client or _client()
    s3.upload_file(
        str(source),
        bucket_name(),
        key,
        ExtraArgs={
            "ContentType": "image/jpeg",
            "ServerSideEncryption": "AES256",
        },
    )
