"""自社フォーマットの PPTX テンプレ（`templates/default.pptx`）を生成する.

スタイル: クリーン・モダン（スレートブルー × スチールブルー）
  - Cover: 下端のソリッドバンド（Primary）＋ 直上の細いライン（Accent）
  - 本文（Title and Content）: 上端の細いライン（Accent）
  - 装飾シェイプは Z-オーダーで背面へ送り、タイトル/本文プレースホルダを隠さない

python-pptx の `LayoutShapes` には `add_shape` の高レベル API が無いため、
DrawingML の `<p:sp>` 要素を XML で組み立てて `spTree` に直接挿入する。

レイアウト解決ルール（`_pptx_builder._LAYOUT_RESOLUTION`）:
  Cover / Agenda / Industry / Position / Product / Cost
  → 無ければ "Title Slide" / "Title and Content"（python-pptx 既定）→ idx 0/1
ここでは Cover のみ改名し、本文5枚は `Title and Content`（slot 1）を共有する。
"""
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Inches


# 配色（自社ブランドを当てたいときはここを変える）
PRIMARY_HEX = "2C3E50"  # ダークスレートブルー
ACCENT_HEX = "5DADE2"   # スチールブルー

# (index, 新しい名前) のマッピング。既定では Cover のみ改名（理由は冒頭参照）。
_LAYOUT_RENAMES = [
    (0, "Cover"),
]

# DrawingML 矩形シェイプの XML テンプレ（枠線なし・ソリッド塗り）
_RECT_XML_TEMPLATE = """\
<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:nvSpPr>
    <p:cNvPr id="{shape_id}" name="Band{shape_id}"/>
    <p:cNvSpPr/>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm>
      <a:off x="{x}" y="{y}"/>
      <a:ext cx="{w}" cy="{h}"/>
    </a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
    <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
    <a:ln><a:noFill/></a:ln>
  </p:spPr>
</p:sp>"""


def _rename_layout(layout, new_name: str) -> None:
    cSld = layout.element.find(qn("p:cSld"))
    if cSld is not None:
        cSld.set("name", new_name)


def _insert_rect(layout, shape_id: int, x: int, y: int, w: int, h: int, color_hex: str) -> None:
    """枠線なしのソリッド矩形を layout の spTree に挿入する.

    最背面（spTree の先頭2要素 nvGrpSpPr / grpSpPr の直後）へ入れて、
    タイトル/本文プレースホルダを隠さないようにする。
    """
    xml = _RECT_XML_TEMPLATE.format(
        shape_id=shape_id, x=int(x), y=int(y), w=int(w), h=int(h), color=color_hex
    )
    sp = etree.fromstring(xml)
    spTree = layout.shapes._spTree  # noqa: SLF001
    # 先頭2要素（nvGrpSpPr, grpSpPr）の直後に挿入＝最背面
    spTree.insert(2, sp)


def _decorate_cover(layout, slide_w, slide_h) -> None:
    """Cover: 下端 Primary バンド ＋ 直上 Accent ライン."""
    band_h = Inches(1.2)
    line_h = Inches(0.08)
    _insert_rect(layout, 9001, 0, slide_h - band_h, slide_w, band_h, PRIMARY_HEX)
    _insert_rect(layout, 9002, 0, slide_h - band_h - line_h, slide_w, line_h, ACCENT_HEX)


def _decorate_content(layout, slide_w) -> None:
    """本文レイアウト: 上端の Accent 細ライン."""
    line_h = Inches(0.08)
    _insert_rect(layout, 9101, 0, 0, slide_w, line_h, ACCENT_HEX)


def build_default_template(out_path: Path) -> None:
    prs = Presentation()
    slide_w = prs.slide_width
    slide_h = prs.slide_height

    for idx, new_name in _LAYOUT_RENAMES:
        if idx < len(prs.slide_layouts):
            _rename_layout(prs.slide_layouts[idx], new_name)

    _decorate_cover(prs.slide_layouts[0], slide_w, slide_h)
    _decorate_content(prs.slide_layouts[1], slide_w)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    print(f"wrote {out_path}")
    print("layouts after rename:")
    for i, layout in enumerate(prs.slide_layouts):
        print(f"  [{i}] {layout.name}")


if __name__ == "__main__":
    # scripts/ → agent-first-meeting/ → templates/default.pptx
    target = Path(__file__).resolve().parents[1] / "templates" / "default.pptx"
    build_default_template(target)
