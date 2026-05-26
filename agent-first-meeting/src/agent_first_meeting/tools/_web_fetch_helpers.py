"""WebFetchPlugin の SSRF / サイズ / Content-Type ガード本体（SK 非依存）.

`web_fetch.py` の `WebFetchPlugin` から切り出した。
semantic_kernel に依存しないので、httpx だけでユニットテスト可能。
"""
import ipaddress

import httpx

from agent_first_meeting.tools._url_safety import safe_resolved_ip

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


def _pinned_request_args(url_str: str, ip: str) -> tuple[str, dict, dict]:
    """検証済み IP へ固定接続するための (接続URL, 追加ヘッダ, extensions) を返す.

    ホストが DNS 名のときだけ接続先を検証済み IP に差し替え、Host ヘッダと TLS SNI を
    元ホスト名に保つ（httpx 公式の IP ピンニング手法）。これにより検証〜接続間の
    DNS 再解決（rebinding）を排除する。ホストが IP リテラルなら rebinding の
    余地が無いのでそのまま接続する。
    """
    url = httpx.URL(url_str)
    host = url.host
    try:
        ipaddress.ip_address(host)
        return url_str, {}, {}  # IP リテラル: 差し替え不要
    except ValueError:
        pass
    connect_url = str(url.copy_with(host=ip))
    host_header = host if url.port is None else f"{host}:{url.port}"
    return connect_url, {"Host": host_header}, {"sni_hostname": host}


def fetch_with_safe_redirects(
    client: httpx.Client, start_url: str
) -> tuple[int, str, bytes, str | None]:
    """SSRF 対策のため、リダイレクトを手動で追跡しつつ毎ホップで URL を検証する.

    各ホップで DNS を解決・検証し、**検証済み IP へ固定接続**することで DNS
    リバインディング（検証時は公開 IP・接続時は内部 IP を返す攻撃）を防ぐ。
    本文は stream で受信し、累積バイト数が MAX_BYTES を超えた時点で打ち切る
    （resp.content を呼ぶと httpx が全量バッファするため、Content-Length を
    詐称した悪意あるサーバでメモリを枯渇させられないようにする）。

    Returns:
        (status_code, final_url, body_bytes, encoding)。final_url は論理 URL
        （IP 差し替え前のホスト名ベース）。
    """
    current_url = start_url
    for _ in range(MAX_REDIRECTS):
        ok, reason, ip = safe_resolved_ip(current_url)
        if not ok or ip is None:
            raise PermissionError(f"refused unsafe url '{current_url}': {reason}")

        connect_url, extra_headers, extensions = _pinned_request_args(current_url, ip)
        with client.stream(
            "GET",
            connect_url,
            headers=extra_headers or None,
            extensions=extensions,
        ) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                next_url = resp.headers.get("location")
                if not next_url:
                    raise httpx.HTTPError("redirect without Location header")
                # 相対 URL の場合は前回の論理 URL からの絶対化
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
            # final_url は論理 URL を返す（接続は IP だが利用側にはホスト名を見せる）
            return resp.status_code, current_url, b"".join(chunks), resp.encoding
    raise httpx.HTTPError(f"too many redirects (>{MAX_REDIRECTS})")
