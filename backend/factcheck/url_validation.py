"""Strict normalization and network policy for Instagram Reel URLs."""

from __future__ import annotations

import contextlib
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from .errors import FactCheckError, INVALID_INSTAGRAM_URL


SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,64}$")
INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
NETWORK_SUFFIXES = (
    "instagram.com",
    "cdninstagram.com",
    "fbcdn.net",
)


def normalize_instagram_reel_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise FactCheckError(INVALID_INSTAGRAM_URL, "A valid Instagram Reel URL is required.")
    try:
        parsed = urlsplit(value.strip())
    except ValueError as error:
        raise FactCheckError(INVALID_INSTAGRAM_URL, "The Instagram URL is malformed.") from error
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or host not in INSTAGRAM_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise FactCheckError(INVALID_INSTAGRAM_URL, "Only public HTTPS Instagram Reel URLs are supported.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0].lower() != "reel" or not SHORTCODE_RE.fullmatch(parts[1]):
        raise FactCheckError(INVALID_INSTAGRAM_URL, "The URL must identify an Instagram Reel.")
    return urlunsplit(("https", "www.instagram.com", f"/reel/{parts[1]}/", "", ""))


def _hostname_allowed(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    return any(normalized == suffix or normalized.endswith(f".{suffix}") for suffix in NETWORK_SUFFIXES)


def _address_is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not any(
        (ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved)
    )


def resolve_public_addresses(host: str, port: int = 443) -> list[str]:
    if not _hostname_allowed(host):
        raise FactCheckError(INVALID_INSTAGRAM_URL, "Instagram redirected to an unsupported host.")
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise FactCheckError(INVALID_INSTAGRAM_URL, "The Instagram media host could not be resolved.") from error
    addresses = sorted({record[4][0] for record in records})
    if not addresses or not all(_address_is_public(address) for address in addresses):
        raise FactCheckError(INVALID_INSTAGRAM_URL, "The media URL resolved to a prohibited address.")
    return addresses


def validate_remote_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise FactCheckError(INVALID_INSTAGRAM_URL, "Instagram returned an unsafe media URL.")
    resolve_public_addresses(parsed.hostname, parsed.port or 443)


@contextlib.contextmanager
def restricted_instagram_network():
    """Restrict every DNS lookup made by yt-dlp, including redirect targets."""
    original_getaddrinfo = socket.getaddrinfo

    def guarded_getaddrinfo(host, port, *args, **kwargs):
        host_text = host.decode() if isinstance(host, bytes) else str(host)
        if not _hostname_allowed(host_text):
            raise OSError("Network destination is not permitted.")
        records = original_getaddrinfo(host, port, *args, **kwargs)
        if not records or not all(_address_is_public(record[4][0]) for record in records):
            raise OSError("Network destination resolved to a prohibited address.")
        return records

    socket.getaddrinfo = guarded_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo
