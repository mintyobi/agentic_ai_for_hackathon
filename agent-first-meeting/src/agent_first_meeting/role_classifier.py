"""取引相手の役職を「経営層 / 部門責任者 / 担当者」の3カテゴリに分類する.

UI は自由入力のため、辞書ベースのキーワードマッチで前処理する。
辞書に無い場合は None を返し、LLM 側で判断させる契約。
"""
from typing import Literal

PositionCategory = Literal["経営層", "部門責任者", "担当者"]

# 重要：「部長」より先に「事業部長」を判定する必要があるため、
#       より具体的なキーワードを先に並べる
_KEYWORDS_BY_CATEGORY: list[tuple[str, PositionCategory]] = [
    # 経営層
    ("代表取締役", "経営層"),
    ("CEO", "経営層"),
    ("CTO", "経営層"),
    ("CFO", "経営層"),
    ("COO", "経営層"),
    ("CIO", "経営層"),
    ("CDO", "経営層"),
    ("社長", "経営層"),
    ("副社長", "経営層"),
    ("会長", "経営層"),
    ("常務", "経営層"),
    ("専務", "経営層"),
    ("執行役員", "経営層"),
    ("取締役", "経営層"),
    # 部門責任者
    ("事業部長", "部門責任者"),
    ("本部長", "部門責任者"),
    ("副部長", "部門責任者"),
    ("部長", "部門責任者"),
    ("室長", "部門責任者"),
    ("次長", "部門責任者"),
    ("課長", "部門責任者"),
    ("マネージャー", "部門責任者"),
    ("マネジャー", "部門責任者"),
    ("manager", "部門責任者"),
    # 担当者
    ("リーダー", "担当者"),
    ("主任", "担当者"),
    ("係長", "担当者"),
    ("主査", "担当者"),
    ("チーフ", "担当者"),
    ("担当", "担当者"),
    ("スタッフ", "担当者"),
]


def classify_position(position: str) -> PositionCategory | None:
    """役職文字列を 3 カテゴリに分類. 不明な場合は None を返す."""
    if not position:
        return None
    normalized = position.strip().lower()
    if not normalized:
        return None
    for keyword, category in _KEYWORDS_BY_CATEGORY:
        if keyword.lower() in normalized:
            return category
    return None
