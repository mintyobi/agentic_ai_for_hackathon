"""WebFetchPlugin の SSRF / サイズ / Content-Type ガード本体（SK 非依存）.

`web_fetch.py` の `WebFetchPlugin` から切り出した。
semantic_kernel に依存しないので、httpx だけでユニットテスト可能。
"""
import httpx

from agent_first_meeting.tools._url_safety import is_safe_public_url

# 安全のためのリミット
FETCH_TIMEOUT_SEC = 10.0
MAX_BYTES = 1_000_000          # 1MB 上限（巨大ページの暴発を防ぐ）
MAX_TEXT_CHARS = 4_000         # LLM に投げるテキストの上限
MAX_REDIRECTS = 5              # リダイレクト追跡の上限
USER_AGENT = (
    "Mozilla/5.0 (compatible; agent-first-meeting/0.1; +https://example.com/bot)"
)
# HTML 以外（PDF / 動画 / バイナリ）は LLM に渡しても意味がないので弾く
ALLOWED_CONTENT_TYPE_PREFIXES = ("text/html", "application/xhtml+xml", "text/plain")


class ContentTooLargeError(httpx.HTTPError):
    """ストリーミング受信中に MAX_BYTES を超えた場合に投げる."""


class UnsupportedContentTypeError(httpx.HTTPError):
    """text/html 以外の Content-Type が返ってきた場合に投げる."""


def is_allowed_content_type(content_type: str | None) -> bool:
    if not content_type:
        # 明示されていない場合は受け入れる（古いサイトでは未設定もある）
        return True
    head = content_type.split(";", 1)[0].strip().lower()
    return head.startswith(ALLOWED_CONTENT_TYPE_PREFIXES)


def fetch_with_safe_redirects(
    client: httpx.Client, start_url: str
) -> tuple[int, str, bytes, str | None]:
    """SSRF 対策のため、リダイレクトを手動で追跡しつつ毎ホップで URL を検証する.

    本文は stream で受信し、累積バイト数が MAX_BYTES を超えた時点で打ち切る
    （resp.content を呼ぶと httpx が全量バッファするため、Content-Length を
    詐称した悪意あるサーバでメモリを枯渇させられないようにする）。

    Returns:
        (status_code, final_url, body_bytes, encoding)
    """
    current_url = start_url
    for _ in range(MAX_REDIRECTS):
        ok, reason = is_safe_public_url(current_url)
        if not ok:
            raise PermissionError(f"refused unsafe url '{current_url}': {reason}")

        with client.stream("GET", current_url) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                next_url = resp.headers.get("location")
                if not next_url:
                    raise httpx.HTTPError("redirect without Location header")
                # 相対 URL の場合は前回 URL からの絶対化
                current_url = str(httpx.URL(current_url).join(next_url))
                continue

            # Content-Length が既に巨大なら本文を読まずに弾く
            content_length = resp.headers.get("content-length")
            if content_length and content_length.isdigit():
                if int(content_length) > MAX_BYTES:
                    raise ContentTooLargeError(
                        f"content-length {content_length} exceeds {MAX_BYTES}"
                    )

            content_type = resp.headers.get("content-type")
            if resp.status_code < 400 and not is_allowed_content_type(content_type):
                raise UnsupportedContentTypeError(
                    f"unsupported content-type: {content_type!r}"
                )

            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ContentTooLargeError(
                        f"response body exceeded {MAX_BYTES} bytes mid-stream"
                    )
                chunks.append(chunk)
            return resp.status_code, str(resp.url), b"".join(chunks), resp.encoding
    raise httpx.HTTPError(f"too many redirects (>{MAX_REDIRECTS})")
