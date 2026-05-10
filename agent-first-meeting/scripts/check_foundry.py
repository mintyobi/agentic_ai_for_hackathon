"""Foundry 接続のスモークテスト：GPT-4.1 デプロイにメッセージを投げて応答を確認."""
import asyncio
import sys

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

from agent_first_meeting.config import settings

sys.stdout.reconfigure(encoding="utf-8")


async def main() -> None:
    agent = ChatCompletionAgent(
        service=AzureChatCompletion(
            api_key=settings.azure_openai_api_key,
            endpoint=settings.azure_openai_endpoint,
            deployment_name=settings.azure_openai_chat_deployment,
            api_version=settings.azure_openai_api_version,
        ),
        name="SmokeTest",
        instructions="日本語で1文だけ返答してください。",
    )

    response = await agent.get_response(
        messages="こんにちは。Foundry 経由の GPT-4.1 接続テストです。動作確認OKと答えてください。"
    )

    print(f"[endpoint] {settings.azure_openai_endpoint}")
    print(f"[deployment] {settings.azure_openai_chat_deployment}")
    print(f"[api_version] {settings.azure_openai_api_version}")
    print(f"[response] {response.content}")


if __name__ == "__main__":
    asyncio.run(main())
