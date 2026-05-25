"""`schemas.GenerateRequest` のバリデーションと `to_user_message` 整形のテスト."""
import pytest
from pydantic import ValidationError

from agent_first_meeting.schemas import GenerateRequest, to_user_message


def _minimum_payload(**overrides) -> dict:
    base = {
        "companyName": "株式会社サンプル",
        "industry": "製造業",
        "scale": "中小企業",
    }
    base.update(overrides)
    return base


def test_minimum_required_fields_are_accepted():
    """3 つの必須項目だけでバリデーションが通り、任意項目はデフォルトになること."""
    req = GenerateRequest(**_minimum_payload())
    assert req.company_name == "株式会社サンプル"
    assert req.industry == "製造業"
    assert req.scale == "中小企業"
    assert req.known_info == ""
    assert req.salesperson == ""
    assert req.homepage_url == ""
    assert req.contact_name == ""
    assert req.contact_department == ""
    assert req.contact_position == ""
    assert req.meeting_status == "first"


def test_missing_required_company_name_raises():
    """会社名が無いとバリデーションエラーになること."""
    with pytest.raises(ValidationError):
        GenerateRequest(industry="製造業", scale="中小企業")


def test_camel_case_aliases_are_accepted():
    """フロントエンドが投げる camelCase キーで受けられること."""
    req = GenerateRequest(
        **_minimum_payload(
            homepageUrl="https://example.co.jp",
            contactName="山田太郎",
            contactDepartment="経営企画部",
            contactPosition="部長",
            meetingStatus="followup",
        )
    )
    assert req.homepage_url == "https://example.co.jp"
    assert req.contact_name == "山田太郎"
    assert req.contact_department == "経営企画部"
    assert req.contact_position == "部長"
    assert req.meeting_status == "followup"


def test_meeting_status_literal_rejects_invalid_value():
    """meeting_status は 'first' / 'followup' 以外は拒否されること."""
    with pytest.raises(ValidationError):
        GenerateRequest(**_minimum_payload(meetingStatus="third"))


def test_to_user_message_includes_all_fields():
    """整形済みプロンプトに全 5 項目（HP / 氏名 / 部署 / 役職 / ステータス）が含まれること."""
    req = GenerateRequest(
        **_minimum_payload(
            homepageUrl="https://example.co.jp",
            contactName="山田太郎",
            contactDepartment="経営企画部",
            contactPosition="部長",
            meetingStatus="followup",
            knownInfo="DX 推進中",
            salesperson="佐々木",
        )
    )
    msg = to_user_message(req)
    assert "株式会社サンプル" in msg
    assert "https://example.co.jp" in msg
    assert "山田太郎" in msg
    assert "経営企画部" in msg
    assert "部長" in msg
    assert "2回目以降の面談" in msg
    assert "DX 推進中" in msg
    assert "佐々木" in msg


def test_to_user_message_first_meeting_label():
    """meeting_status='first' のときは「初回面談」と表示されること."""
    req = GenerateRequest(**_minimum_payload())
    msg = to_user_message(req)
    assert "初回面談" in msg
    assert "2回目以降" not in msg


def test_last_meeting_notes_alias_and_default():
    """lastMeetingNotes は camelCase で受けられ、未指定なら空文字になること."""
    req = GenerateRequest(**_minimum_payload())
    assert req.last_meeting_notes == ""
    req2 = GenerateRequest(
        **_minimum_payload(meetingStatus="followup", lastMeetingNotes="前向きな反応")
    )
    assert req2.last_meeting_notes == "前向きな反応"


def test_to_user_message_followup_includes_last_meeting_notes():
    """followup のときは前回面談メモがプロンプトに含まれること."""
    req = GenerateRequest(
        **_minimum_payload(meetingStatus="followup", lastMeetingNotes="RAG 事例を依頼された")
    )
    msg = to_user_message(req)
    assert "前回面談メモ" in msg
    assert "RAG 事例を依頼された" in msg


def test_to_user_message_first_meeting_omits_last_meeting_notes():
    """初回のときは「前回面談メモ」行を出さないこと（前回が存在しないため）."""
    req = GenerateRequest(**_minimum_payload(lastMeetingNotes="無視されるはず"))
    msg = to_user_message(req)
    assert "前回面談メモ" not in msg
    assert "無視されるはず" not in msg


def test_to_user_message_marks_missing_optional_fields():
    """任意項目が空のとき「（未記入）」が出ること."""
    req = GenerateRequest(**_minimum_payload())
    msg = to_user_message(req)
    # HP, 氏名, 部署, 役職, 既知の課題, 担当営業 はすべて未記入
    assert "（未記入）" in msg
