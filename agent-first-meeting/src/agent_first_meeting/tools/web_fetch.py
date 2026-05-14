"""企業 HP など外部 URL を取得して本文テキスト化するプラグイン.

SSRF 対策:
- スキームは http/https のみ
- DNS 解決後の IP が private/loopback/link-local 等なら拒否
- リダイレクトは手動で追跡し、各ホップで再チェック
"""
import json
import logging
from typing import Annotated

import httpx
from semantic_kernel.functions import kernel_function

from agent_first_meeting.tools._html_to_text import strip_html
from agent_first_meeting.tools._url_safety import is_safe_public_url

logger = logging.getLogger(__name__)

# 安全のためのリミット
_FETCH_TIMEOUT_SEC = 10.0
_MAX_BYTES = 1_000_000          # 1MB 上限（巨大ページの暴発を防ぐ）
_MAX_TEXT_CHARS = 4_000         # LLM に投げるテキストの上限
_MAX_REDIRECTS = 5              # リダイレクト追跡の上限
_USER_AGENT = (
    "Mozilla/5.0 (compatible; agent-first-meeting/0.1; +https://example.com/bot)"
)


def _error_payload(reason: str) -> str:
    """LLM が構造的に判定できる JSON エラーを返す."""
    return json.dumps({"ok": False, "error": reason}, ensure_ascii=False)


def _ok_payload(text: str, final_url: str) -> str:
    """LLM が構造的に判定できる JSON 成功レスポンスを返す."""
    return json.dumps(
        {"ok": True, "final_url": final_url, "text": text},
        ensure_ascii=False,
    )


def _fetch_with_safe_redirects(client: httpx.Client, start_url: str) -> httpx.Response:
    """SSRF 対策のため、リダイレクトを手動で追跡しつつ毎ホップで URL を検証する."""
    current_url = start_url
    for _ in range(_MAX_REDIRECTS):
        ok, reason = is_safe_public_url(current_url)
        if not ok:
            raise PermissionError(f"refused unsafe url '{current_url}': {reason}")
        resp = client.get(current_url)
        if resp.status_code in (301, 302, 303, 307, 308):
            next_url = resp.headers.get("location")
            if not next_url:
                raise httpx.HTTPError("redirect without Location header")
            # 相対 URL の場合は前回 URL からの絶対化
            current_url = str(httpx.URL(current_url).join(next_url))
            continue
        return resp
    raise httpx.HTTPError(f"too many redirects (>{_MAX_REDIRECTS})")


class WebFetchPlugin:
    """顧客企業の HP など、外部 URL の本文テキストを取得する SK プラグイン."""

    @kernel_function(
        description=(
            "顧客企業のホームページなど、外部 URL の本文テキストを取得する。"
            "SSRF 対策のため内部 IP・メタデータエンドポイントは弾かれる。"
            "返り値は JSON 文字列で {ok: bool, ...}。"
            "  - 成功: {ok: true, final_url: '...', text: '...'}"
            "  - 失敗: {ok: false, error: '...'}"
            "失敗時はテキストとして利用してはならない。"
        ),
    )
    def fetch_url_text(
        self,
        url: Annotated[
            str,
            "取得したい URL。http または https で始まる絶対 URL であること。",
        ],
    ) -> Annotated[str, "JSON 文字列。詳細は description を参照。"]:
        logger.info("WebFetchPlugin: fetching url=%s", url)

        ok, reason = is_safe_public_url(url)
        if not ok:
            logger.warning("WebFetchPlugin: refused url=%s reason=%s", url, reason)
            return _error_payload(reason)

        try:
            with httpx.Client(
                timeout=_FETCH_TIMEOUT_SEC,
                follow_redirects=False,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = _fetch_with_safe_redirects(client, url)
        except PermissionError as e:
            logger.warning("WebFetchPlugin: blocked redirect: %s", e)
            return _error_payload(str(e))
        except httpx.HTTPError as e:
            logger.warning(
                "WebFetchPlugin: fetch error url=%s err=%s",
                url, e, exc_info=True,
            )
            return _error_payload(f"fetch failed: {type(e).__name__}: {e}")

        if resp.status_code >= 400:
            logger.warning(
                "WebFetchPlugin: http %s for %s", resp.status_code, url,
            )
            return _error_payload(f"http {resp.status_code}")

        body_bytes = resp.content[:_MAX_BYTES]
        try:
            html = body_bytes.decode(resp.encoding or "utf-8", errors="replace")
        except LookupError:
            html = body_bytes.decode("utf-8", errors="replace")

        text = strip_html(html)
        if len(text) > _MAX_TEXT_CHARS:
            text = text[:_MAX_TEXT_CHARS] + "\n...[truncated]"
        if not text:
            return _error_payload("empty body")

        logger.info(
            "WebFetchPlugin: success url=%s final=%s chars=%d",
            url, resp.url, len(text),
        )
        return _ok_payload(text, str(resp.url))
