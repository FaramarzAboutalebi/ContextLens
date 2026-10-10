"""Transcript matching logic for ContextLens."""

SIMILARITY_THRESHOLD = 80.0
AMBIGUITY_GAP = 5.0
MATCH_LENGTH_TOLERANCE = 0.20


def find_top_flexible_matches(
    original_words,
    clip_words,
    length_tolerance=MATCH_LENGTH_TOLERANCE,
    top_k=5,
):
    """Return the notebook's highest-scoring non-overlapping matches."""
    if not original_words or not clip_words:
        return []

    from rapidfuzz import fuzz

    clip_text = " ".join(word["word"] for word in clip_words)
    clip_length = len(clip_words)
    min_length = max(1, int(clip_length * (1 - length_tolerance)))
    max_length = min(
        len(original_words),
        int(clip_length * (1 + length_tolerance)),
    )
    candidates = []

    for window_length in range(min_length, max_length + 1):
        for i in range(len(original_words) - window_length + 1):
            candidate = original_words[i : i + window_length]
            candidate_text = " ".join(word["word"] for word in candidate)
            score = fuzz.ratio(clip_text, candidate_text)

            candidates.append(
                {
                    "start": candidate[0]["start"],
                    "end": candidate[-1]["end"],
                    "score": round(score, 2),
                    "matched_text": candidate_text,
                    "candidate_word_count": window_length,
                    "clip_word_count": clip_length,
                }
            )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    unique_matches = []

    for candidate in candidates:
        overlaps = False

        for existing in unique_matches:
            if (
                candidate["start"] < existing["end"]
                and candidate["end"] > existing["start"]
            ):
                overlaps = True
                break

        if not overlaps:
            unique_matches.append(candidate)

        if len(unique_matches) >= top_k:
            break

    return unique_matches


def validate_match_robust(
    original_words,
    clip_words,
    threshold=SIMILARITY_THRESHOLD,
    ambiguity_gap=AMBIGUITY_GAP,
):
    """Classify the best flexible match using the notebook's thresholds."""
    matches = find_top_flexible_matches(original_words, clip_words, top_k=2)

    if not matches:
        return {
            "status": "NO_MATCH",
            "match": None,
            "best_similarity": 0.0,
            "second_best_similarity": None,
            "score_gap": None,
            "threshold": threshold,
        }

    best = matches[0]
    second = matches[1] if len(matches) > 1 else None
    second_score = second["score"] if second else None
    score_gap = (
        round(best["score"] - second_score, 2)
        if second_score is not None
        else None
    )

    if best["score"] < threshold:
        status = "NO_MATCH"
        selected_match = None
    elif (
        second is not None
        and second["score"] >= threshold
        and score_gap <= ambiguity_gap
    ):
        status = "AMBIGUOUS_MATCH"
        selected_match = None
    else:
        status = "MATCH_FOUND"
        selected_match = best

    return {
        "status": status,
        "match": selected_match,
        "best_similarity": best["score"],
        "second_best_similarity": second_score,
        "score_gap": score_gap,
        "threshold": threshold,
    }
