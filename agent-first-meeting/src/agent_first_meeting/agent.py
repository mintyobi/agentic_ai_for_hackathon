"""初回面談 / 2回目以降の面談エージェントのファクトリ."""
import logging

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.filters import FilterTypes
from semantic_kernel.functions import KernelArguments

from agent_first_meeting.config import settings
from agent_first_meeting.tools.case_search import CaseSearchPlugin
from agent_first_meeting.tools.customer_history import CustomerHistoryPlugin
from agent_first_meeting.tools.document_gen import DocumentGenPlugin
from agent_first_meeting.tools.meeting_record import MeetingRecordPlugin
from agent_first_meeting.tools.web_fetch import WebFetchPlugin

logger = logging.getLogger(__name__)


class ToolResultTracker:
    """エージェントが呼んだツールと、特定のツール結果を集める Filter.

    SK 1.42 の `invoke_stream` では FunctionCallContent / FunctionResultContent
    が streaming items として流れない（最終テキスト応答のみ流れる）ため、
    Filter で kernel function 呼び出しをフックして必要な結果を集める。
    """

    def __init__(self) -> None:
        self.invoked_tools: set[str] = set()
        self.document_url: str | None = None
        self.meeting_id: str | None = None

    async def hook(self, context, next):  # noqa: A002 (SK API は kw 名 'next' を要求)
        await next(context)
        try:
            fn_name = context.function.name
        except Exception:  # noqa: BLE001
            return
        self.invoked_tools.add(fn_name)
        try:
            result_obj = context.result
            # SK の FunctionResult は .value 経由でアクセス
            val = None
            if result_obj is not None:
                if hasattr(result_obj, "value"):
                    val = result_obj.value
                else:
                    val = result_obj
                # FunctionResult.value がリストの場合もある
                if isinstance(val, list) and val:
                    val = val[0]
                val_str = str(val) if val is not None else None
            else:
                val_str = None
            if fn_name == "generate_pptx" and val_str:
                self.document_url = val_str
                logger.info("ToolResultTracker: captured document_url len=%d", len(val_str))
            elif fn_name == "save_meeting_record" and val_str:
                self.meeting_id = val_str
                logger.info("ToolResultTracker: captured meeting_id=%s", val_str)
        except Exception:  # noqa: BLE001
            logger.exception("ToolResultTracker: failed to extract result")


FIRST_AGENT_INSTRUCTIONS = """\
あなたは営業担当者の初回面談を支援する AI エージェントです。
顧客情報を受け取ったら、以下の流れで動いてください。

1. **get_customer_history** で過去の取引履歴を確認する
   - 既存顧客の場合は前回までの outcomes / nextActions を踏まえて提案を組み立てる
   - 新規顧客（customer=null）の場合は次のステップへ
2. 顧客情報に「公式 HP」の URL が含まれている場合は **fetch_url_text** で
   HP 本文を取得し、事業内容・サービス・直近ニュースから業界課題を推定する。
   （URL が未記入なら飛ばしてよい）
   返り値は JSON 文字列で {ok: bool, ...} の形。ok=false なら text として
   利用してはならず、HP 情報なしで進める。
3. **search_similar_cases** で社内に蓄積された類似事例を最大 3 件取得する
   （クエリは顧客の業界・規模・課題感を含めた自然文で組み立ててください）
4. 顧客情報・履歴・HP・類似事例を踏まえて、6 スライド構成の提案資料の素材を組み立てる
   - **cover_title**: 顧客の業界・規模・課題感が伝わる表紙タイトル。類似事例の成果に触れると説得力が増す
   - **cover_subtitle**: 「<会社名> 様向け / <年月> / 担当: <営業名>」の形式
   - **industry_body**: 業界トレンドと顧客の課題を 3〜5 行の箇条書き（1 行 = 1 項目、改行区切り）
   - **position_body**: 取引相手の役職（経営層 / 部門責任者 / 担当者）に響く論点を 3〜5 行の箇条書き
   - ※ 自社商品スライドと費用スライドはプラグイン側で固定値（テスト商品 / 10 円）が入るので指定不要
5. **generate_pptx** で 6 スライド（表紙 / 目次 / 業界向け / 役職向け / 自社商品 / 費用）の提案資料を作成する
6. **save_meeting_record** で生成資料と次回アクションを meetings コンテナに保存する
   （これが follow-up エージェントへの引き継ぎ点）
7. 最後にユーザー（営業担当者）に向けて、以下を簡潔にレポートする
   - 履歴の有無（新規 or 既存）と参照した過去面談の概要（あれば）
   - HP 取得の有無と推定した事業特性（取得した場合）
   - 生成した資料の URL
   - 提案タイトルとその根拠（参照した事例）
   - 初回面談で確認すべきポイント
   - 保存された面談レコード ID

ツールは必要なものを自分で判断して呼んでください。
"""


