"""Validation for the exact ContextLens 15-field analysis contract."""

import json

from .insights import ALLOWED_CONTEXT_FLAG_TYPES

REQUIRED_RESULT_FIELDS = {
    "analysis_id",
    "created_at",
    "status",
    "clip_transcript",
    "original_duration",
    "clip_duration",
    "similarity",
    "second_best_similarity",
    "score_gap",
    "threshold",
    "match",
    "context",
    "context_flags",
    "error",
    "ai_context_insights",
}

RESULT_STATUSES = {"MATCH_FOUND", "NO_MATCH", "AMBIGUOUS_MATCH", "ERROR"}


def validate_analysis_result(result):
    """Raise AssertionError unless result matches the final notebook contract."""
    assert set(result.keys()) == REQUIRED_RESULT_FIELDS
    assert result["status"] in RESULT_STATUSES
    assert isinstance(result["context_flags"], list)

    for flag in result["context_flags"]:
        assert set(flag.keys()) == {
            "type",
            "title",
            "explanation",
            "evidence",
        }
        assert flag["type"] in ALLOWED_CONTEXT_FLAG_TYPES
        assert all(
            isinstance(flag[key], str) and flag[key].strip()
            for key in ("title", "explanation", "evidence")
        )

    ai_result = result["ai_context_insights"]
    assert set(ai_result.keys()) == {"status", "insight", "model"}
    assert ai_result["status"] in {"success", "unavailable"}

    if result["status"] == "MATCH_FOUND":
        assert result["match"] is not None
        assert result["context"] is not None
        assert result["error"] is None
        assert set(result["match"].keys()) == {
            "start",
            "end",
            "matched_text",
            "candidate_word_count",
            "clip_word_count",
        }
        assert set(result["context"].keys()) == {
            "before",
            "during",
            "after",
            "word_timestamps",
            "window",
        }
    else:
        assert result["match"] is None
        assert result["context"] is None
        assert result["error"] is not None
        assert result["context_flags"] == []

    json.dumps(result)
    return True
