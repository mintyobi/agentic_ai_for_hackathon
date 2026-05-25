"""`_meeting_select.select_target_meeting` のテスト.

`_meeting_select` は azure 系を import しない純粋モジュールなので直接 import できる。
"""
from agent_first_meeting._meeting_select import select_target_meeting


def _meetings() -> list[dict]:
    # わざと round 順をバラバラに並べる（実装が順序に依存しないことを示す）
    return [
        {"id": "mtg_x_0002", "round": 2, "outcomes": None},
        {"id": "mtg_x_0001", "round": 1, "outcomes": "前回の所感"},
        {"id": "mtg_x_0003", "round": 3, "outcomes": None},
    ]


def test_returns_none_when_no_meetings():
    """履歴が空なら対象なし."""
    assert select_target_meeting([], None) is None
    assert select_target_meeting([], 1) is None


def test_picks_latest_when_round_omitted():
    """round 未指定（None / 0 / 負）なら最大 round を返す."""
    for round_arg in (None, 0, -1):
        target = select_target_meeting(_meetings(), round_arg)
        assert target is not None
        assert target["round"] == 3
        assert target["id"] == "mtg_x_0003"


def test_picks_specific_round_when_given():
    """正の round 指定なら、その round の meeting を返す."""
    target = select_target_meeting(_meetings(), 1)
    assert target is not None
    assert target["round"] == 1
    assert target["id"] == "mtg_x_0001"


def test_returns_none_when_specified_round_missing():
    """存在しない round を指定したら None."""
    assert select_target_meeting(_meetings(), 99) is None


def test_handles_missing_round_field():
    """round フィールドが欠けた要素があっても落ちず、最大 round を選べる."""
    meetings = [{"id": "a"}, {"id": "b", "round": 5}]
    target = select_target_meeting(meetings, None)
    assert target is not None
    assert target["id"] == "b"
