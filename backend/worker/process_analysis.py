"""SQS-triggered Lambda worker for ContextLens video analysis."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.analyzer import analyze_context
from core.contract import validate_analysis_result
from services import dynamodb, s3
from settings import gemini_secret_arn

MAX_RECEIVES = 2


def _now():
    return datetime.now(timezone.utc).isoformat()


def _secrets_client():
    import boto3

    return boto3.client("secretsmanager")


def load_gemini_api_key(client=None):
    secret_arn = gemini_secret_arn()
    if not secret_arn:
        return None

    secrets = client or _secrets_client()
    secret_value = secrets.get_secret_value(SecretId=secret_arn).get("SecretString", "")
    if not secret_value:
        return None

    try:
        parsed = json.loads(secret_value)
    except json.JSONDecodeError:
        return secret_value

    if isinstance(parsed, dict):
        return parsed.get("GEMINI_API_KEY")
    return None


def process_message(message, gemini_api_key=None):
    analysis_id = message["analysis_id"]
    claimed = dynamodb.claim_processing(analysis_id, _now())
    if not claimed:
        return False

    with tempfile.TemporaryDirectory(prefix=f"contextlens-worker-{analysis_id}-") as work_dir:
        original_path = Path(work_dir) / "original.mp4"
        clip_path = Path(work_dir) / "clip.mp4"
        s3.download_file(message["original_key"], original_path)
        s3.download_file(message["clip_key"], clip_path)

        result = analyze_context(
            str(original_path),
            str(clip_path),
            use_ai=bool(message.get("use_ai", True)),
            analysis_id=analysis_id,
            gemini_api_key=gemini_api_key,
        )
        validate_analysis_result(result)
        dynamodb.save_result(analysis_id, result, _now())
        return True


def lambda_handler(event, _context):
    failures = []
    gemini_api_key = None

    try:
        gemini_api_key = load_gemini_api_key()
    except Exception as error:
        print("Gemini secret unavailable:", type(error).__name__)

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")
        analysis_id = None
        try:
            message = json.loads(record["body"])
            analysis_id = message.get("analysis_id")
            if not analysis_id:
                raise ValueError("SQS message is missing analysis_id.")
            process_message(message, gemini_api_key=gemini_api_key)
        except Exception as error:
            print("Analysis worker failed:", type(error).__name__)
            receive_count = int(
                record.get("attributes", {}).get("ApproximateReceiveCount", "1")
            )
            if analysis_id:
                try:
                    if receive_count >= MAX_RECEIVES:
                        dynamodb.mark_failed(
                            analysis_id,
                            "Processing failed after retry.",
                            _now(),
                        )
                    else:
                        dynamodb.release_for_retry(analysis_id, _now())
                except Exception as state_error:
                    print("Worker state update failed:", type(state_error).__name__)
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
