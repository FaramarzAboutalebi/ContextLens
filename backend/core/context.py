"""Transcript context-window extraction for ContextLens."""

CONTEXT_SECONDS_BEFORE = 15
CONTEXT_SECONDS_AFTER = 15


def extract_context_by_time(
    transcript,
    start,
    end,
    seconds_before=CONTEXT_SECONDS_BEFORE,
    seconds_after=CONTEXT_SECONDS_AFTER,
):
    """Extract words before, during, and after a matched time range."""
    context_start = max(0, start - seconds_before)
    last_word_end = max(
        (
            word["end"]
            for segment in transcript
            for word in segment["words"]
        ),
        default=end,
    )
    context_end = min(end + seconds_after, last_word_end)

    before = []
    during = []
    after = []

    for segment in transcript:
        for word in segment["words"]:
            if word["end"] <= context_start or word["start"] >= context_end:
                continue

            item = {
                "word": word["word"],
                "start": word["start"],
                "end": word["end"],
            }

            if item["end"] <= start:
                before.append(item)
            elif item["start"] >= end:
                after.append(item)
            else:
                during.append(item)

    def join_words(items):
        return " ".join(item["word"] for item in items)

    return {
        "before": join_words(before),
        "during": join_words(during),
        "after": join_words(after),
        "word_timestamps": {
            "before": before,
            "during": during,
            "after": after,
        },
        "window": {
            "start": round(context_start, 2),
            "end": round(context_end, 2),
            "seconds_before": seconds_before,
            "seconds_after": seconds_after,
        },
    }
