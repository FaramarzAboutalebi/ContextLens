"""Minimal HTTP API response helpers."""

from __future__ import annotations

import base64
import json


def response(status_code: int, body: dict, headers: dict | None = None) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", **(headers or {})},
        "body": json.dumps(body),
    }


def parse_body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object.")
    return parsed
