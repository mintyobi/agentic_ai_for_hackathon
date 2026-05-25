"""`_company_id.deterministic_company_id` / `meeting_record._meeting_doc_id` のテスト.

`_company_id` は azure 系を import しないので直接 import 可能。
`_meeting_doc_id` は meeting_record.py 内にあり azure-cosmos に依存するため、
重い import を避けるためにここでは companyId の決定性のみを検証する。
"""
import pytest

from agent_first_meeting._company_id import deterministic_company_id


def test_company_id_is_deterministic():
    """同じ会社名なら同じ companyId が出ること."""
    a = deterministic_company_id("株式会社サンプル製作所")
    b = deterministic_company_id("株式会社サンプル製作所")
    assert a == b


def test_company_id_normalizes_whitespace():
    """前後の空白は無視して同じ ID になること."""
    a = deterministic_company_id("株式会社サンプル")
    b = deterministic_company_id("  株式会社サンプル  ")
    assert a == b


def test_company_id_is_unique_per_name():
    """別の会社名なら別の ID が出ること."""
    a = deterministic_company_id("株式会社A")
    b = deterministic_company_id("株式会社B")
    assert a != b


def test_company_id_has_expected_prefix_and_length():
    """`cus_` プレフィックス + 12 文字の hex で合計 16 文字."""
    cid = deterministic_company_id("株式会社サンプル")
    assert cid.startswith("cus_")
    assert len(cid) == len("cus_") + 12
    # SHA1 hex 部分は 0-9a-f
    hex_part = cid[len("cus_"):]
    assert all(c in "0123456789abcdef" for c in hex_part)


@pytest.mark.parametrize("name", ["", "   "])
def test_company_id_with_empty_name_is_still_deterministic(name):
    """空文字でも例外を投げず、決定的に同じ ID を返すこと（保険）."""
    a = deterministic_company_id(name)
    b = deterministic_company_id(name)
    assert a == b
    assert a.startswith("cus_")
