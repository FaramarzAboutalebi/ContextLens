"""Tests that do not require MP4 fixtures, Whisper inference, or Gemini."""

import importlib.util
import unittest

from core.analyzer import build_frontend_response
from core.context import extract_context_by_time
from core.insights import ALLOWED_CONTEXT_FLAG_TYPES, parse_context_flags
from core.matching import validate_match_robust
from test_local import validate_final_contract


def timed_words(text, start=0.0):
    return [
        {"word": word, "start": start + index, "end": start + index + 0.5}
        for index, word in enumerate(text.split())
    ]


class MatchingTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("rapidfuzz"),
        "rapidfuzz is not installed",
    )
    def test_exact_unique_match(self):
        original = timed_words("zero alpha beta gamma omega")
        clip = timed_words("alpha beta gamma")
        result = validate_match_robust(original, clip)
        self.assertEqual(result["status"], "MATCH_FOUND")
        self.assertEqual(result["best_similarity"], 100.0)

    @unittest.skipUnless(
        importlib.util.find_spec("rapidfuzz"),
        "rapidfuzz is not installed",
    )
    def test_repeated_exact_match_is_ambiguous(self):
        original = timed_words("alpha beta gamma gap alpha beta gamma")
        clip = timed_words("alpha beta gamma")
        result = validate_match_robust(original, clip)
        self.assertEqual(result["status"], "AMBIGUOUS_MATCH")
        self.assertEqual(result["score_gap"], 0.0)


class ContextTests(unittest.TestCase):
    def test_words_are_partitioned_around_match(self):
        words = timed_words("before one matched words after one")
        transcript = [{"words": words}]
        result = extract_context_by_time(transcript, 2.0, 4.0)
        self.assertEqual(result["before"], "before one")
        self.assertEqual(result["during"], "matched words")
        self.assertEqual(result["after"], "after one")


class InsightTests(unittest.TestCase):
    def test_invalid_flags_are_discarded(self):
        valid_type = "ATTRIBUTION_CHANGE"
        flags = parse_context_flags(
            [
                {
                    "type": valid_type,
                    "title": " Attribution removed ",
                    "explanation": " Explanation ",
                    "evidence": " Evidence ",
                },
                {
                    "type": "UNSUPPORTED",
                    "title": "Bad",
                    "explanation": "Bad",
                    "evidence": "Bad",
                },
            ]
        )
        self.assertEqual(len(ALLOWED_CONTEXT_FLAG_TYPES), 7)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["title"], "Attribution removed")


class ContractTests(unittest.TestCase):
    def test_error_response_has_exact_contract(self):
        response = build_frontend_response(
            {
                "analysis_id": "test-id",
                "created_at": "2026-01-01T00:00:00+00:00",
                "status": "ERROR",
                "clip_transcript": None,
                "original_duration": None,
                "clip_duration": None,
                "similarity": None,
                "second_best_similarity": None,
                "score_gap": None,
                "threshold": 80.0,
                "match": None,
                "context": None,
                "error": {"code": "TEST", "message": "Test error."},
            }
        )
        self.assertTrue(validate_final_contract(response))
        self.assertEqual(len(response), 15)


if __name__ == "__main__":
    unittest.main()
