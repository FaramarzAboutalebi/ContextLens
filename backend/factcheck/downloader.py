"""Anonymous, bounded Instagram Reel retrieval using yt-dlp."""

from __future__ import annotations

import contextlib
import os
import signal
from pathlib import Path

from .config import download_timeout_seconds, max_media_bytes
from .errors import FactCheckError, INSTAGRAM_DOWNLOAD_FAILED, VIDEO_TOO_LARGE
from .url_validation import restricted_instagram_network, validate_remote_url


class _DownloadDeadline(Exception):
    pass


@contextlib.contextmanager
def _deadline(seconds: int):
    if not hasattr(signal, "SIGALRM"):
        yield
        return
    previous = signal.getsignal(signal.SIGALRM)

    def expired(_signum, _frame):
        raise _DownloadDeadline()

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _yt_dlp_options(work_dir: Path, *, download: bool) -> dict:
    def progress_hook(status):
        if status.get("status") == "downloading":
            downloaded = int(status.get("downloaded_bytes") or 0)
            if downloaded > max_media_bytes():
                raise FactCheckError(VIDEO_TOO_LARGE, "The Reel exceeds the 75 MB limit.")

    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "cookiefile": None,
        "cachedir": False,
        "retries": 0,
        "fragment_retries": 0,
        "socket_timeout": min(20, download_timeout_seconds()),
        "max_filesize": max_media_bytes(),
        "overwrites": True,
        "restrictfilenames": True,
        "proxy": "",
        "progress_hooks": [progress_hook],
        "outtmpl": str(work_dir / "instagram.%(ext)s"),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "skip_download": not download,
    }
    return options


def _validate_extracted_network_urls(info: dict) -> None:
    candidates = []
    for item in info.get("requested_formats") or []:
        if isinstance(item, dict) and item.get("url"):
            if item.get("protocol") not in (None, "https"):
                raise FactCheckError(
                    INSTAGRAM_DOWNLOAD_FAILED,
                    "Instagram returned an unsupported streaming format. Upload an authorized MP4 instead.",
                )
            candidates.append(item["url"])
    if not candidates and info.get("url"):
        if info.get("protocol") not in (None, "https"):
            raise FactCheckError(
                INSTAGRAM_DOWNLOAD_FAILED,
                "Instagram returned an unsupported streaming format. Upload an authorized MP4 instead.",
            )
        candidates.append(info["url"])
    if not candidates:
        raise FactCheckError(INSTAGRAM_DOWNLOAD_FAILED, "Instagram did not provide downloadable media.")
    for value in candidates:
        validate_remote_url(value)


def download_instagram_reel(url: str, work_dir: Path) -> tuple[Path, dict]:
    """Download one public Reel without cookies, login, retries, or proxies."""
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError

        with restricted_instagram_network(), _deadline(download_timeout_seconds()):
            with YoutubeDL(_yt_dlp_options(work_dir, download=True)) as ydl:
                metadata = ydl.extract_info(url, download=False)
                if not isinstance(metadata, dict):
                    raise FactCheckError(INSTAGRAM_DOWNLOAD_FAILED, "Instagram did not return Reel metadata.")
                _validate_extracted_network_urls(metadata)
                downloaded = ydl.process_ie_result(metadata, download=True)
                prepared = Path(ydl.prepare_filename(downloaded))
        candidates = [prepared.with_suffix(".mp4"), prepared]
        output = next((path for path in candidates if path.is_file()), None)
        if output is None:
            outputs = sorted(work_dir.glob("instagram.*"))
            output = outputs[0] if len(outputs) == 1 else None
        if output is None or output.stat().st_size <= 0:
            raise FactCheckError(INSTAGRAM_DOWNLOAD_FAILED, "The Reel download did not produce a video.")
        if output.stat().st_size > max_media_bytes():
            raise FactCheckError(VIDEO_TOO_LARGE, "The Reel exceeds the 75 MB limit.")
        safe_metadata = {
            "extractor": str(metadata.get("extractor_key") or "Instagram"),
            "duration_seconds": metadata.get("duration"),
        }
        return output, safe_metadata
    except FactCheckError:
        raise
    except (_DownloadDeadline, DownloadError, OSError, ValueError) as error:
        raise FactCheckError(
            INSTAGRAM_DOWNLOAD_FAILED,
            "Instagram could not provide this public Reel. Upload an authorized MP4 instead.",
        ) from error
