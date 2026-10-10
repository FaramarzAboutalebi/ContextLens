"""Environment-backed configuration for the isolated fact-check stack."""

from __future__ import annotations

import os


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable is not configured: {name}")
    return value


def int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def bucket_name() -> str:
    return require_env("FACTCHECK_BUCKET")


def table_name() -> str:
    return require_env("FACTCHECK_TABLE")


def queue_url() -> str:
    return require_env("FACTCHECK_QUEUE_URL")


def upload_url_ttl_seconds() -> int:
    return int_env("UPLOAD_URL_TTL_SECONDS", 900)


def job_ttl_seconds() -> int:
    return int_env("JOB_TTL_SECONDS", 172800)


def max_media_bytes() -> int:
    return int_env("MAX_MEDIA_BYTES", 78643200)


def max_video_seconds() -> int:
    return int_env("MAX_VIDEO_SECONDS", 180)


def download_timeout_seconds() -> int:
    return int_env("DOWNLOAD_TIMEOUT_SECONDS", 60)


def gemini_secret_id() -> str:
    return os.getenv("GEMINI_SECRET_ID", "")


def gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def max_reviewed_claims() -> int:
    """Return the configured review budget, bounded by the service hard limit."""
    return max(1, min(int_env("MAX_REVIEWED_CLAIMS", 6), 8))


def max_identified_claims() -> int:
    """Bound claim discovery separately so omitted claims can be reported."""
    return max(8, min(int_env("MAX_IDENTIFIED_CLAIMS", 16), 20))


def rate_limit_per_client_hour() -> int:
    return max(1, int_env("RATE_LIMIT_PER_CLIENT_HOUR", 6))


def rate_limit_global_hour() -> int:
    return max(1, int_env("RATE_LIMIT_GLOBAL_HOUR", 30))


def rate_limit_global_day() -> int:
    return max(1, int_env("RATE_LIMIT_GLOBAL_DAY", 100))


def processing_lease_seconds() -> int:
    return int_env("PROCESSING_LEASE_SECONDS", 5400)
