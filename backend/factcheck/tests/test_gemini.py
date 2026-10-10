import unittest
from types import SimpleNamespace

from factcheck.gemini_review import _exact_transcript_quote, _finalize_review, _grounding_sources


class GeminiValidationTests(unittest.TestCase):
    def test_exact_quote_is_taken_from_timestamped_transcript(self):
        segments = [
            {"start": 0.0, "end": 2.0, "text": "First exact sentence."},
            {"start": 2.0, "end": 4.0, "text": "Second exact sentence."},
        ]
        self.assertEqual(
            _exact_transcript_quote(segments, 2.5),
            "Second exact sentence.",
        )

    @staticmethod
    def _response(*, text="", chunks=None, supports=None):
        return SimpleNamespace(
            text=text,
            candidates=[
                SimpleNamespace(
                    grounding_metadata=SimpleNamespace(
                        grounding_chunks=chunks or [],
                        grounding_supports=supports or [],
                    )
                )
            ],
        )

    def test_only_https_grounding_metadata_becomes_sources(self):
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    grounding_metadata=SimpleNamespace(
                        grounding_chunks=[
                            SimpleNamespace(web=SimpleNamespace(uri="https://nasa.gov/source", title="nasa.gov")),
                            SimpleNamespace(web=SimpleNamespace(uri="javascript:alert(1)", title="Bad")),
                        ],
                        grounding_supports=[
                            SimpleNamespace(
                                segment=SimpleNamespace(text="NASA directly confirms the launch date."),
                                grounding_chunk_indices=[0, 1],
                            )
                        ],
                    )
                )
            ]
        )
        self.assertEqual(
            _grounding_sources(response),
            [
                {
                    "title": "nasa.gov",
                    "url": "https://nasa.gov/source",
                    "authority": "PRIMARY",
                    "evidence_excerpt": "NASA directly confirms the launch date.",
                }
            ],
        )

    def test_secondary_only_evidence_is_visible_as_a_limitation(self):
        result = _finalize_review(
            {
                "claim_id": "claim-1",
                "text": "A narrow factual claim.",
                "timestamp_seconds": 1.0,
                "excerpt": "A narrow factual claim.",
            },
            {
                "assessment": "SUPPORTED",
                "explanation": "Direct evidence supports it.",
                "limitations": [],
                "source_indices": [1],
            },
            [
                {
                    "title": "example.com",
                    "url": "https://example.com/evidence",
                    "authority": "SECONDARY",
                    "evidence_excerpt": "The narrow claim is confirmed.",
                }
            ],
        )
        self.assertEqual(result["assessment"], "SUPPORTED")
        self.assertEqual(result["sources"][0]["authority"], "SECONDARY")
        self.assertIn("No authoritative primary source", result["limitations"][0])

    def test_partial_claim_fidelity_prevents_supported_verdict(self):
        result = _finalize_review(
            {
                "claim_id": "claim-1",
                "text": "Bona fide loan proceeds are generally not income.",
                "timestamp_seconds": 50.0,
                "excerpt": "The trust loan is tax-free.",
                "context_excerpt": (
                    "We will repeatedly take out larger loans to avoid paying taxes until we die."
                ),
            },
            {
                "assessment": "SUPPORTED",
                "explanation": "A genuine loan creates a repayment obligation.",
                "limitations": [],
                "source_indices": [1],
                "claim_fidelity": "PARTIAL",
                "fidelity_explanation": "The normalized claim omits the repeated tax-avoidance scheme.",
            },
            [
                {
                    "title": "irs.gov",
                    "url": "https://irs.gov/source",
                    "authority": "PRIMARY",
                    "evidence_excerpt": "Bona fide loans are not income when received.",
                }
            ],
        )
        self.assertEqual(result["assessment"], "MIXED")
        self.assertIn("narrower rule", result["explanation"])

    def test_omitted_absolute_language_prevents_supported_verdict(self):
        result = _finalize_review(
            {
                "claim_id": "claim-1",
                "text": "Some Roth distributions are tax free.",
                "timestamp_seconds": 1.0,
                "excerpt": "Roth profits are always completely tax-free.",
                "context_excerpt": "Roth profits are always completely tax-free.",
            },
            {
                "assessment": "SUPPORTED",
                "explanation": "Qualified distributions are tax free.",
                "limitations": [],
                "source_indices": [1],
                "claim_fidelity": "PRESERVED",
                "fidelity_explanation": "",
            },
            [
                {
                    "title": "irs.gov",
                    "url": "https://irs.gov/source",
                    "authority": "PRIMARY",
                    "evidence_excerpt": "Qualified distributions are tax free.",
                }
            ],
        )
        self.assertEqual(result["assessment"], "MIXED")
        self.assertEqual(result["claim_fidelity"], "PARTIAL")

    def test_missing_grounding_metadata_returns_no_sources(self):
        response = SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=None)])
        self.assertEqual(_grounding_sources(response), [])

    def test_uncited_and_low_quality_grounding_chunks_are_rejected(self):
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    grounding_metadata=SimpleNamespace(
                        grounding_chunks=[
                            SimpleNamespace(web=SimpleNamespace(uri="https://irs.gov/direct", title="irs.gov")),
                            SimpleNamespace(web=SimpleNamespace(uri="https://reddit.com/topic", title="reddit.com")),
                            SimpleNamespace(web=SimpleNamespace(uri="https://example.com/general", title="example.com")),
                        ],
                        grounding_supports=[
                            SimpleNamespace(
                                segment=SimpleNamespace(text="A forum discussion and broad article."),
                                grounding_chunk_indices=[1, 2],
                            )
                        ],
                    )
                )
            ]
        )
        self.assertEqual(
            _grounding_sources(response),
            [
                {
                    "title": "example.com",
                    "url": "https://example.com/general",
                    "authority": "SECONDARY",
                    "evidence_excerpt": "A forum discussion and broad article.",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
