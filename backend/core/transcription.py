"""Whisper transcription and transcript normalization for ContextLens."""

import re

from .audio import load_audio

MIN_CLIP_WORDS = 3
WHISPER_MODEL_NAME = "small"

_model = None


def get_whisper_model():
    """Load the notebook's Whisper model once, on first transcription."""
    global _model

    if _model is None:
        import torch
        from faster_whisper import WhisperModel

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        _model = WhisperModel(
            WHISPER_MODEL_NAME,
            device=device,
            compute_type=compute_type,
        )

    return _model


def transcribe_audio(audio_path):
    """Transcribe an extracted WAV using the notebook's Whisper settings."""
    audio = load_audio(audio_path)
    segments, _ = get_whisper_model().transcribe(
        audio,
        language="en",
        word_timestamps=True,
        beam_size=5,
    )

    results = []

    for segment in segments:
        results.append(
            {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
                "words": [
                    {
                        "word": word.word.strip(),
                        "start": round(word.start, 2),
                        "end": round(word.end, 2),
                    }
                    for word in (segment.words or [])
                ],
            }
        )

    return results


def get_words(transcript):
    """Flatten and normalize word-timestamp entries from a transcript."""
    words = []

    for segment in transcript:
        for item in segment["words"]:
            normalized = re.sub(r"[^\w']", "", item["word"].lower())

            if normalized:
                words.append(
                    {
                        "word": normalized,
                        "start": item["start"],
                        "end": item["end"],
                    }
                )

    return words


def validate_input_words(original_words, clip_words, min_clip_words=MIN_CLIP_WORDS):
    """Apply the notebook's transcript input validation rules."""
    if not original_words:
        return {"valid": False, "error": "NO_ORIGINAL_SPEECH"}

    if not clip_words:
        return {"valid": False, "error": "NO_CLIP_SPEECH"}

    if len(clip_words) < min_clip_words:
        return {"valid": False, "error": "CLIP_TOO_SHORT"}

    if len(clip_words) > len(original_words):
        return {"valid": False, "error": "CLIP_LONGER_THAN_ORIGINAL"}

    return {"valid": True, "error": None}
