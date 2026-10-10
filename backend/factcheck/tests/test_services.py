import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from factcheck import repository, storage
from factcheck.downloader import _validate_extracted_network_urls
from factcheck.errors import FactCheckError, INSTAGRAM_DOWNLOAD_FAILED
from factcheck.transcription import transcribe_video


class StorageTests(unittest.TestCase):
    def test_presigned_post_enforces_size_type_and_encryption(self):
        client = Mock()
        client.generate_presigned_post.return_value = {"url": "https://upload", "fields": {}}
        with patch.dict(
            os.environ,
            {"FACTCHECK_BUCKET": "bucket", "MAX_MEDIA_BYTES": "100"},
            clear=False,
        ):
            storage.create_upload_form("key", 900, client=client)
        kwargs = client.generate_presigned_post.call_args.kwargs
        self.assertIn(["content-length-range", 1, 100], kwargs["Conditions"])
        self.assertEqual(kwargs["Fields"]["Content-Type"], "video/mp4")
        self.assertEqual(kwargs["Fields"]["x-amz-server-side-encryption"], "AES256")

    def test_uploaded_object_size_is_checked_again(self):
        client = Mock()
        client.head_object.return_value = {"ContentLength": 101, "ContentType": "video/mp4"}
        with patch.dict(os.environ, {"FACTCHECK_BUCKET": "bucket", "MAX_MEDIA_BYTES": "100"}, clear=False):
            with self.assertRaises(FactCheckError):
                storage.validate_uploaded_object("key", client=client)


class RepositoryTests(unittest.TestCase):
    @staticmethod
    def _conditional_error():
        error = RuntimeError("conditional")
        error.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        return error

    def test_creation_quota_enforces_client_and_global_limits(self):
        table = Mock()
        table.update_item.side_effect = [None, self._conditional_error()]
        with patch.dict(
            os.environ,
            {
                "RATE_LIMIT_PER_CLIENT_HOUR": "6",
                "RATE_LIMIT_GLOBAL_HOUR": "30",
                "RATE_LIMIT_GLOBAL_DAY": "100",
            },
            clear=False,
        ):
            allowed, retry_after, scope = repository.consume_creation_quota(
                "hashed-client", now_epoch=3601, table=table
            )
        self.assertFalse(allowed)
        self.assertEqual(scope, "global")
        self.assertEqual(retry_after, 3599)
        self.assertEqual(table.update_item.call_count, 2)
        first_key = table.update_item.call_args_list[0].kwargs["Key"]["fact_check_id"]
        self.assertIn("hashed-client", first_key)

    def test_creation_quota_stops_at_client_hour_limit(self):
        table = Mock()
        table.update_item.side_effect = self._conditional_error()
        with patch.dict(os.environ, {"RATE_LIMIT_PER_CLIENT_HOUR": "6"}, clear=False):
            allowed, retry_after, scope = repository.consume_creation_quota(
                "hashed-client", now_epoch=3601, table=table
            )
        self.assertFalse(allowed)
        self.assertEqual(scope, "client_hour")
        self.assertEqual(retry_after, 3599)
        self.assertEqual(table.update_item.call_count, 1)

    def test_creation_quota_success_is_two_atomic_updates(self):
        table = Mock()
        with patch.dict(os.environ, {}, clear=False):
            allowed, retry_after, scope = repository.consume_creation_quota(
                "hashed-client", now_epoch=3601, table=table
            )
        self.assertTrue(allowed)
        self.assertEqual((retry_after, scope), (0, None))
        self.assertEqual(table.update_item.call_count, 2)

    def test_created_job_transition_is_conditional(self):
        table = Mock()
        repository.queue_created_job("id", "now", table=table)
        kwargs = table.update_item.call_args.kwargs
        self.assertEqual(kwargs["ConditionExpression"], "#status = :created")
        self.assertEqual(kwargs["ExpressionAttributeValues"][":created"], repository.CREATED)

    def test_processing_claim_has_expiring_lease(self):
        table = Mock()
        with patch.dict(os.environ, {"PROCESSING_LEASE_SECONDS": "60"}, clear=False):
            self.assertTrue(repository.claim_processing("id", "now", now_epoch=100, table=table))
        values = table.update_item.call_args.kwargs["ExpressionAttributeValues"]
        self.assertEqual(values[":lease"], 160)


class DownloaderValidationTests(unittest.TestCase):
    @patch("factcheck.downloader.validate_remote_url")
    def test_all_extracted_media_urls_are_validated(self, validate):
        _validate_extracted_network_urls(
            {"requested_formats": [{"url": "https://cdninstagram.com/video"}, {"url": "https://fbcdn.net/audio"}]}
        )
        self.assertEqual(validate.call_count, 2)

    def test_missing_download_url_is_rejected(self):
        with self.assertRaises(FactCheckError) as raised:
            _validate_extracted_network_urls({})
        self.assertEqual(raised.exception.code, INSTAGRAM_DOWNLOAD_FAILED)

    def test_non_https_streaming_protocol_is_rejected(self):
        with self.assertRaises(FactCheckError):
            _validate_extracted_network_urls(
                {"requested_formats": [{"url": "https://cdninstagram.com/manifest", "protocol": "m3u8_native"}]}
            )


class TranscriptionTests(unittest.TestCase):
    @patch("factcheck.transcription.transcribe_audio")
    @patch("factcheck.transcription.require_speech_energy")
    @patch("factcheck.transcription.extract_audio")
    def test_timestamped_segments_are_preserved(self, extract_audio, require_energy, transcribe):
        transcribe.return_value = [{"start": 1.25, "end": 2.5, "text": " hello ", "words": []}]
        with tempfile.TemporaryDirectory() as temp:
            result = transcribe_video(Path(temp) / "video.mp4", Path(temp))
        self.assertEqual(result, {"text": "hello", "segments": [{"start": 1.25, "end": 2.5, "text": "hello"}]})

    @patch("factcheck.transcription.extract_audio", side_effect=RuntimeError("ffmpeg"))
    def test_extraction_exception_becomes_safe_error(self, extract_audio):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(FactCheckError):
            transcribe_video(Path(temp) / "video.mp4", Path(temp))


if __name__ == "__main__":
    unittest.main()
