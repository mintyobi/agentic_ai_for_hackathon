"""outcomes 記録の対象 meeting を選ぶ純ロジック.

`_company_id.py` と同じく azure 系を import しない純粋モジュールに分離して、
重い依存なしで unit test できるようにする。
"""
from typing import Any


def select_target_meeting(
    meetings: list[dict[str, Any]], round_num: int | None
) -> dict[str, Any] | None:
    """outcomes を書き込む対象の meeting を選ぶ.

    Args:
        meetings: 同一顧客の meeting ドキュメント一覧（順序は問わない）。
        round_num: 対象の round。None または 0 以下なら最新（最大 round）を対象にする。

    Returns:
        対象 meeting。候補が無い / 指定 round が見つからない場合は None。
    """
    if not meetings:
        return None
    if round_num is not None and round_num > 0:
        for meeting in meetings:
            if meeting.get("round") == round_num:
                return meeting
        return None
    return max(meetings, key=lambda m: m.get("round", 0))