# Phase 2 スケルトン：2回目以降の面談エージェント。
# 中身は first と同じツール群を持つが、instructions だけ差し替えている。
# 本実装は Phase 3 以降で詰める。
FOLLOWUP_AGENT_INSTRUCTIONS = """\
あなたは営業担当者の **2回目以降** の面談を支援する AI エージェントです。
初回面談との違いは「前回までの outcomes と nextActions を必ず踏まえる」点です。

1. **get_customer_history** で過去の取引履歴を必ず取得する
   - meetings 配列が空なら、ユーザーに「初回面談を先に実施してください」と返して終了
   - 直近の meeting の outcomes / nextActions を抽出する
2. 必要に応じて **fetch_url_text** で HP を再取得（事業状況に変化がないか確認）
3. 前回の nextActions を解決する提案を組み立て、必要なら
   **search_similar_cases** で追加事例を取得
4. **generate_pptx** で 6 スライド構成の継続提案資料を生成する。
   industry_body / position_body は前回 outcomes を踏まえた論点で組み立てる。
5. **save_meeting_record** で本回のレコードを保存（round は自動採番）
6. ユーザーに対し、前回からの差分・今回の論点・次回アクションを報告

※ このプロンプトは Phase 2 スケルトン。Phase 3 以降で本格的な
継続提案ロジックに差し替える前提です。
"""


def _build(name: str, instructions: str) -> tuple[ChatCompletionAgent, ToolResultTracker]:
    """両エージェント共通の組み立て処理. agent と tracker をペアで返す."""
    execution_settings = OpenAIChatPromptExecutionSettings(
        function_choice_behavior=FunctionChoiceBehavior.Auto(),
    )

    agent = ChatCompletionAgent(
        service=AzureChatCompletion(
            api_key=settings.azure_openai_api_key,
            endpoint=settings.azure_openai_endpoint,
            deployment_name=settings.azure_openai_chat_deployment,
            api_version=settings.azure_openai_api_version,
        ),
        name=name,
        instructions=instructions,
        plugins=[
            CustomerHistoryPlugin(),
            CaseSearchPlugin(),
            WebFetchPlugin(),
            DocumentGenPlugin(),
            MeetingRecordPlugin(),
        ],
        arguments=KernelArguments(settings=execution_settings),
    )

    # Filter を kernel に登録して、ツール呼び出しの結果をフックする
    tracker = ToolResultTracker()
    agent.kernel.add_filter(FilterTypes.FUNCTION_INVOCATION, tracker.hook)
    return agent, tracker


def build_agent() -> tuple[ChatCompletionAgent, ToolResultTracker]:
    """初回面談エージェント. (agent, tracker) を返す."""
    return _build("FirstMeetingAgent", FIRST_AGENT_INSTRUCTIONS)


def build_followup_agent() -> tuple[ChatCompletionAgent, ToolResultTracker]:
    """2回目以降の面談エージェント（Phase 2 スケルトン）. (agent, tracker) を返す."""
    return _build("FollowupMeetingAgent", FOLLOWUP_AGENT_INSTRUCTIONS)
