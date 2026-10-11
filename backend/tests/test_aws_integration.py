"""Mocked tests for the AWS-facing ContextLens backend."""

import json
import os
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from core.analyzer import build_frontend_response
from handlers import create_analysis, get_analysis
from services import dynamodb, s3
from worker import process_analysis


def valid_error_result(analysis_id="analysis-1"):
    return build_frontend_response(
        {
            "analysis_id": analysis_id,
            "created_at": "2026-10-10T00:00:00+00:00",
            "status": "ERROR",
            "clip_transcript": None,
            "original_duration": None,
            "clip_duration": None,
            "similarity": None,
            "second_best_similarity": None,
            "score_gap": None,
            "threshold": 80.0,
            "match": None,
            "context": None,
            "error": {"code": "TEST", "message": "Test result."},
        }
    )


class FakeS3Client:
    def __init__(self, metadata=None):
        self.metadata = metadata or {
            "ContentLength": 1024,
            "ContentType": "video/mp4",
        }
        self.presign_calls = []
        self.upload_calls = []

    def generate_presigned_url(self, operation, **kwargs):
        self.presign_calls.append((operation, kwargs))
        return "https://upload.example/presigned"

    def head_object(self, **_kwargs):
        return self.metadata

    def upload_file(self, *args, **kwargs):
        self.upload_calls.append((args, kwargs))


