"""DynamoDB persistence with idempotent state transitions."""

from __future__ import annotations

import json
import time
from decimal import Decimal

from .config import (
    processing_lease_seconds,
    rate_limit_global_day,
    rate_limit_global_hour,
    rate_limit_per_client_hour,
    table_name,
)

CREATED = "CREATED"
UPLOADING = "UPLOADING"
QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
TERMINAL_STATES = {COMPLETED, FAILED}


def _table():
    import boto3

    return boto3.resource("dynamodb").Table(table_name())


def to_dynamodb(value):
    return json.loads(json.dumps(value), parse_float=Decimal)


def from_dynamodb(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, list):
        return [from_dynamodb(item) for item in value]
    if isinstance(value, dict):
        return {key: from_dynamodb(item) for key, item in value.items()}
    return value


def create_job(item: dict, table=None) -> None:
    (table or _table()).put_item(
        Item=to_dynamodb(item),
        ConditionExpression="attribute_not_exists(fact_check_id)",
    )


def get_job(fact_check_id: str, table=None) -> dict | None:
    response = (table or _table()).get_item(
        Key={"fact_check_id": fact_check_id},
        ConsistentRead=True,
    )
    item = response.get("Item")
    if not item or item.get("item_type") == "rate_limit":
        return None
    return from_dynamodb(item)


def _increment_counter(
    target,
    *,
    key: str,
    attribute: str,
    limit: int,
    expires_at: int,
) -> bool:
    try:
        target.update_item(
            Key={"fact_check_id": key},
            UpdateExpression=(
                "SET #counter = if_not_exists(#counter, :zero) + :one, "
                "expires_at = :expires, item_type = :item_type"
            ),
            ConditionExpression="attribute_not_exists(#counter) OR #counter < :limit",
            ExpressionAttributeNames={"#counter": attribute},
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":limit": limit,
                ":expires": expires_at,
                ":item_type": "rate_limit",
            },
        )
        return True
    except Exception as error:
        if _conditional_failure(error):
            return False
        raise


def consume_creation_quota(
    client_hash: str,
    *,
    now_epoch: int | None = None,
    table=None,
) -> tuple[bool, int, str | None]:
    """Atomically enforce client/hour plus global hour/day creation budgets.

    The client counter is consumed first. If a global limit is already full, that client may lose
    one slot for the current hour; this conservative failure mode never creates an extra job.
    """
    target = table or _table()
    now_epoch = int(time.time()) if now_epoch is None else now_epoch
    hour_bucket = now_epoch // 3600
    day_bucket = now_epoch // 86400
    hour_end = (hour_bucket + 1) * 3600
    day_end = (day_bucket + 1) * 86400

    if not _increment_counter(
        target,
        key=f"rate#client#{client_hash}#{hour_bucket}",
        attribute="request_count",
        limit=rate_limit_per_client_hour(),
        expires_at=hour_end + 3600,
    ):
        return False, max(1, hour_end - now_epoch), "client_hour"

    try:
        target.update_item(
            Key={"fact_check_id": f"rate#global#{day_bucket}"},
            UpdateExpression=(
                "SET #hour = if_not_exists(#hour, :zero) + :one, "
                "#day = if_not_exists(#day, :zero) + :one, "
                "expires_at = :expires, item_type = :item_type"
            ),
            ConditionExpression=(
                "(attribute_not_exists(#hour) OR #hour < :hour_limit) AND "
                "(attribute_not_exists(#day) OR #day < :day_limit)"
            ),
            ExpressionAttributeNames={
                "#hour": f"hour_{hour_bucket % 24}",
                "#day": "day_count",
            },
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":hour_limit": rate_limit_global_hour(),
                ":day_limit": rate_limit_global_day(),
                ":expires": day_end + 86400,
                ":item_type": "rate_limit",
            },
        )
        return True, 0, None
    except Exception as error:
        if not _conditional_failure(error):
            raise
        return False, max(1, hour_end - now_epoch), "global"


def queue_created_job(fact_check_id: str, updated_at: str, table=None) -> None:
    (table or _table()).update_item(
        Key={"fact_check_id": fact_check_id},
        UpdateExpression="SET #status = :queued, updated_at = :updated",
        ConditionExpression="#status = :created",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":created": CREATED,
            ":queued": QUEUED,
            ":updated": updated_at,
        },
    )


def queue_uploaded_job(fact_check_id: str, updated_at: str, table=None) -> tuple[dict | None, bool]:
    target = table or _table()
    try:
        response = target.update_item(
            Key={"fact_check_id": fact_check_id},
            UpdateExpression="SET #status = :queued, updated_at = :updated",
            ConditionExpression="#status = :uploading",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":uploading": UPLOADING,
                ":queued": QUEUED,
                ":updated": updated_at,
            },
            ReturnValues="ALL_NEW",
        )
        return from_dynamodb(response["Attributes"]), True
    except Exception as error:
        if not _conditional_failure(error):
            raise
        return get_job(fact_check_id, table=target), False


def claim_processing(fact_check_id: str, updated_at: str, now_epoch: int | None = None, table=None) -> bool:
    target = table or _table()
    now_epoch = int(time.time()) if now_epoch is None else now_epoch
    try:
        target.update_item(
            Key={"fact_check_id": fact_check_id},
            UpdateExpression=(
                "SET #status = :processing, updated_at = :updated, "
                "processing_lease_until = :lease"
            ),
            ConditionExpression=(
                "#status = :queued OR "
                "(#status = :processing AND processing_lease_until < :now)"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":queued": QUEUED,
                ":processing": PROCESSING,
                ":updated": updated_at,
                ":now": now_epoch,
                ":lease": now_epoch + processing_lease_seconds(),
            },
        )
        return True
    except Exception as error:
        if _conditional_failure(error):
            return False
        raise


def save_result(fact_check_id: str, result: dict, updated_at: str, table=None) -> None:
    (table or _table()).update_item(
        Key={"fact_check_id": fact_check_id},
        UpdateExpression=(
            "SET #status = :completed, updated_at = :updated, #result = :result "
            "REMOVE #error, processing_lease_until"
        ),
        ConditionExpression="#status = :processing",
        ExpressionAttributeNames={"#status": "status", "#result": "result", "#error": "error"},
        ExpressionAttributeValues={
            ":processing": PROCESSING,
            ":completed": COMPLETED,
            ":updated": updated_at,
            ":result": to_dynamodb(result),
        },
    )


def release_for_retry(fact_check_id: str, updated_at: str, table=None) -> None:
    (table or _table()).update_item(
        Key={"fact_check_id": fact_check_id},
        UpdateExpression=(
            "SET #status = :queued, updated_at = :updated "
            "REMOVE processing_lease_until"
        ),
        ConditionExpression="#status = :processing",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":processing": PROCESSING,
            ":queued": QUEUED,
            ":updated": updated_at,
        },
    )


def mark_failed(fact_check_id: str, error: dict, updated_at: str, table=None) -> None:
    (table or _table()).update_item(
        Key={"fact_check_id": fact_check_id},
        UpdateExpression=(
            "SET #status = :failed, updated_at = :updated, #error = :error "
            "REMOVE processing_lease_until"
        ),
        ConditionExpression="#status = :processing",
        ExpressionAttributeNames={"#status": "status", "#error": "error"},
        ExpressionAttributeValues={
            ":processing": PROCESSING,
            ":failed": FAILED,
            ":updated": updated_at,
            ":error": error,
        },
    )


def _conditional_failure(error: Exception) -> bool:
    response = getattr(error, "response", {})
    return response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"
