"""API のリクエスト/レスポンス スキーマ."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_first_meeting.role_classifier import classify_position

MeetingStatus = Literal["first", "followup"]


class GenerateRequest(BaseModel):
    """初回面談アポ資料生成のリクエスト."""

    model_config = ConfigDict(populate_by_name=True)

    company_name: str = Field(..., alias="companyName", description="顧客企業名")
    industry: str = Field(..., description="業種")
    scale: str = Field(..., description="企業規模")
    known_info: str = Field(default="", alias="knownInfo", description="既知の課題感など")
    salesperson: str = Field(default="", description="担当営業名")

    # Phase 2 追加：顧客 HP と取引相手の詳細
    homepage_url: str = Field(
        default="",
        alias="homepageUrl",
        description="顧客企業の公式 HP URL。WebFetchPlugin で本文を取得して提案の根拠に使う。",
    )
    contact_name: str = Field(
        default="",
        alias="contactName",
        description="取引相手の氏名（例: 山田太郎）",
    )
    contact_department: str = Field(
        default="",
        alias="contactDepartment",
        description="取引相手の部署（例: 経営企画部）",
    )
    contact_position: str = Field(
        default="",
        alias="contactPosition",
        description="取引相手の役職（例: 部長）",
    )
    meeting_status: MeetingStatus = Field(
        default="first",
        alias="meetingStatus",
        description="面談ステータス。'first' = 初回、'followup' = 2回目以降。",
    )

    # follow-up 用：前回面談で実際に何が起きたか（outcomes 記録の入力）
    last_meeting_notes: str = Field(
        default="",
        alias="lastMeetingNotes",
        description=(
            "（followup 時）前回面談の実績・反応・所感のメモ。"
            "記入されていれば record_meeting_outcomes で前回 meeting の outcomes として保存され、"
            "今回の継続提案の根拠になる。"
        ),
    )


def to_user_message(req: GenerateRequest) -> str:
    """ユーザー向けプロンプト形式に整形する."""
    status_label = "初回面談" if req.meeting_status == "first" else "2回目以降の面談"
    position_category = classify_position(req.contact_position)
    position_category_text = (
        f"{position_category}（バックエンド側で自動分類）"
        if position_category
        else "不明（役職表記から判定できなかったので、あなたが判断してください）"
    )
    today = datetime.now().strftime("%Y年%m月%d日")
    message = (
        f"以下の顧客の{status_label}に向けたアポ資料を作ってください。\n\n"
        f"- 本日の日付：{today}（表紙やサブタイトルの年月はこの日付を基準にすること）\n"
        f"- 会社名：{req.company_name}\n"
        f"- 業種：{req.industry}\n"
        f"- 規模：{req.scale}\n"
        f"- 公式 HP：{req.homepage_url or '（未記入）'}\n"
        f"- 取引相手：{req.contact_name or '（未記入）'}"
        f"（部署：{req.contact_department or '（未記入）'} / "
        f"役職：{req.contact_position or '（未記入）'}）\n"
        f"- 取引相手の役職カテゴリ：{position_category_text}\n"
        f"- 既知の課題：{req.known_info or '（未記入）'}\n"
        f"- 担当営業：{req.salesperson or '（未記入）'}\n"
        f"- 面談ステータス：{status_label}\n"
    )
    # follow-up のときだけ「前回面談メモ」を渡す（初回には存在しない情報なので出さない）。
    # メモはサーバ側で既に前回 outcomes として記録済みなので、ここでは提案の素材として渡す。
    if req.meeting_status == "followup":
        message += (
            f"- 前回面談メモ（※システムが前回 outcomes として記録済み）："
            f"{req.last_meeting_notes or '（未記入）'}\n"
        )
    return message
