"""Audio extraction and WAV utilities for ContextLens."""

import subprocess
import wave

def extract_audio(video_path, audio_path):
    """Extract mono, 16 kHz, 16-bit PCM audio from a video with FFmpeg."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
    )


def load_audio(audio_path):
    """Load a mono, 16 kHz, 16-bit PCM WAV as normalized float32 samples."""
    import numpy as np

    with wave.open(str(audio_path), "rb") as wav:
        if wav.getframerate() != 16000:
            raise ValueError("Audio must be 16 kHz.")

        if wav.getnchannels() != 1:
            raise ValueError("Audio must be mono.")

        if wav.getsampwidth() != 2:
            raise ValueError("Audio must be 16-bit PCM.")

        audio = np.frombuffer(
            wav.readframes(wav.getnframes()),
            dtype=np.int16,
        )

    return audio.astype(np.float32) / 32768.0


def get_audio_duration(audio_path):
    """Return WAV duration in seconds, rounded to two decimal places."""
    with wave.open(str(audio_path), "rb") as wav:
        return round(wav.getnframes() / wav.getframerate(), 2)