class S3ServiceTests(unittest.TestCase):
    def test_upload_url_signs_content_type_and_encryption(self):
        client = FakeS3Client()
        with patch.dict(os.environ, {"UPLOAD_BUCKET": "test-bucket"}, clear=False):
            url = s3.create_upload_url(
                "analyses/id/original.mp4",
                "video/mp4",
                900,
                client=client,
            )
        self.assertEqual(url, "https://upload.example/presigned")
        params = client.presign_calls[0][1]["Params"]
        self.assertEqual(params["ServerSideEncryption"], "AES256")
        self.assertEqual(params["ContentType"], "video/mp4")

    def test_playback_url_signs_private_object_for_inline_video(self):
        client = FakeS3Client()
        with patch.dict(os.environ, {"UPLOAD_BUCKET": "test-bucket"}, clear=False):
            url = s3.create_playback_url(
                "analyses/id/clip.mp4",
                3600,
                client=client,
            )
        self.assertEqual(url, "https://upload.example/presigned")
        operation, request = client.presign_calls[0]
        self.assertEqual(operation, "get_object")
        self.assertEqual(request["ExpiresIn"], 3600)
        self.assertEqual(request["HttpMethod"], "GET")
        self.assertEqual(request["Params"]["ResponseContentType"], "video/mp4")
        self.assertEqual(request["Params"]["ResponseContentDisposition"], "inline")

    def test_poster_url_signs_private_object_as_inline_jpeg(self):
        client = FakeS3Client()
        with patch.dict(os.environ, {"UPLOAD_BUCKET": "test-bucket"}, clear=False):
            url = s3.create_poster_url(
                "analyses/id/original-poster.jpg",
                3600,
                client=client,
            )
        self.assertEqual(url, "https://upload.example/presigned")
        operation, request = client.presign_calls[0]
        self.assertEqual(operation, "get_object")
        self.assertEqual(request["Params"]["ResponseContentType"], "image/jpeg")

    def test_poster_upload_is_private_encrypted_jpeg(self):
        client = FakeS3Client()
        with patch.dict(os.environ, {"UPLOAD_BUCKET": "test-bucket"}, clear=False):
            s3.upload_poster(
                "analyses/id/original-poster.jpg",
                "/tmp/poster.jpg",
                client=client,
            )
        args, kwargs = client.upload_calls[0]
        self.assertEqual(args[1], "test-bucket")
        self.assertEqual(kwargs["ExtraArgs"]["ContentType"], "image/jpeg")
        self.assertEqual(kwargs["ExtraArgs"]["ServerSideEncryption"], "AES256")

    def test_object_exists_uses_private_head_request(self):
        client = FakeS3Client()
        with patch.dict(os.environ, {"UPLOAD_BUCKET": "test-bucket"}, clear=False):
            exists = s3.object_exists(
                "analyses/id/original-poster.jpg",
                client=client,
            )
        self.assertTrue(exists)

    def test_upload_validation_rejects_oversized_file(self):
        client = FakeS3Client({"ContentLength": 101, "ContentType": "video/mp4"})
        with patch.dict(
            os.environ,
            {"UPLOAD_BUCKET": "test-bucket", "MAX_UPLOAD_BYTES": "100"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "size limit"):
                s3.validate_uploaded_object("key", client=client)


class DynamoServiceTests(unittest.TestCase):
    def test_numbers_round_trip_through_decimal(self):
        encoded = dynamodb.to_dynamodb({"score": 53.79, "count": 16})
        self.assertIsInstance(encoded["score"], Decimal)
        self.assertEqual(dynamodb.from_dynamodb(encoded), {"score": 53.79, "count": 16})


class HandlerTests(unittest.TestCase):
    @patch("handlers.create_analysis.s3.create_upload_url")
    @patch("handlers.create_analysis.dynamodb.create_analysis")
    def test_create_returns_two_presigned_uploads(self, create_item, create_url):
        create_url.side_effect = ["https://upload/original", "https://upload/clip"]
        with patch.dict(
            os.environ,
            {
                "UPLOAD_URL_TTL_SECONDS": "900",
                "ANALYSIS_TTL_SECONDS": "3600",
            },
            clear=False,
        ):
            response = create_analysis.create_analysis(
                {
                    "original": {
                        "filename": "original.mp4",
                        "content_type": "video/mp4",
                    },
                    "clip": {
                        "filename": "clip.mp4",
                        "content_type": "video/mp4",
                    },
                    "use_ai": True,
                }
            )
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 201)
        self.assertEqual(body["state"], dynamodb.AWAITING_UPLOADS)
        self.assertEqual(set(body["uploads"]), {"original", "clip"})
        create_item.assert_called_once()

    @patch("handlers.create_analysis.dynamodb.queue_analysis")
    @patch("handlers.create_analysis.s3.validate_uploaded_object")
    @patch("handlers.create_analysis.dynamodb.get_analysis")
    def test_complete_queues_verified_uploads(self, get_item, validate, queue_item):
        item = {
            "analysis_id": "analysis-1",
            "state": dynamodb.AWAITING_UPLOADS,
            "original_key": "original-key",
            "clip_key": "clip-key",
            "use_ai": True,
        }
        get_item.return_value = item
        queue_item.return_value = ({**item, "state": dynamodb.QUEUED}, True)
        sqs = Mock()
        with patch.dict(os.environ, {"ANALYSIS_QUEUE_URL": "queue-url"}, clear=False):
            response = create_analysis.complete_analysis("analysis-1", sqs_client=sqs)
        self.assertEqual(response["statusCode"], 202)
        self.assertEqual(validate.call_count, 2)
        sqs.send_message.assert_called_once()

    @patch("handlers.get_analysis.s3.create_poster_url")
    @patch("handlers.get_analysis.s3.create_playback_url")
    @patch("handlers.get_analysis.dynamodb.get_analysis")
    def test_get_returns_polling_envelope_with_playback_media(
        self, get_item, create_playback_url, create_poster_url
    ):
        result = valid_error_result()
        get_item.return_value = {
            "analysis_id": "analysis-1",
            "state": dynamodb.COMPLETE,
            "result": result,
            "original_key": "analyses/analysis-1/original.mp4",
            "clip_key": "analyses/analysis-1/clip.mp4",
            "poster_keys": {
                "original": "analyses/analysis-1/original-poster.jpg",
                "clip": "analyses/analysis-1/clip-poster.jpg",
            },
        }
        create_playback_url.side_effect = [
            "https://media.example/original",
            "https://media.example/clip",
        ]
        create_poster_url.side_effect = [
            "https://media.example/original-poster",
            "https://media.example/clip-poster",
        ]
        with patch.dict(
            os.environ, {"PLAYBACK_URL_TTL_SECONDS": "3600"}, clear=False
        ):
            response = get_analysis.lambda_handler(
                {"pathParameters": {"analysis_id": "analysis-1"}}, None
            )
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["state"], dynamodb.COMPLETE)
        self.assertEqual(len(body["result"]), 15)
        self.assertEqual(body["media"]["clip"]["url"], "https://media.example/clip")
        self.assertEqual(body["media"]["original"]["expires_in"], 3600)
        self.assertEqual(
            body["media"]["original"]["poster_url"],
            "https://media.example/original-poster",
        )
        self.assertEqual(create_playback_url.call_count, 2)
        self.assertEqual(create_poster_url.call_count, 2)

    @patch("handlers.get_analysis.s3.create_poster_url")
    @patch("handlers.get_analysis.s3.object_exists")
    @patch("handlers.get_analysis.s3.create_playback_url")
    @patch("handlers.get_analysis.dynamodb.get_analysis")
    def test_get_discovers_backfilled_posters_for_older_analysis(
        self,
        get_item,
        create_playback_url,
        object_exists,
        create_poster_url,
    ):
        get_item.return_value = {
            "analysis_id": "analysis-1",
            "state": dynamodb.COMPLETE,
            "result": valid_error_result(),
            "original_key": "analyses/analysis-1/original.mp4",
            "clip_key": "analyses/analysis-1/clip.mp4",
        }
        create_playback_url.side_effect = ["original-video", "clip-video"]
        object_exists.side_effect = [True, True]
        create_poster_url.side_effect = ["original-poster", "clip-poster"]

        response = get_analysis.lambda_handler(
            {"pathParameters": {"analysis_id": "analysis-1"}}, None
        )
        body = json.loads(response["body"])

        self.assertEqual(body["media"]["original"]["poster_url"], "original-poster")
        self.assertEqual(body["media"]["clip"]["poster_url"], "clip-poster")
        self.assertEqual(object_exists.call_count, 2)


