"""HTML → 本文テキストの軽量変換ユーティリティ（Azure / SK 非依存）.

`web_fetch.py` の `WebFetchPlugin` から切り出し、ユニットテスト容易性のため
独立ファイルにしてある。bs4 にのみ依存。
"""
from bs4 import BeautifulSoup


def strip_html(html: str) -> str:
    """HTML から script/style/nav/footer/header を捨てて、本文テキストを抽出する.

    - 連続する空白行は 1 つに圧縮
    - 行頭・行末の空白は trim
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
