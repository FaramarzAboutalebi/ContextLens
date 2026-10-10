"""Create analyses, issue upload URLs, and queue completed uploads."""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from http_utils import json_response, parse_json_body
from services import dynamodb, s3
from settings import (
    ALLOWED_CONTENT_TYPES,
    analysis_ttl_seconds,
    queue_url,
    upload_url_ttl_seconds,
)


def _sqs_client():
    import boto3

    return boto3.client("sqs")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _validate_video_descriptor(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    filename = value.get("filename")
    content_type = value.get("content_type")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError(f"{label}.filename is required.")
    if Path(filename).suffix.lower() != ".mp4":
        raise ValueError(f"{label} must be an MP4 file.")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"{label}.content_type must be video/mp4.")
    return {"filename": Path(filename).name, "content_type": content_type}


def create_analysis(body):
    original = _validate_video_descriptor(body.get("original"), "original")
    clip = _validate_video_descriptor(body.get("clip"), "clip")
    use_ai = body.get("use_ai", True)
    if not isinstance(use_ai, bool):
        raise ValueError("use_ai must be a boolean.")

    analysis_id = str(uuid.uuid4())
    created_at = _now()
    keys = s3.object_keys(analysis_id)
    item = {
        "analysis_id": analysis_id,
        "state": dynamodb.AWAITING_UPLOADS,
        "created_at": created_at,
        "updated_at": created_at,
        "expires_at": int(time.time()) + analysis_ttl_seconds(),
        "original_key": keys["original"],
        "clip_key": keys["clip"],
        "use_ai": use_ai,
        "result": None,
    }
    dynamodb.create_analysis(item)

    expires_in = upload_url_ttl_seconds()
    upload_headers = {
        "Content-Type": "video/mp4",
        "x-amz-server-side-encryption": "AES256",
    }
    uploads = {
        "original": {
            "url": s3.create_upload_url(
                keys["original"], original["content_type"], expires_in
            ),
            "method": "PUT",
            "headers": upload_headers,
        },
        "clip": {
            "url": s3.create_upload_url(
                keys["clip"], clip["content_type"], expires_in
            ),
            "method": "PUT",
            "headers": upload_headers,
        },
    }
    return json_response(
        201,
        {
            "analysis_id": analysis_id,
            "state": dynamodb.AWAITING_UPLOADS,
            "uploads": uploads,
            "expires_in": expires_in,
        },
    )


def complete_analysis(analysis_id, sqs_client=None):
    item = dynamodb.get_analysis(analysis_id)
    if item is None:
        return json_response(404, {"error": "Analysis not found."})
    if item["state"] in {dynamodb.PROCESSING, dynamodb.COMPLETE, dynamodb.FAILED}:
        return json_response(202, {"analysis_id": analysis_id, "state": item["state"]})

    try:
        s3.validate_uploaded_object(item["original_key"])
        s3.validate_uploaded_object(item["clip_key"])
    except ValueError as error:
        return json_response(400, {"error": str(error)})
    except Exception as error:
        if _is_missing_object(error):
            return json_response(409, {"error": "Both video uploads must complete first."})
        raise

    queued_item, _ = dynamodb.queue_analysis(analysis_id, _now())
    if queued_item is None:
        return json_response(404, {"error": "Analysis not found."})
    if queued_item["state"] not in {dynamodb.QUEUED, dynamodb.PROCESSING}:
        return json_response(
            202, {"analysis_id": analysis_id, "state": queued_item["state"]}
        )

    message = {
        "analysis_id": analysis_id,
        "original_key": item["original_key"],
        "clip_key": item["clip_key"],
        "use_ai": bool(item.get("use_ai", True)),
    }
    sqs = sqs_client or _sqs_client()
    sqs.send_message(QueueUrl=queue_url(), MessageBody=json.dumps(message))
    return json_response(202, {"analysis_id": analysis_id, "state": queued_item["state"]})


def lambda_handler(event, _context):
    try:
        route_key = event.get("routeKey", "")
        raw_path = event.get("rawPath", "")
        if route_key == "POST /analyses" or raw_path.rstrip("/") == "/analyses":
            return create_analysis(parse_json_body(event))
        if route_key == "POST /analyses/{analysis_id}/complete" or raw_path.endswith(
            "/complete"
        ):
            analysis_id = (event.get("pathParameters") or {}).get("analysis_id")
            if not analysis_id:
                return json_response(400, {"error": "analysis_id is required."})
            return complete_analysis(analysis_id)
        return json_response(404, {"error": "Route not found."})
    except (ValueError, json.JSONDecodeError) as error:
        return json_response(400, {"error": str(error)})
    except Exception as error:
        print("Create analysis request failed:", type(error).__name__)
        return json_response(500, {"error": "The request could not be completed."})


def _is_missing_object(error):
    response = getattr(error, "response", {})
    return str(response.get("Error", {}).get("Code")) in {"404", "NoSuchKey", "NotFound"}
