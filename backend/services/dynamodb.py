"""DynamoDB persistence and idempotent state transitions."""

import json
from decimal import Decimal

from settings import table_name

AWAITING_UPLOADS = "AWAITING_UPLOADS"
QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
COMPLETE = "COMPLETE"
FAILED = "FAILED"


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


def create_analysis(item, table=None):
    target = table or _table()
    target.put_item(
        Item=to_dynamodb(item),
        ConditionExpression="attribute_not_exists(analysis_id)",
    )
    return item


def get_analysis(analysis_id, table=None):
    target = table or _table()
    response = target.get_item(
        Key={"analysis_id": analysis_id},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return from_dynamodb(item) if item else None


def queue_analysis(analysis_id, updated_at, table=None):
    target = table or _table()
    try:
        response = target.update_item(
            Key={"analysis_id": analysis_id},
            UpdateExpression="SET #state = :queued, updated_at = :updated",
            ConditionExpression="#state = :awaiting",
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues={
                ":queued": QUEUED,
                ":awaiting": AWAITING_UPLOADS,
                ":updated": updated_at,
            },
            ReturnValues="ALL_NEW",
        )
        return from_dynamodb(response["Attributes"]), True
    except Exception as error:
        if not _is_conditional_failure(error):
            raise
        return get_analysis(analysis_id, table=target), False


def claim_processing(analysis_id, updated_at, table=None):
    target = table or _table()
    try:
        target.update_item(
            Key={"analysis_id": analysis_id},
            UpdateExpression="SET #state = :processing, updated_at = :updated",
            ConditionExpression="#state = :queued",
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues={
                ":queued": QUEUED,
                ":processing": PROCESSING,
                ":updated": updated_at,
            },
        )
        return True
    except Exception as error:
        if _is_conditional_failure(error):
            return False
        raise


def save_result(analysis_id, result, updated_at, table=None):
    target = table or _table()
    target.update_item(
        Key={"analysis_id": analysis_id},
        UpdateExpression=(
            "SET #state = :complete, updated_at = :updated, #result = :result "
            "REMOVE failure"
        ),
        ConditionExpression="#state = :processing",
        ExpressionAttributeNames={"#state": "state", "#result": "result"},
        ExpressionAttributeValues={
            ":processing": PROCESSING,
            ":complete": COMPLETE,
            ":updated": updated_at,
            ":result": to_dynamodb(result),
        },
    )


def release_for_retry(analysis_id, updated_at, table=None):
    target = table or _table()
    target.update_item(
        Key={"analysis_id": analysis_id},
        UpdateExpression="SET #state = :queued, updated_at = :updated",
        ConditionExpression="#state = :processing",
        ExpressionAttributeNames={"#state": "state"},
        ExpressionAttributeValues={
            ":processing": PROCESSING,
            ":queued": QUEUED,
            ":updated": updated_at,
        },
    )


def mark_failed(analysis_id, message, updated_at, table=None):
    target = table or _table()
    target.update_item(
        Key={"analysis_id": analysis_id},
        UpdateExpression="SET #state = :failed, updated_at = :updated, failure = :failure",
        ConditionExpression="#state = :processing",
        ExpressionAttributeNames={"#state": "state"},
        ExpressionAttributeValues={
            ":processing": PROCESSING,
            ":failed": FAILED,
            ":updated": updated_at,
            ":failure": message,
        },
    )


def _is_conditional_failure(error):
    response = getattr(error, "response", {})
    return response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"
