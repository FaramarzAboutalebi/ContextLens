import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from factcheck.errors import FactCheckError
from factcheck.media import probe_media
from factcheck.schemas import (
    build_result,
    build_summary,
    select_claims_for_review,
    validate_extracted_claims,
    validate_extraction,
    validate_review,
)


class SchemaTests(unittest.TestCase):
    def test_claims_are_configurably_capped_and_timestamp_bounded(self):
        raw = {
            "claims": [
                {"text": f"Claim {i}", "timestamp_seconds": 999, "excerpt": "Exact"}
                for i in range(5)
            ]
        }
        claims = validate_extracted_claims(raw, 10.0, limit=8)
        self.assertEqual(len(claims), 5)
        self.assertEqual(claims[0]["timestamp_seconds"], 10.0)

    def test_more_than_three_claims_are_kept_and_duplicates_removed(self):
        raw = {
            "total_factual_claims_identified": 7,
            "claims": [
                {"text": f"Distinct factual claim {i}", "timestamp_seconds": i, "excerpt": f"Claim {i}"}
                for i in range(6)
            ]
            + [{"text": "Distinct factual claim 0", "timestamp_seconds": 0, "excerpt": "Claim 0"}],
            "content_items": [
                {
                    "type": "PREDICTION",
                    "text": "The market will rise tomorrow.",
                    "timestamp_seconds": 9,
                    "excerpt": "The market will rise tomorrow.",
                },
                {
                    "type": "FINANCIAL_ADVICE",
                    "text": "Buy this fund.",
                    "timestamp_seconds": 10,
                    "excerpt": "Buy this fund.",
                },
                {
                    "type": "GUARANTEED_RETURN",
                    "text": "This always doubles your money.",
                    "timestamp_seconds": 11,
                    "excerpt": "This always doubles your money.",
                },
            ],
        }
        result = validate_extraction(raw, 20.0, identification_limit=16)
        self.assertEqual(len(result["claims"]), 6)
        self.assertEqual(result["total_factual_claims_identified"], 7)
        self.assertEqual(
            [item["type"] for item in result["content_items"]],
            ["PREDICTION", "FINANCIAL_ADVICE", "GUARANTEED_RETURN"],
        )

    def test_invalid_review_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_review({"assessment": "TRUE", "explanation": "No"})

    def test_result_is_versioned_and_frontend_friendly(self):
        result = build_result(
            fact_check_id="id",
            source={"type": "manual_upload", "duration_seconds": 1.0},
            transcript={"text": "hello", "segments": [], "duration_seconds": 1.0},
            review_status="NO_CHECKABLE_CLAIMS",
            claims=[],
            model="model",
        )
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertIsNone(result["error"])
        self.assertIn("summary", result["review"])
        self.assertIn("unreviewed_claims", result["review"])
        self.assertIn("content_items", result["review"])

    def test_summary_aggregation_is_deterministic_and_reports_partial_review(self):
        claims = [
            {"assessment": "CONTRADICTED"},
            {"assessment": "CONTRADICTED"},
            {"assessment": "SUPPORTED"},
            {"assessment": "MIXED"},
            {"assessment": "INSUFFICIENT_EVIDENCE"},
        ]
        summary = build_summary(
            total_identified=7,
            reviewed_claims=claims,
            content_items=[
                {"type": "OPINION"},
                {"type": "FINANCIAL_ADVICE"},
                {"type": "GUARANTEED_RETURN"},
            ],
        )
        self.assertEqual(summary["verdict"], "MOSTLY_MISLEADING")
        self.assertEqual(summary["factual_claims_omitted"], 2)
        self.assertTrue(summary["partial_review"])
        self.assertEqual(summary["content_item_counts"]["financial_advice"], 1)
        self.assertEqual(summary["key_findings"][0]["assessment"], "CONTRADICTED")
        self.assertIn("Key concerns:", summary["explanation"])

    def test_high_impact_claims_are_selected_before_earlier_low_risk_claims(self):
        claims = [
            {
                "claim_id": "claim-1",
                "text": "A low-impact background fact.",
                "excerpt": "A low-impact background fact.",
                "timestamp_seconds": 1.0,
                "importance": "LOW",
                "risk_tags": ["OTHER"],
            },
            {
                "claim_id": "claim-2",
                "text": "This investment is guaranteed to double without tax.",
                "excerpt": "This investment is guaranteed to double without tax.",
                "timestamp_seconds": 20.0,
                "importance": "HIGH",
                "risk_tags": ["GUARANTEED_RETURN", "TAX_OR_LEGAL", "CENTRAL_ARGUMENT"],
            },
        ]
        reviewed, omitted = select_claims_for_review(claims, 1)
        self.assertEqual(reviewed[0]["claim_id"], "claim-2")
        self.assertEqual(omitted[0]["claim_id"], "claim-1")

    def test_weak_evidence_majority_yields_insufficient_verdict(self):
        summary = build_summary(
            total_identified=3,
            reviewed_claims=[
                {"assessment": "INSUFFICIENT_EVIDENCE"},
                {"assessment": "INSUFFICIENT_EVIDENCE"},
                {"assessment": "SUPPORTED"},
            ],
            content_items=[],
        )
        self.assertEqual(summary["verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(summary["partial_review"])
        self.assertIn("adequate evidence", summary["coverage_warning"])


class MediaTests(unittest.TestCase):
    def _probe(self, streams, duration="10.0", size=1024):
        temp = tempfile.NamedTemporaryFile(delete=False)
        try:
            temp.write(b"x" * size)
            temp.close()
            completed = Mock(stdout=json.dumps({"format": {"duration": duration, "format_name": "mp4"}, "streams": streams}))
            with patch("factcheck.media.subprocess.run", return_value=completed), patch.dict(
                os.environ,
                {"MAX_MEDIA_BYTES": "2048", "MAX_VIDEO_SECONDS": "180"},
                clear=False,
            ):
                return probe_media(Path(temp.name))
        finally:
            Path(temp.name).unlink(missing_ok=True)

    def test_valid_media(self):
        result = self._probe(
            [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        )
        self.assertEqual(result["audio_codec"], "aac")

    def test_missing_audio_is_rejected(self):
        with self.assertRaises(FactCheckError):
            self._probe([{"codec_type": "video", "codec_name": "h264"}])

    def test_long_video_is_rejected(self):
        with self.assertRaises(FactCheckError):
            self._probe(
                [
                    {"codec_type": "video", "codec_name": "h264"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                duration="181",
            )


if __name__ == "__main__":
    unittest.main()
