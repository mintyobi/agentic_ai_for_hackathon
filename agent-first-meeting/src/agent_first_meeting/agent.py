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

from agent_first_meeting._azure_clients import openai_token_provider
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
    あわせて (event_type, tool_name) を `events` に貯め、API 側が SSE で
    ツール呼び出しの進捗を配信できるようにする。
    """

    def __init__(self) -> None:
        self.invoked_tools: set[str] = set()
        self.document_url: str | None = None
        self.meeting_id: str | None = None
        # SSE で進捗表示するためのイベントキュー。(event_type, tool_name) を貯め、
        # API 側が invoke_stream のチャンク間でドレインして yield する。
        self.events: list[tuple[str, str]] = []

    async def hook(self, context, next):  # noqa: A002 (SK API は kw 名 'next' を要求)
        try:
            fn_name = context.function.name
        except Exception:  # noqa: BLE001
            fn_name = None
        if fn_name:
            self.events.append(("tool", fn_name))
        await next(context)
        if not fn_name:
            return
        self.invoked_tools.add(fn_name)
        self.events.append(("tool_result", fn_name))
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
   - ※ 自社商品スライドと費用スライドはプラグイン側で既定値（config 設定。未設定時はプレースホルダ＝価格は「別途お見積もり」）が入るので指定不要
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


# 2回目以降の面談エージェント。first と同じツール群を共有し、instructions で
# 「前回 outcomes を踏まえた継続提案」に振る舞いを切り替える。
FOLLOWUP_AGENT_INSTRUCTIONS = """\
あなたは営業担当者の **2回目以降** の面談を支援する AI エージェントです。
初回との決定的な違いは「前回までに起きたこと（outcomes）と積み残し（nextActions）を
必ず踏まえ、継続提案として一歩進める」点です。以下の流れで動いてください。

なお「前回面談メモ」は **システム側が既に前回 outcomes として記録済み** です。
あなたは **record_meeting_outcomes を呼ばないでください**（呼ぶと今回作る新しい
レコードに誤って書き込まれます）。前回実績は get_customer_history の outcomes で参照します。

1. **get_customer_history** で過去の取引履歴を必ず取得する
   - meetings 配列が空なら継続提案は成り立たない。
     「初回面談を先に実施してください」と伝えて終了する
   - meetings は round 降順。直近 meeting の round / proposedTitle / outcomes /
     nextActions / preMeetingDocumentUrl を読み取る
   - outcomes も nextActions も無ければ、前回は資料生成のみで実績未確定とみなして
     慎重に提案する

2. 必要に応じて **fetch_url_text** で HP を再取得し、前回からの事業状況の
   変化（新規事業・プレスリリース等）を拾う（URL が無ければ飛ばす）

3. 前回の nextActions を「解決・前進させる」観点で今回の論点を設計する。
   裏付けが欲しければ **search_similar_cases** で追加事例を取得する

4. **generate_pptx** で 6 スライド構成の継続提案資料を生成する
   - **cover_title**: 継続提案だと分かるタイトル。前回テーマからの前進を示す
     （例: 「技能継承 DX 第2次ご提案：PoC から本格導入へ」）
   - **cover_subtitle**: 「<会社名> 様向け / <年月> / 担当: <営業名>（第<round+1>回）」
   - **industry_body**: 前回 outcomes で判明した課題と、その後の業界動向を
     踏まえた残課題・打ち手を 3〜5 行の箇条書き（改行区切り）
   - **position_body**: 前回 nextActions への回答・進捗を、取引相手の役職に
     響く形で 3〜5 行の箇条書き（改行区切り）

5. **save_meeting_record** で今回のレコードを保存する（round は自動採番）
   - next_actions には「今回の面談で確認・合意したい次の一手」を入れる
     （今回の outcomes は面談実施後にシステム側で記録される契約）

6. 最後に営業担当者へ簡潔に報告する
   - 前回（round / テーマ / outcomes）からの差分
   - 今回の継続提案タイトルと、その根拠（前回 nextActions / 参照事例）
   - 生成資料の URL
   - 今回の面談で確認すべきポイント（＝保存した next_actions）
   - 保存された面談レコード ID

ツールは必要なものを自分で判断して呼んでください。
"""


def _build(name: str, instructions: str) -> tuple[ChatCompletionAgent, ToolResultTracker]:
    """両エージェント共通の組み立て処理. agent と tracker をペアで返す."""
    execution_settings = OpenAIChatPromptExecutionSettings(
        function_choice_behavior=FunctionChoiceBehavior.Auto(),
    )

    # キーがあればキー認証、無ければ Entra トークン（Managed Identity）で認証
    chat_kwargs = dict(
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_chat_deployment,
        api_version=settings.azure_openai_api_version,
    )
    token_provider = openai_token_provider()
    if token_provider is None:
        chat_kwargs["api_key"] = settings.azure_openai_api_key
    else:
        chat_kwargs["ad_token_provider"] = token_provider

    agent = ChatCompletionAgent(
        service=AzureChatCompletion(**chat_kwargs),
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
