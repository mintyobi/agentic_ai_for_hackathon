"""自社フォーマットの PPTX テンプレ（`templates/default.pptx`）を生成する.

このスクリプトは「テンプレ方式の動作確認用」の最小サンプルを生成する。
実運用ではこの `default.pptx` を PowerPoint で開き、
スライドマスター・レイアウトに **会社の配色・ロゴ・フォント** を適用して上書きする。

レイアウトは `_pptx_builder._LAYOUT_RESOLUTION` の順序で解決される：
  Cover / Agenda / Industry / Position / Product / Cost
  → 無ければ "Title Slide" / "Title and Content"（python-pptx 既定）
  → それも無ければ index 0/1

ここでは便宜のため、python-pptx 既定のレイアウト名 0..5 を上記6つに**改名**しておく
（XML 属性 `cSld@name` を書き換える）。これにより、テンプレを編集する人が
PowerPoint 上で「どのレイアウトが何用か」を一目で識別できる。
"""
from pathlib import Path

from pptx import Presentation
from pptx.oxml.ns import qn


# (index, 新しい名前) のマッピング。
# 既定では Cover のみ改名し、他のスライドは fallback で "Title and Content"（slot 1）を共有する。
# python-pptx 既定の slot 2..5（Section Header / Two Content / Comparison / Title Only）は
# プレースホルダ構造が違うため、Agenda/Industry/... と勝手に名付けると本文流し込みで失敗する。
# 専用デザインを当てたい場合は、各レイアウトを PowerPoint で複製→改名する運用にする。
_LAYOUT_RENAMES = [
    (0, "Cover"),
]


def _rename_layout(layout, new_name: str) -> None:
    """slideLayout/cSld@name を上書きしてレイアウト名を改名する."""
    cSld = layout.element.find(qn("p:cSld"))
    if cSld is not None:
        cSld.set("name", new_name)


def build_default_template(out_path: Path) -> None:
    prs = Presentation()
    for idx, new_name in _LAYOUT_RENAMES:
        if idx < len(prs.slide_layouts):
            _rename_layout(prs.slide_layouts[idx], new_name)
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
