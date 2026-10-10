"""Master ContextLens local analysis pipeline."""

import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

from .audio import extract_audio, get_audio_duration
from .context import extract_context_by_time
from .insights import generate_context_insights, parse_context_flags
from .matching import SIMILARITY_THRESHOLD, validate_match_robust
from .transcription import get_words, transcribe_audio, validate_input_words


def build_frontend_response(analysis_result, ai_result=None):
    """Build the exact final 15-field response from notebook cell 29."""
    if ai_result is None:
        ai_result = {
            "status": "unavailable",
            "insight": None,
            "model": None,
            "context_flags": [],
        }

    context_flags = []

    if (
        analysis_result.get("status") == "MATCH_FOUND"
        and ai_result.get("status") == "success"
    ):
        context_flags = parse_context_flags(ai_result.get("context_flags", []))

    return {
        "analysis_id": analysis_result.get("analysis_id"),
        "created_at": analysis_result.get("created_at"),
        "status": analysis_result.get("status"),
        "clip_transcript": analysis_result.get("clip_transcript"),
        "original_duration": analysis_result.get("original_duration"),
        "clip_duration": analysis_result.get("clip_duration"),
        "similarity": analysis_result.get("similarity"),
        "second_best_similarity": analysis_result.get(
            "second_best_similarity"
        ),
        "score_gap": analysis_result.get("score_gap"),
        "threshold": analysis_result.get("threshold"),
        "match": analysis_result.get("match"),
        "context": analysis_result.get("context"),
        "context_flags": context_flags,
        "error": analysis_result.get("error"),
        "ai_context_insights": {
            "status": ai_result.get("status", "unavailable"),
            "insight": ai_result.get("insight"),
            "model": ai_result.get("model"),
        },
    }


def analyze_context(original_video, clip_video, use_ai=True):
    """Analyze a cropped clip against its original video."""
    analysis_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    def error_response(code, message):
        result = {
            "analysis_id": analysis_id,
            "created_at": created_at,
            "status": "ERROR",
            "clip_transcript": None,
            "original_duration": None,
            "clip_duration": None,
            "similarity": None,
            "second_best_similarity": None,
            "score_gap": None,
            "threshold": SIMILARITY_THRESHOLD,
            "match": None,
            "context": None,
            "error": {"code": code, "message": message},
        }
        return build_frontend_response(result)

    if not os.path.isfile(original_video):
        return error_response(
            "ORIGINAL_FILE_NOT_FOUND",
            "The original video file was not found.",
        )

    if not os.path.isfile(clip_video):
        return error_response(
            "CLIP_FILE_NOT_FOUND",
            "The cropped video file was not found.",
        )

    if os.path.getsize(original_video) == 0:
        return error_response(
            "EMPTY_ORIGINAL_FILE",
            "The original video file is empty.",
        )

    if os.path.getsize(clip_video) == 0:
        return error_response(
            "EMPTY_CLIP_FILE",
            "The cropped video file is empty.",
        )

    try:
        with tempfile.TemporaryDirectory(prefix=f"contextlens-{analysis_id}-") as work_dir:
            original_audio = os.path.join(work_dir, "original.wav")
            clip_audio = os.path.join(work_dir, "clip.wav")

            try:
                extract_audio(original_video, original_audio)
            except subprocess.CalledProcessError:
                return error_response(
                    "INVALID_ORIGINAL_MEDIA",
                    (
                        "The original file could not be processed as media or "
                        "contains no usable audio."
                    ),
                )

            try:
                extract_audio(clip_video, clip_audio)
            except subprocess.CalledProcessError:
                return error_response(
                    "INVALID_CLIP_MEDIA",
                    (
                        "The cropped file could not be processed as media or "
                        "contains no usable audio."
                    ),
                )

            try:
                original_transcript = transcribe_audio(original_audio)
                clip_transcript = transcribe_audio(clip_audio)
            except Exception:
                return error_response(
                    "TRANSCRIPTION_FAILED",
                    "The audio could not be transcribed.",
                )

            original_words = get_words(original_transcript)
            clip_words = get_words(clip_transcript)
            input_check = validate_input_words(original_words, clip_words)

            if not input_check["valid"]:
                messages = {
                    "NO_ORIGINAL_SPEECH": (
                        "No speech was detected in the original video."
                    ),
                    "NO_CLIP_SPEECH": (
                        "No speech was detected in the cropped video."
                    ),
                    "CLIP_TOO_SHORT": (
                        "The cropped video does not contain enough speech "
                        "for reliable matching."
                    ),
                    "CLIP_LONGER_THAN_ORIGINAL": (
                        "The cropped transcript is longer than the original "
                        "transcript."
                    ),
                }
                result = error_response(
                    input_check["error"],
                    messages.get(input_check["error"], "Invalid transcript input."),
                )
                result["clip_transcript"] = " ".join(
                    segment["text"] for segment in clip_transcript
                )
                result["original_duration"] = get_audio_duration(original_audio)
                result["clip_duration"] = get_audio_duration(clip_audio)
                return result

            validation = validate_match_robust(original_words, clip_words)
            result = {
                "analysis_id": analysis_id,
                "created_at": created_at,
                "status": validation["status"],
                "clip_transcript": " ".join(
                    segment["text"] for segment in clip_transcript
                ),
                "original_duration": get_audio_duration(original_audio),
                "clip_duration": get_audio_duration(clip_audio),
                "similarity": validation["best_similarity"],
                "second_best_similarity": validation["second_best_similarity"],
                "score_gap": validation["score_gap"],
                "threshold": validation["threshold"],
                "match": None,
                "context": None,
                "error": None,
            }

            if validation["status"] == "NO_MATCH":
                result["error"] = {
                    "code": "NO_MATCH",
                    "message": (
                        "No sufficiently similar excerpt was found in the "
                        "original recording."
                    ),
                }
                return build_frontend_response(result)

            if validation["status"] == "AMBIGUOUS_MATCH":
                result["error"] = {
                    "code": "AMBIGUOUS_MATCH",
                    "message": (
                        "Multiple similarly strong matches were found in the "
                        "original recording."
                    ),
                }
                return build_frontend_response(result)

            match = validation["match"]
            result["match"] = {
                "start": match["start"],
                "end": match["end"],
                "matched_text": match["matched_text"],
                "candidate_word_count": match["candidate_word_count"],
                "clip_word_count": match["clip_word_count"],
            }
            result["context"] = extract_context_by_time(
                original_transcript,
                match["start"],
                match["end"],
            )
            ai_result = generate_context_insights(result) if use_ai else None
            return build_frontend_response(result, ai_result)

    except Exception as error:
        print("Internal pipeline error:", type(error).__name__)
        return error_response(
            "PROCESSING_ERROR",
            "The video analysis could not be completed.",
        )
