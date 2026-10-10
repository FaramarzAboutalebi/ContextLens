"""Adapter around the proven ContextLens FFmpeg and Faster-Whisper modules."""

from __future__ import annotations

from pathlib import Path

from core.audio import extract_audio
from core.transcription import transcribe_audio

from .errors import FactCheckError, NO_SPEECH, TRANSCRIPTION_FAILED
from .media import require_speech_energy


def transcribe_video(video_path: Path, work_dir: Path) -> dict:
    audio_path = work_dir / "audio.wav"
    try:
        extract_audio(video_path, audio_path)
        require_speech_energy(audio_path)
        segments = transcribe_audio(audio_path)
    except FactCheckError:
        raise
    except Exception as error:
        raise FactCheckError(TRANSCRIPTION_FAILED, "The video could not be transcribed.") from error

    normalized = [
        {
            "start": float(segment["start"]),
            "end": float(segment["end"]),
            "text": str(segment["text"]).strip(),
        }
        for segment in segments
        if str(segment.get("text", "")).strip()
    ]
    text = " ".join(segment["text"] for segment in normalized).strip()
    if not text:
        raise FactCheckError(NO_SPEECH, "No usable speech was detected in the video.")
    return {"text": text, "segments": normalized}
