"""SQS worker for isolated Instagram/manual-upload fact-check jobs."""

from __future__ import annotations

import json
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import repository, storage
from .config import gemini_model, gemini_secret_id, max_reviewed_claims
from .downloader import download_instagram_reel
from .errors import FactCheckError, PROCESSING_FAILED
from .gemini_review import extract_claims, review_claims
from .media import probe_media, verify_media_integrity
from .schemas import build_result, select_claims_for_review
from .transcription import transcribe_video

MAX_RECEIVES = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_gemini_api_key(client=None) -> str | None:
    secret_id = gemini_secret_id()
    if not secret_id:
        return None
    if client is None:
        import boto3

        client = boto3.client("secretsmanager")
    secret = client.get_secret_value(SecretId=secret_id).get("SecretString", "")
    if not secret:
        return None
    try:
        parsed = json.loads(secret)
    except json.JSONDecodeError:
        return secret
    return parsed.get("GEMINI_API_KEY") if isinstance(parsed, dict) else None


def _prepare_source(item: dict, work_dir: Path) -> tuple[Path, dict]:
    if item["source_type"] == "instagram_url":
        video_path, _metadata = download_instagram_reel(item["source_url"], work_dir)
        return video_path, {"type": "instagram_url", "url": item["source_url"]}
    video_path = work_dir / "source.mp4"
    storage.download_file(item["object_key"], video_path)
    return video_path, {"type": "manual_upload"}


def process_message(message: dict, api_key: str | None = None) -> bool:
    fact_check_id = message["fact_check_id"]
    if not repository.claim_processing(fact_check_id, _now(), int(time.time())):
        return False
    item = repository.get_job(fact_check_id)
    if not item:
        raise RuntimeError("Claimed fact-check job no longer exists.")

    with tempfile.TemporaryDirectory(prefix=f"contextlens-factcheck-{fact_check_id}-") as temp:
        work_dir = Path(temp)
        print("Fact-check stage: preparing source")
        video_path, source = _prepare_source(item, work_dir)
        print("Fact-check stage: validating media")
        media = probe_media(video_path)
        verify_media_integrity(video_path)
        if item["source_type"] == "instagram_url":
            storage.upload_file(video_path, storage.object_key(fact_check_id))

        print("Fact-check stage: transcription")
        transcript = transcribe_video(video_path, work_dir)
        transcript["duration_seconds"] = media["duration_seconds"]
        source["duration_seconds"] = media["duration_seconds"]

        print("Fact-check stage: claim review")
        if not api_key:
            claims = []
            unreviewed_claims = []
            content_items = []
            total_identified = 0
            review_status = "UNAVAILABLE"
            model = None
        else:
            extraction = extract_claims(transcript, media["duration_seconds"], api_key)
            identified_claims = extraction["claims"]
            total_identified = extraction["total_factual_claims_identified"]
            content_items = extraction["content_items"]
            review_limit = max_reviewed_claims()
            claims, unreviewed_claims = select_claims_for_review(
                identified_claims, review_limit
            )
            if not identified_claims:
                review_status = "NO_CHECKABLE_CLAIMS"
                model = gemini_model()
            else:
                claims, review_status = review_claims(claims, api_key)
                model = gemini_model()

        result = build_result(
            fact_check_id=fact_check_id,
            source=source,
            transcript=transcript,
            review_status=review_status,
            claims=claims,
            model=model,
            total_identified=total_identified,
            unreviewed_claims=unreviewed_claims,
            content_items=content_items,
        )
        repository.save_result(fact_check_id, result, _now())
        return True


def lambda_handler(event, _context):
    failures = []
    try:
        api_key = load_gemini_api_key()
    except Exception as error:
        print("Gemini secret unavailable:", type(error).__name__)
        api_key = None

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")
        fact_check_id = None
        try:
            message = json.loads(record["body"])
            fact_check_id = message.get("fact_check_id")
            if not fact_check_id:
                raise ValueError("SQS message is missing fact_check_id.")
            process_message(message, api_key=api_key)
        except FactCheckError as error:
            print("Fact-check rejected:", error.code)
            if fact_check_id:
                repository.mark_failed(
                    fact_check_id,
                    {"code": error.code, "message": error.public_message},
                    _now(),
                )
        except Exception as error:
            error_types = []
            current_error = error
            while current_error is not None and len(error_types) < 4:
                error_types.append(type(current_error).__name__)
                current_error = current_error.__cause__ or current_error.__context__
            print("Fact-check worker failed:", " <- ".join(error_types))
            frames = traceback.extract_tb(error.__traceback__)
            print(
                "Fact-check failure location:",
                " > ".join(
                    f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}"
                    for frame in frames[-6:]
                ),
            )
            receives = int(record.get("attributes", {}).get("ApproximateReceiveCount", "1"))
            if fact_check_id:
                try:
                    if receives >= MAX_RECEIVES:
                        repository.mark_failed(
                            fact_check_id,
                            {"code": PROCESSING_FAILED, "message": "Fact-check processing failed."},
                            _now(),
                        )
                    else:
                        repository.release_for_retry(fact_check_id, _now())
                except Exception as state_error:
                    print("Fact-check state update failed:", type(state_error).__name__)
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
