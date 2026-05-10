"""エージェントを単体起動して end-to-end 動作確認するスクリプト (Step 9)."""
import asyncio
import sys

from agent_first_meeting.agent import build_agent

sys.stdout.reconfigure(encoding="utf-8")


SAMPLE_INPUT = """\
以下の顧客の初回面談に向けたアポ資料を作ってください。

- 会社名：株式会社サンプル製作所
- 業種：製造業
- 規模：中小企業
- 既知の課題：DX 推進したいが何から手を付けるか不明。
  ベテラン技術者の高齢化で技能継承も気がかり。
- 担当営業：ともや
"""


async def main() -> None:
    agent = build_agent()

    print("[input]")
    print(SAMPLE_INPUT)
    print("---")

    response = await agent.get_response(messages=SAMPLE_INPUT)
    print("[response]")
    print(response.content)


if __name__ == "__main__":
    asyncio.run(main())
