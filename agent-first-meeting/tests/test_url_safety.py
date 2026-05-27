"""SSRF ガード `_url_safety.is_safe_public_url` のテスト."""
from unittest.mock import patch

import pytest

from agent_first_meeting.tools._url_safety import (
    is_safe_public_url,
    safe_resolved_ip,
)


def _mock_getaddrinfo(ip: str):
    """socket.getaddrinfo の戻り値を ip 1つだけにモックするヘルパ."""
    return [(0, 0, 0, "", (ip, 0))]


def test_rejects_invalid_scheme():
    ok, reason = is_safe_public_url("ftp://example.com")
    assert ok is False
    assert "scheme" in reason


def test_rejects_empty_url():
    ok, reason = is_safe_public_url("")
    assert ok is False


def test_rejects_url_without_hostname():
    ok, reason = is_safe_public_url("http:///path")
    assert ok is False


@pytest.mark.parametrize(
    "hostname",
    ["169.254.169.254", "metadata.google.internal", "localhost", "metadata"],
)
def test_rejects_known_metadata_hostnames(hostname):
    ok, reason = is_safe_public_url(f"http://{hostname}/foo")
    assert ok is False
    assert "blocked" in reason.lower() or "internal" in reason.lower()


@pytest.mark.parametrize(
    "internal_ip",
    [
        "127.0.0.1",         # loopback
        "10.0.0.5",          # private
        "192.168.1.1",       # private
        "172.16.0.1",        # private
        "169.254.169.254",   # link-local / IMDS
        "0.0.0.0",           # unspecified
        "::1",               # ipv6 loopback
        "fc00::1",           # ipv6 unique-local (private)
    ],
)
def test_rejects_internal_ip_resolutions(internal_ip):
    """DNS が内部 IP を返した場合に弾かれること."""
    with patch(
        "agent_first_meeting.tools._url_safety.socket.getaddrinfo",
        return_value=_mock_getaddrinfo(internal_ip),
    ):
        ok, reason = is_safe_public_url("http://attacker.example.com/foo")
    assert ok is False
    # 名前ベースで弾いたか、IP ベースで弾いたか、いずれかのメッセージ
    assert (
        "internal" in reason.lower()
        or "blocked" in reason.lower()
    ), reason


def test_accepts_public_ip_resolution():
    """公開 IP が返れば通ること."""
    with patch(
        "agent_first_meeting.tools._url_safety.socket.getaddrinfo",
        return_value=_mock_getaddrinfo("93.184.216.34"),  # example.com の旧 IP
    ):
        ok, reason = is_safe_public_url("https://example.com/")
    assert ok is True, reason


def test_safe_resolved_ip_returns_validated_public_ip():
    """公開 IP に解決される場合、ピンニング用の IP を返す."""
    with patch(
        "agent_first_meeting.tools._url_safety.socket.getaddrinfo",
        return_value=_mock_getaddrinfo("93.184.216.34"),
    ):
        ok, reason, ip = safe_resolved_ip("https://example.com/")
    assert ok is True, reason
    assert ip == "93.184.216.34"


def test_safe_resolved_ip_blocks_internal_and_returns_none():
    """内部 IP に解決される場合は ok=False かつ ip=None."""
    with patch(
        "agent_first_meeting.tools._url_safety.socket.getaddrinfo",
        return_value=_mock_getaddrinfo("169.254.169.254"),
    ):
        ok, reason, ip = safe_resolved_ip("http://attacker.example.com/")
    assert ok is False
    assert ip is None


def test_dns_failure_is_treated_as_unsafe():
    import socket as real_socket
    with patch(
        "agent_first_meeting.tools._url_safety.socket.getaddrinfo",
        side_effect=real_socket.gaierror("simulated"),
    ):
        ok, reason = is_safe_public_url("http://does-not-exist.example.invalid/")
    assert ok is False
    assert "dns" in reason.lower()
