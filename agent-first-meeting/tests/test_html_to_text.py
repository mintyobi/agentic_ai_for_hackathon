"""`_html_to_text.strip_html` のテスト.

bs4 だけに依存。WebFetchPlugin 本体（httpx 経由）は実 HTTP が必要なのでここでは扱わない。
"""
from agent_first_meeting.tools._html_to_text import strip_html


def test_strips_script_and_style_tags():
    """script / style の中身は出力に含まれないこと."""
    html = """
    <html><head>
      <style>body { color: red; }</style>
      <script>alert('xss');</script>
    </head><body>
      <p>こんにちは</p>
    </body></html>
    """
    out = strip_html(html)
    assert "こんにちは" in out
    assert "color: red" not in out
    assert "alert" not in out


def test_strips_navigation_chrome():
    """nav / footer / header は本文から除外されること."""
    html = """
    <html><body>
      <header>サイトヘッダー（除外対象）</header>
      <nav>メニュー（除外対象）</nav>
      <main><p>本文コンテンツ</p></main>
      <footer>フッター（除外対象）</footer>
    </body></html>
    """
    out = strip_html(html)
    assert "本文コンテンツ" in out
    assert "サイトヘッダー" not in out
    assert "メニュー" not in out
    assert "フッター" not in out


def test_compresses_blank_lines():
    """連続する空白行が圧縮され、空行のないテキストが返ること."""
    html = """
    <html><body>
      <p>段落1</p>


      <p>段落2</p>




      <p>段落3</p>
    </body></html>
    """
    out = strip_html(html)
    lines = out.splitlines()
    # 空行が含まれない
    assert all(line.strip() for line in lines)
    # 3 行（段落 3 つ）
    assert lines == ["段落1", "段落2", "段落3"]


def test_handles_empty_body():
    """空 HTML でも例外を投げないこと."""
    assert strip_html("") == ""
    assert strip_html("<html><body></body></html>") == ""


def test_returns_japanese_business_content():
    """企業 HP を想定した実用的な HTML を本文化できること."""
    html = """
    <html><head><title>会社案内</title></head>
    <body>
      <header>ロゴ・ナビ</header>
      <main>
        <h1>事業紹介</h1>
        <p>当社は製造業向けのDXソリューションを提供しています。</p>
        <ul>
          <li>AI ナレッジ管理</li>
          <li>技能継承支援</li>
        </ul>
      </main>
      <footer>copyright 2026</footer>
    </body></html>
    """
    out = strip_html(html)
    assert "事業紹介" in out
    assert "製造業向けのDXソリューション" in out
    assert "AI ナレッジ管理" in out
    assert "技能継承支援" in out
    assert "copyright" not in out  # footer は除外
