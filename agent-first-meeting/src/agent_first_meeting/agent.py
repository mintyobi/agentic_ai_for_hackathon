"""初回面談エージェントのファクトリ."""
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.functions import KernelArguments

from agent_first_meeting.config import settings
from agent_first_meeting.tools.case_search import CaseSearchPlugin
from agent_first_meeting.tools.document_gen import DocumentGenPlugin


AGENT_INSTRUCTIONS = """\
あなたは営業担当者の初回面談を支援する AI エージェントです。
顧客情報を受け取ったら、以下の流れで動いてください。

1. search_similar_cases ツールで、社内に蓄積された類似事例を最大 3 件取得する
   （クエリは顧客の業界・規模・課題感を含めた自然文で組み立ててください）
2. 顧客情報と取得した事例を踏まえ、初回提案資料の表紙タイトルを 1 つ考案する
   - 顧客の業界・規模・課題感が伝わる
   - 類似事例の成果（例: 30%効率化）に触れると説得力が増す
3. generate_pptx ツールで表紙だけの提案資料を作成する
4. 最後にユーザー（営業担当者）に向けて、以下を簡潔にレポートする
   - 生成した資料の URL
   - 提案タイトルとその根拠（参照した事例）
   - 初回面談で確認すべきポイントの提案

ツールは必要なものを自分で判断して呼んでください。
"""


def build_agent() -> ChatCompletionAgent:
    """auto function calling 有効化済みの ChatCompletionAgent を返す."""
    execution_settings = OpenAIChatPromptExecutionSettings(
        function_choice_behavior=FunctionChoiceBehavior.Auto(),
    )

    return ChatCompletionAgent(
        service=AzureChatCompletion(
            api_key=settings.azure_openai_api_key,
            endpoint=settings.azure_openai_endpoint,
            deployment_name=settings.azure_openai_chat_deployment,
            api_version=settings.azure_openai_api_version,
        ),
        name="FirstMeetingAgent",
        instructions=AGENT_INSTRUCTIONS,
        plugins=[CaseSearchPlugin(), DocumentGenPlugin()],
        arguments=KernelArguments(settings=execution_settings),
    )
