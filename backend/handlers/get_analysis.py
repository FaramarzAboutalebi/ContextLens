"""Retrieve operational state and final ContextLens results."""

from http_utils import json_response
from services import dynamodb


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
        if item["state"] == dynamodb.FAILED:
            payload["error"] = "Analysis processing failed. Please try again."
        return json_response(200, payload)
    except Exception as error:
        print("Get analysis request failed:", type(error).__name__)
        return json_response(500, {"error": "The request could not be completed."})
