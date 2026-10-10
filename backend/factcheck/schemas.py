"""Versioned output schema and strict Gemini response validation."""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any


SCHEMA_VERSION = "1.0"
ASSESSMENTS = {
    "SUPPORTED",
    "CONTRADICTED",
    "MIXED",
    "INSUFFICIENT_EVIDENCE",
}
REVIEW_STATUSES = {"SUCCESS", "NO_CHECKABLE_CLAIMS", "UNAVAILABLE"}
CONTENT_ITEM_TYPES = {
    "PREDICTION",
    "OPINION",
    "FINANCIAL_ADVICE",
    "GUARANTEED_RETURN",
}
RISK_TAGS = {
    "CENTRAL_ARGUMENT",
    "TAX_OR_LEGAL",
    "GUARANTEED_RETURN",
    "FINANCIAL_PRODUCT",
    "NUMERICAL_OR_REGULATORY",
    "OTHER",
}
CLAIM_FIDELITY_VALUES = {"PRESERVED", "PARTIAL", "MISMATCHED"}
OVERALL_VERDICTS = {
    "MOSTLY_SUPPORTED",
    "MIXED",
    "MOSTLY_MISLEADING",
    "INSUFFICIENT_EVIDENCE",
}


def _clean_text(value: Any, *, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def _normalized_claim(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _is_duplicate_claim(text: str, accepted: list[dict]) -> bool:
    normalized = _normalized_claim(text)
    for claim in accepted:
        existing = _normalized_claim(claim["text"])
        if normalized == existing or SequenceMatcher(None, normalized, existing).ratio() >= 0.96:
            return True
    return False


def _validated_claims(value: Any, transcript_duration: float, limit: int) -> list[dict]:
    if not isinstance(value, dict) or not isinstance(value.get("claims"), list):
        raise ValueError("Claim extraction did not return a claims list.")

    claims = []
    for raw in value["claims"]:
        if len(claims) >= limit:
            break
        if not isinstance(raw, dict):
            continue
        text = _clean_text(raw.get("text"), max_length=500)
        excerpt = _clean_text(raw.get("excerpt"), max_length=600)
        timestamp = raw.get("timestamp_seconds")
        if (
            not text
            or not excerpt
            or not isinstance(timestamp, (int, float))
            or _is_duplicate_claim(text, claims)
        ):
            continue
        timestamp = round(max(0.0, min(float(timestamp), transcript_duration)), 2)
        claims.append(
            {
                "claim_id": f"claim-{len(claims) + 1}",
                "text": text,
                "timestamp_seconds": timestamp,
                "excerpt": excerpt,
                "importance": raw.get("importance")
                if raw.get("importance") in {"HIGH", "MEDIUM", "LOW"}
                else "MEDIUM",
                "risk_tags": [
                    tag
                    for tag in dict.fromkeys(raw.get("risk_tags", []))
                    if tag in RISK_TAGS
                ][:5]
                if isinstance(raw.get("risk_tags"), list)
                else [],
            }
        )
    return claims


def validate_extracted_claims(
    value: Any,
    transcript_duration: float,
    limit: int = 16,
) -> list[dict]:
    """Backward-compatible claim-list validator with bounded deduplication."""
    return _validated_claims(value, transcript_duration, max(1, min(limit, 20)))


def validate_extraction(
    value: Any,
    transcript_duration: float,
    identification_limit: int = 16,
) -> dict:
    claims = _validated_claims(
        value,
        transcript_duration,
        max(8, min(identification_limit, 20)),
    )
    items = []
    raw_items = value.get("content_items", []) if isinstance(value, dict) else []
    if isinstance(raw_items, list):
        for raw in raw_items[:20]:
            if not isinstance(raw, dict) or raw.get("type") not in CONTENT_ITEM_TYPES:
                continue
            text = _clean_text(raw.get("text"), max_length=500)
            excerpt = _clean_text(raw.get("excerpt"), max_length=600)
            timestamp = raw.get("timestamp_seconds")
            if not text or not excerpt or not isinstance(timestamp, (int, float)):
                continue
            items.append(
                {
                    "item_id": f"item-{len(items) + 1}",
                    "type": raw["type"],
                    "text": text,
                    "timestamp_seconds": round(
                        max(0.0, min(float(timestamp), transcript_duration)), 2
                    ),
                    "excerpt": excerpt,
                }
            )

    raw_total = value.get("total_factual_claims_identified", len(claims))
    if not isinstance(raw_total, int) or isinstance(raw_total, bool):
        raw_total = len(claims)
    total = max(len(claims), min(raw_total, 100))
    return {
        "claims": claims,
        "content_items": items,
        "total_factual_claims_identified": total,
    }


def validate_review(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Review response must be an object.")
    assessment = value.get("assessment")
    explanation = _clean_text(value.get("explanation"), max_length=1500)
    limitations = value.get("limitations", [])
    if assessment not in ASSESSMENTS or not explanation:
        raise ValueError("Review response is missing a valid assessment or explanation.")
    if not isinstance(limitations, list):
        limitations = []
    source_indices = value.get("source_indices", [])
    if not isinstance(source_indices, list):
        source_indices = []
    claim_fidelity = value.get("claim_fidelity", "PRESERVED")
    if claim_fidelity not in CLAIM_FIDELITY_VALUES:
        claim_fidelity = "PARTIAL"
    fidelity_explanation = _clean_text(
        value.get("fidelity_explanation"), max_length=500
    )
    return {
        "assessment": assessment,
        "explanation": explanation,
        "limitations": [
            text
            for item in limitations[:5]
            if (text := _clean_text(item, max_length=300))
        ],
        "source_indices": [
            item for item in source_indices[:8] if isinstance(item, int) and not isinstance(item, bool)
        ],
        "claim_fidelity": claim_fidelity,
        "fidelity_explanation": fidelity_explanation,
    }


_ABSOLUTE_TERMS = re.compile(
    r"\b(always|never|guaranteed|completely|absolutely|zero|cannot|can't|nothing|"
    r"tax[- ]?free|locked forever|every single)\b",
    re.IGNORECASE,
)


def _claim_priority(claim: dict) -> int:
    score = {"HIGH": 50, "MEDIUM": 25, "LOW": 0}.get(claim.get("importance"), 25)
    weights = {
        "GUARANTEED_RETURN": 50,
        "TAX_OR_LEGAL": 45,
        "CENTRAL_ARGUMENT": 40,
        "NUMERICAL_OR_REGULATORY": 35,
        "FINANCIAL_PRODUCT": 30,
        "OTHER": 0,
    }
    score += sum(weights.get(tag, 0) for tag in set(claim.get("risk_tags", [])))
    if _ABSOLUTE_TERMS.search(f"{claim.get('text', '')} {claim.get('excerpt', '')}"):
        score += 25
    return score


def select_claims_for_review(claims: list[dict], limit: int) -> tuple[list[dict], list[dict]]:
    """Select the highest-impact claims without changing stable claim identifiers."""
    ordered = sorted(
        claims,
        key=lambda claim: (-_claim_priority(claim), claim.get("timestamp_seconds", 0.0)),
    )
    limit = max(1, min(limit, 8))
    return ordered[:limit], ordered[limit:]


def build_summary(
    *,
    total_identified: int,
    reviewed_claims: list[dict],
    content_items: list[dict],
) -> dict:
    reviewed = len(reviewed_claims)
    total = max(total_identified, reviewed)
    omitted = max(0, total - reviewed)
    counts = {assessment.lower(): 0 for assessment in ASSESSMENTS}
    for claim in reviewed_claims:
        assessment = claim.get("assessment")
        if assessment in ASSESSMENTS:
            counts[assessment.lower()] += 1

    conclusive = reviewed - counts["insufficient_evidence"]
    if reviewed == 0 or conclusive < math.ceil(reviewed / 2):
        verdict = "INSUFFICIENT_EVIDENCE"
    elif (
        counts["contradicted"] > counts["supported"]
        and counts["contradicted"] >= math.ceil(conclusive / 2)
    ):
        verdict = "MOSTLY_MISLEADING"
    elif (
        counts["supported"] > counts["contradicted"]
        and counts["supported"] >= math.ceil((2 * conclusive) / 3)
    ):
        verdict = "MOSTLY_SUPPORTED"
    else:
        verdict = "MIXED"

    item_counts = {item_type.lower(): 0 for item_type in CONTENT_ITEM_TYPES}
    for item in content_items:
        if item.get("type") in CONTENT_ITEM_TYPES:
            item_counts[item["type"].lower()] += 1

    parts = [
        f"Reviewed {reviewed} of {total} identified factual claims:",
        f"{counts['supported']} supported, {counts['contradicted']} contradicted,",
        f"{counts['mixed']} mixed, and {counts['insufficient_evidence']} with insufficient evidence.",
    ]
    key_findings = []
    for assessment in ("CONTRADICTED", "MIXED", "INSUFFICIENT_EVIDENCE"):
        for claim in reviewed_claims:
            if claim.get("assessment") == assessment and len(key_findings) < 3:
                key_findings.append(
                    {
                        "claim_id": claim.get("claim_id"),
                        "assessment": assessment,
                        "text": _clean_text(claim.get("text"), max_length=220),
                    }
                )
    if key_findings:
        labels = {
            "CONTRADICTED": "contradicted",
            "MIXED": "required important qualification",
            "INSUFFICIENT_EVIDENCE": "lacked adequate evidence",
        }
        findings_text = "; ".join(
            f'“{finding["text"]}” was {labels[finding["assessment"]]}'
            for finding in key_findings
        )
        parts.append(f"Key concerns: {findings_text}.")
    coverage_warning = None
    if omitted:
        coverage_warning = (
            f"Partial review: {omitted} identified factual claim"
            f"{' was' if omitted == 1 else 's were'} omitted because of the review limit."
        )
        parts.append(coverage_warning)
    elif counts["insufficient_evidence"]:
        coverage_warning = "Some reviewed claims could not be resolved with adequate evidence."
        parts.append(coverage_warning)

    summary = {
        "verdict": verdict,
        "explanation": " ".join(parts),
        "factual_claims_identified": total,
        "factual_claims_reviewed": reviewed,
        "factual_claims_omitted": omitted,
        "assessment_counts": counts,
        "content_item_counts": item_counts,
        "partial_review": omitted > 0,
        "coverage_warning": coverage_warning,
        "key_findings": key_findings,
    }
    if summary["verdict"] not in OVERALL_VERDICTS:
        raise ValueError("Invalid overall verdict.")
    return summary


def build_result(
    *,
    fact_check_id: str,
    source: dict,
    transcript: dict,
    review_status: str,
    claims: list[dict],
    model: str | None,
    total_identified: int | None = None,
    unreviewed_claims: list[dict] | None = None,
    content_items: list[dict] | None = None,
) -> dict:
    if review_status not in REVIEW_STATUSES:
        raise ValueError("Invalid review status.")
    unreviewed_claims = unreviewed_claims or []
    content_items = content_items or []
    total_identified = max(total_identified or len(claims), len(claims) + len(unreviewed_claims))
    return {
        "fact_check_id": fact_check_id,
        "status": "COMPLETED",
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "transcript": transcript,
        "review": {
            "status": review_status,
            "model": model,
            "claims": claims,
            "unreviewed_claims": unreviewed_claims,
            "content_items": content_items,
            "summary": build_summary(
                total_identified=total_identified,
                reviewed_claims=claims,
                content_items=content_items,
            ),
        },
        "error": None,
    }
