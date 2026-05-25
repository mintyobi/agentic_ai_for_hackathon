"""エージェント単体動作確認スクリプト.

使い方:
  python scripts/run_agent.py            # 新規顧客シナリオ
  python scripts/run_agent.py existing   # 既存顧客シナリオ（履歴あり）
"""
import asyncio
import sys

from agent_first_meeting.agent import build_agent

sys.stdout.reconfigure(encoding="utf-8")


SCENARIOS = {
    "new": (
        "以下の顧客の初回面談に向けたアポ資料を作ってください。\n\n"
        "- 会社名：株式会社サンプル製作所\n"
        "- 業種：製造業\n"
        "- 規模：中小企業\n"
        "- 既知の課題：DX 推進したいが何から手を付けるか不明。"
        "ベテラン技術者の高齢化で技能継承も気がかり。\n"
        "- 担当営業：佐々木\n"
    ),
    "existing": (
        "以下の顧客の初回面談に向けたアポ資料を作ってください。\n\n"
        "- 会社名：株式会社既存お得意様\n"
        "- 業種：製造業\n"
        "- 規模：中小企業\n"
        "- 既知の課題：DX 推進と技能継承\n"
        "- 担当営業：佐々木\n"
    ),
}


async def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "new"
    if scenario not in SCENARIOS:
        print(f"unknown scenario: {scenario}. choose from {list(SCENARIOS)}")
        sys.exit(1)

    # build_agent() は (agent, tracker) のタプルを返す。tracker はここでは未使用。
    agent, _ = build_agent()
    user_input = SCENARIOS[scenario]

    print(f"[scenario] {scenario}")
    print("[input]")
    print(user_input)
    print("---")

    response = await agent.get_response(messages=user_input)
    print("[response]")
    print(response.content)


if __name__ == "__main__":
    asyncio.run(main())
