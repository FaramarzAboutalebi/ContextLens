import socket
import unittest
from unittest.mock import patch

from factcheck.errors import FactCheckError
from factcheck.url_validation import (
    normalize_instagram_reel_url,
    resolve_public_addresses,
    restricted_instagram_network,
)


class UrlValidationTests(unittest.TestCase):
    def test_normalizes_query_and_trailing_slash(self):
        self.assertEqual(
            normalize_instagram_reel_url(
                "https://instagram.com/reel/DePHLhtON_i/?utm_source=test"
            ),
            "https://www.instagram.com/reel/DePHLhtON_i/",
        )

    def test_rejects_non_https_and_lookalike_domains(self):
        for value in (
            "http://www.instagram.com/reel/DePHLhtON_i/",
            "https://instagram.com.evil.example/reel/DePHLhtON_i/",
            "https://evilinstagram.com/reel/DePHLhtON_i/",
        ):
            with self.subTest(value=value), self.assertRaises(FactCheckError):
                normalize_instagram_reel_url(value)

    def test_rejects_credentials_and_wrong_paths(self):
        for value in (
            "https://user:pass@www.instagram.com/reel/DePHLhtON_i/",
            "https://www.instagram.com/p/DePHLhtON_i/",
            "https://www.instagram.com/reel/!!/",
        ):
            with self.subTest(value=value), self.assertRaises(FactCheckError):
                normalize_instagram_reel_url(value)

    @patch("factcheck.url_validation.socket.getaddrinfo")
    def test_rejects_private_dns_result(self, getaddrinfo):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))
        ]
        with self.assertRaises(FactCheckError):
            resolve_public_addresses("www.instagram.com")

    def test_network_guard_rejects_unrelated_redirect_host(self):
        with restricted_instagram_network(), self.assertRaises(OSError):
            socket.getaddrinfo("example.com", 443)


if __name__ == "__main__":
    unittest.main()

