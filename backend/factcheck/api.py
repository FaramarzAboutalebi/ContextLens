"""Independent HTTP API handler for fact-check jobs."""

from __future__ import annotations

import json
import hashlib
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import repository, storage
from .config import job_ttl_seconds, queue_url, upload_url_ttl_seconds
from .errors import FactCheckError, INVALID_INSTAGRAM_URL, RateLimitError
from .http import parse_body, response
from .url_validation import normalize_instagram_reel_url


def _sqs_client():
    import boto3

    return boto3.client("sqs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enqueue(message: dict, sqs_client=None) -> None:
    (sqs_client or _sqs_client()).send_message(
        QueueUrl=queue_url(),
        MessageBody=json.dumps(message),
    )


def _validate_upload_request(source: dict) -> None:
    filename = source.get("filename")
    content_type = source.get("content_type")
    if not isinstance(filename, str) or Path(filename).suffix.lower() != ".mp4":
        raise ValueError("A .mp4 filename is required for manual upload.")
    if content_type != storage.CONTENT_TYPE:
        raise ValueError("Manual uploads must use video/mp4.")


def _client_hash(event: dict) -> str:
    source_ip = str(
        ((event.get("requestContext") or {}).get("http") or {}).get("sourceIp")
        or "unknown"
    )
    return hashlib.sha256(source_ip.encode("utf-8")).hexdigest()[:32]


def _consume_creation_quota(client_hash: str | None) -> None:
    if not client_hash:
        return
    allowed, retry_after, _scope = repository.consume_creation_quota(client_hash)
    if not allowed:
        raise RateLimitError(retry_after)


def create_fact_check(body: dict, sqs_client=None, client_hash: str | None = None) -> dict:
    source = body.get("source")
    if not isinstance(source, dict):
        raise ValueError("source must be an object.")
    source_type = source.get("type")
    fact_check_id = str(uuid.uuid4())
    now = _now()
    base_item = {
        "fact_check_id": fact_check_id,
        "schema_version": "1.0",
        "created_at": now,
        "updated_at": now,
        "expires_at": int(time.time()) + job_ttl_seconds(),
        "result": None,
        "error": None,
    }

    if source_type == "instagram_url":
        normalized_url = normalize_instagram_reel_url(source.get("url"))
        _consume_creation_quota(client_hash)
        item = {
            **base_item,
            "status": repository.CREATED,
            "source_type": source_type,
            "source_url": normalized_url,
        }
        repository.create_job(item)
        repository.queue_created_job(fact_check_id, _now())
        try:
            _enqueue({"fact_check_id": fact_check_id}, sqs_client=sqs_client)
        except Exception:
            # The record intentionally remains QUEUED for an operator-safe retry.
            raise
        return response(202, {"fact_check_id": fact_check_id, "status": repository.QUEUED})

    if source_type == "manual_upload":
        _validate_upload_request(source)
        _consume_creation_quota(client_hash)
        key = storage.object_key(fact_check_id)
        item = {
            **base_item,
            "status": repository.UPLOADING,
            "source_type": source_type,
            "object_key": key,
        }
        repository.create_job(item)
        expires_in = upload_url_ttl_seconds()
        signed_form = storage.create_upload_form(key, expires_in)
        upload = {
            "url": signed_form["url"],
            "method": "POST",
            "fields": signed_form["fields"],
        }
        return response(
            201,
            {
                "fact_check_id": fact_check_id,
                "status": repository.UPLOADING,
                "upload": upload,
                "expires_in": expires_in,
            },
        )
    raise FactCheckError(INVALID_INSTAGRAM_URL, "source.type must be instagram_url or manual_upload.")


def complete_upload(fact_check_id: str, sqs_client=None) -> dict:
    item = repository.get_job(fact_check_id)
    if item is None:
        return response(404, {"error": {"code": "NOT_FOUND", "message": "Fact-check job not found."}})
    if item.get("source_type") != "manual_upload":
        return response(409, {"error": {"code": "INVALID_STATE", "message": "Completion applies only to manual uploads."}})
    if item["status"] != repository.UPLOADING:
        return response(202, {"fact_check_id": fact_check_id, "status": item["status"]})
    storage.validate_uploaded_object(item["object_key"])
    queued, changed = repository.queue_uploaded_job(fact_check_id, _now())
    if changed:
        _enqueue({"fact_check_id": fact_check_id}, sqs_client=sqs_client)
    return response(202, {"fact_check_id": fact_check_id, "status": queued["status"]})


def get_fact_check(fact_check_id: str) -> dict:
    item = repository.get_job(fact_check_id)
    if item is None:
        return response(404, {"error": {"code": "NOT_FOUND", "message": "Fact-check job not found."}})
    payload = {
        "fact_check_id": fact_check_id,
        "status": item["status"],
        "schema_version": item.get("schema_version", "1.0"),
        "result": item.get("result"),
        "error": item.get("error"),
    }
    return response(200, payload)


def lambda_handler(event, _context):
    try:
        route = event.get("routeKey", "")
        params = event.get("pathParameters") or {}
        if route == "POST /fact-checks":
            return create_fact_check(parse_body(event), client_hash=_client_hash(event))
        if route == "POST /fact-checks/{fact_check_id}/complete":
            fact_check_id = params.get("fact_check_id", "")
            return complete_upload(fact_check_id)
        if route == "GET /fact-checks/{fact_check_id}":
            fact_check_id = params.get("fact_check_id", "")
            return get_fact_check(fact_check_id)
        return response(404, {"error": {"code": "NOT_FOUND", "message": "Route not found."}})
    except RateLimitError as error:
        return response(
            429,
            {"error": {"code": error.code, "message": error.public_message}},
            headers={"Retry-After": str(error.retry_after_seconds)},
        )
    except (ValueError, json.JSONDecodeError, FactCheckError) as error:
        code = error.code if isinstance(error, FactCheckError) else "INVALID_REQUEST"
        message = error.public_message if isinstance(error, FactCheckError) else str(error)
        return response(400, {"error": {"code": code, "message": message}})
    except Exception as error:
        print("Fact-check API request failed:", type(error).__name__)
        return response(500, {"error": {"code": "INTERNAL_ERROR", "message": "The request could not be completed."}})
