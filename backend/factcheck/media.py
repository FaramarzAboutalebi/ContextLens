"""FFprobe validation and audio preparation for fact-check media."""

from __future__ import annotations

import json
import math
import subprocess
import wave
from pathlib import Path

from .config import max_media_bytes, max_video_seconds
from .errors import (
    FactCheckError,
    NO_AUDIO,
    NO_SPEECH,
    UNSUPPORTED_MEDIA,
    VIDEO_TOO_LARGE,
    VIDEO_TOO_LONG,
)


def probe_media(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size <= 0:
        raise FactCheckError(UNSUPPORTED_MEDIA, "The video file is empty or missing.")
    if path.stat().st_size > max_media_bytes():
        raise FactCheckError(VIDEO_TOO_LARGE, "The video exceeds the 75 MB limit.")
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,format_name:stream=index,codec_type,codec_name",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(completed.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as error:
        raise FactCheckError(UNSUPPORTED_MEDIA, "The uploaded file is not valid media.") from error

    streams = payload.get("streams", [])
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise FactCheckError(UNSUPPORTED_MEDIA, "The file does not contain a video stream.")
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise FactCheckError(NO_AUDIO, "The video does not contain an audio stream.")
    try:
        duration = float(payload.get("format", {}).get("duration", 0))
    except (TypeError, ValueError) as error:
        raise FactCheckError(UNSUPPORTED_MEDIA, "The video duration could not be determined.") from error
    if not math.isfinite(duration) or duration <= 0:
        raise FactCheckError(UNSUPPORTED_MEDIA, "The video duration is invalid.")
    if duration > max_video_seconds() + 0.1:
        raise FactCheckError(VIDEO_TOO_LONG, "The video exceeds the 180 second limit.")
    return {
        "duration_seconds": round(duration, 2),
        "size_bytes": path.stat().st_size,
        "format": payload.get("format", {}).get("format_name", ""),
        "audio_codec": next(
            stream.get("codec_name")
            for stream in streams
            if stream.get("codec_type") == "audio"
        ),
    }


def verify_media_integrity(path: Path) -> None:
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-xerror",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-f",
                "null",
                "-",
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.SubprocessError, OSError) as error:
        raise FactCheckError(UNSUPPORTED_MEDIA, "The media file is incomplete or corrupted.") from error


def wav_has_speech_energy(path: Path, threshold: float = 0.001) -> bool:
    """Reject nearly silent audio before Whisper can hallucinate speech."""
    with wave.open(str(path), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
    if not frames:
        return False
    import numpy as np

    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(np.square(samples))))
    return math.isfinite(rms) and rms >= threshold


def require_speech_energy(path: Path) -> None:
    if not wav_has_speech_energy(path):
        raise FactCheckError(NO_SPEECH, "No usable speech was detected in the video.")

