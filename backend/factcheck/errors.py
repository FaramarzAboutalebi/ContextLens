"""Safe, machine-readable errors used by the fact-check pipeline."""

from __future__ import annotations


class FactCheckError(Exception):
    """A failure safe to represent through a public error code."""

    def __init__(self, code: str, public_message: str):
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


class RateLimitError(FactCheckError):
    """A safe creation-limit rejection with a bounded retry delay."""

    def __init__(self, retry_after_seconds: int):
        super().__init__(
            "RATE_LIMITED",
            "Fact-check creation limit reached. Please try again later.",
        )
        self.retry_after_seconds = max(1, retry_after_seconds)


INVALID_INSTAGRAM_URL = "INVALID_INSTAGRAM_URL"
INSTAGRAM_DOWNLOAD_FAILED = "INSTAGRAM_DOWNLOAD_FAILED"
VIDEO_TOO_LARGE = "VIDEO_TOO_LARGE"
VIDEO_TOO_LONG = "VIDEO_TOO_LONG"
UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"
NO_AUDIO = "NO_AUDIO"
NO_SPEECH = "NO_SPEECH"
TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
GROUNDING_UNAVAILABLE = "GROUNDING_UNAVAILABLE"
PROCESSING_FAILED = "PROCESSING_FAILED"