class WorkerTests(unittest.TestCase):
    @patch("worker.process_analysis.dynamodb.save_result")
    @patch("worker.process_analysis.create_posters")
    @patch("worker.process_analysis.analyze_context")
    @patch("worker.process_analysis.s3.download_file")
    @patch("worker.process_analysis.dynamodb.claim_processing")
    def test_worker_claims_validates_and_saves(
        self,
        claim,
        download,
        analyze,
        create_posters,
        save,
    ):
        claim.return_value = True
        download.side_effect = lambda _key, destination: destination.write_bytes(b"video")
        analyze.return_value = valid_error_result()
        create_posters.return_value = {
            "original": "analyses/analysis-1/original-poster.jpg",
            "clip": "analyses/analysis-1/clip-poster.jpg",
        }
        processed = process_analysis.process_message(
            {
                "analysis_id": "analysis-1",
                "original_key": "original-key",
                "clip_key": "clip-key",
                "use_ai": False,
            }
        )
        self.assertTrue(processed)
        self.assertEqual(download.call_count, 2)
        save.assert_called_once()
        saved_result = save.call_args.args[1]
        self.assertEqual(len(saved_result), 15)
        self.assertEqual(save.call_args.kwargs["poster_keys"], create_posters.return_value)

    @patch("worker.process_analysis.s3.download_file")
    @patch("worker.process_analysis.dynamodb.claim_processing")
    def test_duplicate_message_is_acknowledged_without_processing(self, claim, download):
        claim.return_value = False
        processed = process_analysis.process_message(
            {
                "analysis_id": "analysis-1",
                "original_key": "original-key",
                "clip_key": "clip-key",
            }
        )
        self.assertFalse(processed)
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
