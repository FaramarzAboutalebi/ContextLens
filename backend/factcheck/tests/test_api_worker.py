import json
import os
import unittest
from unittest.mock import Mock, patch

from factcheck import api, repository, worker
from factcheck.errors import FactCheckError, INSTAGRAM_DOWNLOAD_FAILED


class ApiTests(unittest.TestCase):
    @patch("factcheck.api.repository.consume_creation_quota", return_value=(False, 120, "client_hour"))
    def test_creation_rate_limit_returns_429_without_creating_job(self, consume):
        event = {
            "routeKey": "POST /fact-checks",
            "requestContext": {"http": {"sourceIp": "203.0.113.10"}},
            "body": json.dumps(
                {
                    "source": {
                        "type": "manual_upload",
                        "filename": "video.mp4",
                        "content_type": "video/mp4",
                    }
                }
            ),
        }
        result = api.lambda_handler(event, None)
        payload = json.loads(result["body"])
        self.assertEqual(result["statusCode"], 429)
        self.assertEqual(result["headers"]["Retry-After"], "120")
        self.assertEqual(payload["error"]["code"], "RATE_LIMITED")
        consume.assert_called_once()

    @patch("factcheck.api.repository.create_job")
    @patch("factcheck.api.repository.queue_created_job")
    def test_url_mode_queues_immediately(self, queue_job, create_job):
        sqs = Mock()
        with patch.dict(os.environ, {"FACTCHECK_QUEUE_URL": "queue", "JOB_TTL_SECONDS": "3600"}, clear=False):
            result = api.create_fact_check(
                {"source": {"type": "instagram_url", "url": "https://www.instagram.com/reel/DePHLhtON_i/"}},
                sqs_client=sqs,
            )
        payload = json.loads(result["body"])
        self.assertEqual(result["statusCode"], 202)
        self.assertEqual(payload["status"], repository.QUEUED)
        create_job.assert_called_once()
        queue_job.assert_called_once()
        sqs.send_message.assert_called_once()

    @patch(
        "factcheck.api.storage.create_upload_form",
        return_value={"url": "https://upload.example/signed", "fields": {"key": "value"}},
    )
    @patch("factcheck.api.repository.create_job")
    def test_manual_mode_returns_one_presigned_upload(self, create_job, create_url):
        with patch.dict(os.environ, {"JOB_TTL_SECONDS": "3600", "UPLOAD_URL_TTL_SECONDS": "900"}, clear=False):
            result = api.create_fact_check(
                {"source": {"type": "manual_upload", "filename": "video.mp4", "content_type": "video/mp4"}}
            )
        payload = json.loads(result["body"])
        self.assertEqual(result["statusCode"], 201)
        self.assertEqual(payload["status"], repository.UPLOADING)
        self.assertEqual(payload["upload"]["method"], "POST")
        self.assertEqual(payload["upload"]["fields"], {"key": "value"})

    @patch("factcheck.api.repository.queue_uploaded_job")
    @patch("factcheck.api.storage.validate_uploaded_object")
    @patch("factcheck.api.repository.get_job")
    def test_duplicate_completion_does_not_duplicate_queue_message(self, get_job, validate, queue_job):
        item = {"source_type": "manual_upload", "status": repository.UPLOADING, "object_key": "key"}
        get_job.return_value = item
        queue_job.return_value = ({**item, "status": repository.QUEUED}, False)
        sqs = Mock()
        result = api.complete_upload("id", sqs_client=sqs)
        self.assertEqual(result["statusCode"], 202)
        sqs.send_message.assert_not_called()


class WorkerTests(unittest.TestCase):
    @patch("factcheck.worker.repository.save_result")
    @patch("factcheck.worker.review_claims")
    @patch("factcheck.worker.extract_claims")
    @patch("factcheck.worker.transcribe_video")
    @patch("factcheck.worker.verify_media_integrity")
    @patch("factcheck.worker.probe_media")
    @patch("factcheck.worker._prepare_source")
    @patch("factcheck.worker.repository.get_job")
    @patch("factcheck.worker.repository.claim_processing", return_value=True)
    def test_successful_manual_job_saves_versioned_result(
        self,
        claim,
        get_job,
        prepare,
        probe,
        verify,
        transcribe,
        extract,
        review,
        save,
    ):
        get_job.return_value = {"fact_check_id": "id", "source_type": "manual_upload", "object_key": "key"}
        prepare.return_value = (Mock(), {"type": "manual_upload"})
        probe.return_value = {"duration_seconds": 10.0}
        transcribe.return_value = {"text": "The claim.", "segments": [{"start": 0.0, "end": 1.0, "text": "The claim."}]}
        extracted = [{"claim_id": "claim-1", "text": "The claim.", "timestamp_seconds": 0.0, "excerpt": "The claim."}]
        extract.return_value = {
            "claims": extracted,
            "content_items": [],
            "total_factual_claims_identified": 1,
        }
        review.return_value = ([{**extracted[0], "assessment": "SUPPORTED", "explanation": "Evidence.", "sources": [], "limitations": []}], "SUCCESS")
        self.assertTrue(worker.process_message({"fact_check_id": "id"}, api_key="key"))
        result = save.call_args.args[1]
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["review"]["status"], "SUCCESS")
        self.assertEqual(result["review"]["summary"]["verdict"], "MOSTLY_SUPPORTED")

    @patch("factcheck.worker.repository.get_job")
    @patch("factcheck.worker.repository.claim_processing", return_value=False)
    def test_duplicate_sqs_delivery_is_acknowledged(self, claim, get_job):
        self.assertFalse(worker.process_message({"fact_check_id": "id"}, api_key="key"))
        get_job.assert_not_called()

    @patch("factcheck.worker.repository.mark_failed")
    @patch("factcheck.worker.process_message")
    @patch("factcheck.worker.load_gemini_api_key", return_value="key")
    def test_deterministic_media_failure_is_not_retried(self, load_key, process, mark_failed):
        process.side_effect = FactCheckError(INSTAGRAM_DOWNLOAD_FAILED, "Use upload.")
        result = worker.lambda_handler(
            {"Records": [{"messageId": "m1", "body": json.dumps({"fact_check_id": "id"}), "attributes": {"ApproximateReceiveCount": "1"}}]},
            None,
        )
        self.assertEqual(result, {"batchItemFailures": []})
        mark_failed.assert_called_once()

    @patch("factcheck.worker.repository.release_for_retry")
    @patch("factcheck.worker.process_message", side_effect=RuntimeError("transient"))
    @patch("factcheck.worker.load_gemini_api_key", return_value="key")
    def test_transient_failure_is_retried_once(self, load_key, process, release):
        result = worker.lambda_handler(
            {"Records": [{"messageId": "m1", "body": json.dumps({"fact_check_id": "id"}), "attributes": {"ApproximateReceiveCount": "1"}}]},
            None,
        )
        self.assertEqual(result["batchItemFailures"], [{"itemIdentifier": "m1"}])
        release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
