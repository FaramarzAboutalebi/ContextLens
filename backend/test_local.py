"""Run ContextLens locally against an original MP4 and a cropped MP4."""

import argparse
import json
from pathlib import Path

from core.analyzer import analyze_context
from core.insights import ALLOWED_CONTEXT_FLAG_TYPES


def validate_final_contract(result):
    """Validate the exact final JSON contract from notebook cell 39."""
    required_top_level = {
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

    assert set(result.keys()) == required_top_level, (
        f"Unexpected top-level keys: {set(result.keys())}"
    )
    assert result["status"] in {
        "MATCH_FOUND",
        "NO_MATCH",
        "AMBIGUOUS_MATCH",
        "ERROR",
    }
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
            for key in ["title", "explanation", "evidence"]
        )

    ai = result["ai_context_insights"]
    assert set(ai.keys()) == {"status", "insight", "model"}
    assert ai["status"] in {"success", "unavailable"}

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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze a cropped MP4 against its original MP4.",
    )
    parser.add_argument("original_video", type=Path)
    parser.add_argument("clip_video", type=Path)
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip optional Gemini insights and context flags.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    result = analyze_context(
        str(args.original_video),
        str(args.clip_video),
        use_ai=not args.no_ai,
    )
    validate_final_contract(result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
