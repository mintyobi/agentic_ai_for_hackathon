"""API のリクエスト/レスポンス スキーマ."""
from pydantic import BaseModel, ConfigDict, Field


class GenerateRequest(BaseModel):
    """初回面談アポ資料生成のリクエスト."""

    model_config = ConfigDict(populate_by_name=True)

    company_name: str = Field(..., alias="companyName", description="顧客企業名")
    industry: str = Field(..., description="業種")
    scale: str = Field(..., description="企業規模")
    known_info: str = Field(default="", alias="knownInfo", description="既知の課題感など")
    salesperson: str = Field(default="", description="担当営業名")


def to_user_message(req: GenerateRequest) -> str:
    """ユーザー向けプロンプト形式に整形する."""
    return (
        "以下の顧客の初回面談に向けたアポ資料を作ってください。\n\n"
        f"- 会社名：{req.company_name}\n"
        f"- 業種：{req.industry}\n"
        f"- 規模：{req.scale}\n"
        f"- 既知の課題：{req.known_info or '（未記入）'}\n"
        f"- 担当営業：{req.salesperson or '（未記入）'}\n"
    )
