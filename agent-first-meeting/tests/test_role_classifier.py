"""役職カテゴリ分類のテスト."""
import pytest

from agent_first_meeting.role_classifier import classify_position


@pytest.mark.parametrize(
    "position,expected",
    [
        # 経営層
        ("代表取締役社長", "経営層"),
        ("CEO", "経営層"),
        ("ceo", "経営層"),
        ("CFO", "経営層"),
        ("取締役", "経営層"),
        ("常務取締役", "経営層"),
        ("執行役員", "経営層"),
        # 部門責任者（事業部長が部長より優先されること）
        ("事業部長", "部門責任者"),
        ("営業本部長", "部門責任者"),
        ("経営企画部長", "部門責任者"),
        ("課長", "部門責任者"),
        ("マネージャー", "部門責任者"),
        ("Senior Manager", "部門責任者"),
        # 担当者
        ("主任", "担当者"),
        ("係長", "担当者"),
        ("チームリーダー", "担当者"),
        ("担当", "担当者"),
    ],
)
def test_known_positions_are_classified(position, expected):
    assert classify_position(position) == expected


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_empty_input_returns_none(empty):
    assert classify_position(empty) is None


@pytest.mark.parametrize(
    "unknown",
    ["相談役", "アンバサダー", "メンター", "顧問"],
)
def test_unknown_positions_return_none(unknown):
    # 辞書に無い役職は None（= LLM 判定にゆだねる）
    assert classify_position(unknown) is None
