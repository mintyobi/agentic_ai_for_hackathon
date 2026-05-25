"""PPTX 組み立てロジック（Azure 非依存・ユニットテスト容易）.

`document_gen.py` の Blob アップロード処理から分離し、
ローカルだけで PPTX 生成が再現できるようにする。
"""
from io import BytesIO

from pptx import Presentation

# 固定スライドのテンプレート文言（Phase 3 ではダミー値）
DEFAULT_PRODUCT_NAME = "テスト商品"
DEFAULT_PRODUCT_PRICE_JPY = 10
AGENDA_ITEMS = [
    "1. ご挨拶",
    "2. 業界トレンドとお客様の課題",
    "3. ご担当者向けのご提案",
    "4. 自社商品のご紹介",
    "5. 費用について",
]


def _add_cover(prs: Presentation, title: str, subtitle: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[0])  # Title Slide
    slide.shapes.title.text = title
    slide.placeholders[1].text = subtitle


def _add_content_slide(prs: Presentation, title: str, body: str) -> None:
    """Title + bullet body の標準スライドを追加."""
    slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title and Content
    slide.shapes.title.text = title
    # placeholder[1] は body プレースホルダ。複数行は自動で箇条書きになる
    slide.placeholders[1].text = body


def build_presentation_bytes(
    cover_title: str,
    cover_subtitle: str,
    industry_body: str,
    position_body: str,
    product_name: str = DEFAULT_PRODUCT_NAME,
    product_price_jpy: int = DEFAULT_PRODUCT_PRICE_JPY,
) -> bytes:
    """6 スライド構成の PPTX をメモリ上に生成して bytes で返す.

    Azure に依存しない純粋関数。ローカルでユニットテスト可能。
    """
    prs = Presentation()

    # 1. 表紙
    _add_cover(prs, cover_title, cover_subtitle)

    # 2. 目次
    _add_content_slide(prs, "本日のアジェンダ", "\n".join(AGENDA_ITEMS))

    # 3. 対業界向け
    _add_content_slide(prs, "業界トレンドとお客様の課題", industry_body)

    # 4. 役職向け
    _add_content_slide(prs, "ご担当者向けのご提案", position_body)

    # 5. 自社商品
    _add_content_slide(
        prs,
        "自社商品のご紹介",
        f"商品名：{product_name}\n本日はこちらの商品をご提案いたします。",
    )

    # 6. 費用
    _add_content_slide(
        prs,
        "費用について",
        (
            f"商品「{product_name}」のご提供価格\n"
            f"価格：{product_price_jpy:,} 円（税別）\n"
            "※ 詳細条件は別途ご相談のうえ決定いたします。"
        ),
    )

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()
