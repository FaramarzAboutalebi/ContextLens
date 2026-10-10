"""Environment-backed configuration for the ContextLens AWS backend."""

import os

ALLOWED_CONTENT_TYPES = {"video/mp4"}


def require_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable is not configured: {name}")
    return value


def int_env(name, default):
    return int(os.getenv(name, str(default)))


def bucket_name():
    return require_env("UPLOAD_BUCKET")


def table_name():
    return require_env("ANALYSIS_TABLE")


def queue_url():
    return require_env("ANALYSIS_QUEUE_URL")


def upload_url_ttl_seconds():
    return int_env("UPLOAD_URL_TTL_SECONDS", 900)


def analysis_ttl_seconds():
    return int_env("ANALYSIS_TTL_SECONDS", 172800)


def max_upload_bytes():
    return int_env("MAX_UPLOAD_BYTES", 262144000)


def gemini_secret_arn():
    return os.getenv("GEMINI_SECRET_ARN", "")
