"""Retrieve operational state and final ContextLens results."""

from http_utils import json_response
from services import dynamodb, s3
from settings import playback_url_ttl_seconds


def _playback_media(item):
    if item.get("state") != dynamodb.COMPLETE:
        return None

    original_key = item.get("original_key")
    clip_key = item.get("clip_key")
    if not original_key or not clip_key:
        return None

    expires_in = playback_url_ttl_seconds()
    media = {
        "original": {
            "url": s3.create_playback_url(original_key, expires_in),
            "content_type": "video/mp4",
            "expires_in": expires_in,
        },
        "clip": {
            "url": s3.create_playback_url(clip_key, expires_in),
            "content_type": "video/mp4",
            "expires_in": expires_in,
        },
    }
    poster_keys = item.get("poster_keys") or {}
    if not poster_keys and item.get("analysis_id"):
        candidate_keys = s3.object_keys(item["analysis_id"])
        poster_keys = {
            name: candidate_keys[f"{name}_poster"]
            for name in ("original", "clip")
            if s3.object_exists(candidate_keys[f"{name}_poster"])
        }

    for name, poster_key in poster_keys.items():
        if name in media and poster_key:
            media[name]["poster_url"] = s3.create_poster_url(
                poster_key,
                expires_in,
            )
    return media


def lambda_handler(event, _context):
    try:
        analysis_id = (event.get("pathParameters") or {}).get("analysis_id")
        if not analysis_id:
            return json_response(400, {"error": "analysis_id is required."})
        item = dynamodb.get_analysis(analysis_id)
        if item is None:
            return json_response(404, {"error": "Analysis not found."})

        payload = {
            "analysis_id": analysis_id,
            "state": item["state"],
            "result": item.get("result"),
        }
        try:
            media = _playback_media(item)
            if media:
                payload["media"] = media
        except Exception as error:
            # Playback is supplementary; never hide a completed analysis if URL
            # signing is temporarily unavailable.
            print("Playback URL generation failed:", type(error).__name__)
        if item["state"] == dynamodb.FAILED:
            payload["error"] = "Analysis processing failed. Please try again."
        return json_response(200, payload)
    except Exception as error:
        print("Get analysis request failed:", type(error).__name__)
        return json_response(500, {"error": "The request could not be completed."})
