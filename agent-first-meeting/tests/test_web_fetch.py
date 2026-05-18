"""`_web_fetch_helpers` のストリーミング / Content-Type ガードのテスト.

httpx の本物ネットワークは叩かず、`httpx.MockTransport` でレスポンスを差し替える。
Azure / Semantic Kernel に依存しない（SK 非依存ヘルパだけを import している）。
"""
from unittest.mock import patch

import httpx
import pytest

from agent_first_meeting.tools._web_fetch_helpers import (
    MAX_BYTES,
    ContentTooLargeError,
    UnsupportedContentTypeError,
    fetch_with_safe_redirects,
    is_allowed_content_type,
)


def _safe_url_patch():
    """is_safe_public_url を常に OK 扱いにする patch（SSRF ガード以外を試験するため）."""
    return patch(
        "agent_first_meeting.tools._web_fetch_helpers.is_safe_public_url",
        return_value=(True, "ok"),
    )


def _client_with(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------- is_allowed_content_type ----------

@pytest.mark.parametrize("ct", [
    "text/html",
    "text/html; charset=utf-8",
    "TEXT/HTML",
    "application/xhtml+xml",
    "text/plain; charset=us-ascii",
    None,  # ヘッダ未設定は許容
    "",
])
def test_allowed_content_types(ct):
    assert is_allowed_content_type(ct) is True


@pytest.mark.parametrize("ct", [
    "application/pdf",
    "image/png",
    "application/octet-stream",
    "video/mp4",
])
def test_blocked_content_types(ct):
    assert is_allowed_content_type(ct) is False


# ---------- fetch_with_safe_redirects: ストリーミング切り捨て ----------

def test_rejects_oversized_content_length_header():
    """Content-Length が MAX_BYTES 超なら本文を読まずに弾く."""
    def handler(req):
        return httpx.Response(
            200,
            headers={
                "content-length": str(MAX_BYTES + 1),
                "content-type": "text/html",
            },
            content=b"x",
        )
    with _safe_url_patch(), _client_with(handler) as client:
        with pytest.raises(ContentTooLargeError):
            fetch_with_safe_redirects(client, "https://example.com")


def test_rejects_body_exceeding_max_bytes_midstream():
    """Content-Length 詐称（or 未設定）で実体が MAX_BYTES 超の場合も弾く."""
    huge_body = b"a" * (MAX_BYTES + 100)
    def handler(req):
        # content-length ヘッダはあえて付けない
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=huge_body
        )
    with _safe_url_patch(), _client_with(handler) as client:
        with pytest.raises(ContentTooLargeError):
            fetch_with_safe_redirects(client, "https://example.com")


def test_rejects_non_html_content_type():
    def handler(req):
        return httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF-"
        )
    with _safe_url_patch(), _client_with(handler) as client:
        with pytest.raises(UnsupportedContentTypeError):
            fetch_with_safe_redirects(client, "https://example.com")


def test_accepts_html_response():
    html = "<html><body><p>hello world</p></body></html>"
    def handler(req):
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=html.encode("utf-8"),
        )
    with _safe_url_patch(), _client_with(handler) as client:
        status, final_url, body, _ = fetch_with_safe_redirects(
            client, "https://example.com"
        )
    assert status == 200
    assert "example.com" in final_url
    assert b"hello world" in body


def test_follows_redirect_and_revalidates_each_hop():
    """301 を辿る間、is_safe_public_url が各ホップ呼ばれること."""
    calls = {"n": 0}

    def handler(req):
        if str(req.url).endswith("/start"):
            return httpx.Response(
                301, headers={"location": "https://example.com/end"}
            )
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"<p>ok</p>"
        )

    def fake_safe(url):
        calls["n"] += 1
        return True, "ok"

    with patch(
        "agent_first_meeting.tools._web_fetch_helpers.is_safe_public_url",
        side_effect=fake_safe,
    ), _client_with(handler) as client:
        status, final_url, _body, _enc = fetch_with_safe_redirects(
            client, "https://example.com/start"
        )
    assert status == 200
    assert final_url.endswith("/end")
    assert calls["n"] == 2  # start + end の 2 ホップ分


def test_redirect_to_unsafe_url_is_blocked():
    """リダイレクト先が内部 IP だった場合に PermissionError で停止する."""
    def handler(req):
        if str(req.url).endswith("/start"):
            return httpx.Response(
                302, headers={"location": "http://169.254.169.254/meta"}
            )
        return httpx.Response(200, content=b"should not reach")

    # 1 段目だけ True、それ以降は本物の判定にフォールバック
    real_safe = __import__(
        "agent_first_meeting.tools._url_safety", fromlist=["is_safe_public_url"]
    ).is_safe_public_url

    def fake_safe(url):
        if url.endswith("/start"):
            return True, "ok"
        return real_safe(url)

    with patch(
        "agent_first_meeting.tools._web_fetch_helpers.is_safe_public_url",
        side_effect=fake_safe,
    ), _client_with(handler) as client:
        with pytest.raises(PermissionError):
            fetch_with_safe_redirects(client, "https://example.com/start")
