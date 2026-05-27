"""FastAPI アプリ：初回面談エージェントの SSE エンドポイント."""
import json
import logging
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from semantic_kernel.contents import StreamingTextContent
from sse_starlette.sse import EventSourceResponse

from agent_first_meeting.agent import build_agent, build_followup_agent
from agent_first_meeting.config import settings
from agent_first_meeting.logging_config import setup_logging
from agent_first_meeting.schemas import GenerateRequest, to_user_message
from agent_first_meeting.tools.customer_history import CustomerHistoryPlugin
from agent_first_meeting.tools.meeting_record import MeetingRecordPlugin

PPTX_URL_PATTERN = re.compile(r"https://[^\s)\]」]+?\.pptx(?:\?[^\s)\]」]*)?")

# follow-up エージェントが要求するツール（呼ばれないと完了扱いにしない）
REQUIRED_TOOLS_FIRST = {"generate_pptx", "save_meeting_record"}
REQUIRED_TOOLS_FOLLOWUP = {"get_customer_history", "generate_pptx", "save_meeting_record"}

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリ起動時に logging と長寿命プラグインを初期化する.

    NOTE: agent と tracker はリクエスト毎に build する（tracker が state を
    持つため共有不可）。CustomerHistoryPlugin は read-only なので使い回し OK。
    """
    setup_logging(settings.app_log_level)
    logger.info("starting agent-first-meeting api...")
    app.state.history_plugin = CustomerHistoryPlugin()
    logger.info("history plugin initialized")
    yield
    logger.info("shutting down agent-first-meeting api")


app = FastAPI(title="agent-first-meeting", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _sse(event: str, payload: dict) -> dict:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


def _check_followup_precondition(
    history_plugin: CustomerHistoryPlugin, company_name: str
) -> tuple[bool, str | None, int | None]:
    """follow-up モードで前提となる過去面談があるか確認し、直近 round を返す.

    Returns:
        (ok, error_message, latest_round). ok=False のとき error_message に理由。
    """
    history_json = history_plugin.get_customer_history(company_name)
    try:
        history = json.loads(history_json)
    except json.JSONDecodeError as e:
        logger.exception("invalid history json: %s", e)
        return False, "履歴の取得に失敗しました", None
    meetings = history.get("meetings") or []
    if not meetings:
        return False, (
            f"「{company_name}」の過去面談が見つかりません。"
            "「初回」を選択して初回面談を先に実施してください。"
        ), None
    latest_round = max((m.get("round", 0) for m in meetings), default=0)
    return True, None, latest_round


@app.post("/api/first-meeting/generate")
async def generate(req: GenerateRequest) -> EventSourceResponse:
    user_message = to_user_message(req)
    logger.info(
        "generate request: company=%s status=%s",
        req.company_name, req.meeting_status,
    )

    async def event_stream() -> AsyncGenerator[dict, None]:
        # meeting_status をトリガーにしてエージェントを分岐（リクエスト毎に build）
        if req.meeting_status == "followup":
            # 早期 return: 過去面談がなければ followup は意味をなさない
            ok, reason, latest_round = _check_followup_precondition(
                app.state.history_plugin, req.company_name
            )
            if not ok:
                logger.warning("followup precondition failed: %s", reason)
                yield _sse(
                    "done",
                    {
                        "status": "error",
                        "data": None,
                        "error": {"code": "NoPreviousMeeting", "message": reason},
                    },
                )
                return

            # 前回実績メモは「エージェント実行前」に、直近 round を明示してサーバ側で
            # 記録する。LLM の呼び出し順に依存させると、今回作る新レコード（最大 round）
            # に誤って書き込まれて前回実績が確定しなくなるため、ここで決定的に確定させる。
            notes = req.last_meeting_notes.strip()
            if notes:
                yield _sse(
                    "thought",
                    {"text": f"前回面談（round {latest_round}）の実績メモを記録中..."},
                )
                try:
                    MeetingRecordPlugin().record_meeting_outcomes(
                        req.company_name, notes, latest_round or 0
                    )
                    yield _sse("tool_result", {"name": "record_meeting_outcomes"})
                except Exception:  # noqa: BLE001
                    logger.exception("failed to record previous outcomes (continuing)")
                    yield _sse(
                        "thought",
                        {"text": "前回実績メモの記録に失敗しました（処理は継続します）。"},
                    )

            agent, tracker = build_followup_agent()
            agent_label = "2回目以降"
        else:
            agent, tracker = build_agent()
            agent_label = "初回"

        document_url: str | None = None
        accumulated_text = ""

        def _drain_tool_events() -> list[dict]:
            """tracker が記録したツール進捗を SSE 形式に変換して取り出す.

            SK 1.42 の invoke_stream では FunctionCall/Result が stream に流れない
            ため、Filter(ToolResultTracker) が貯めたイベントをここでドレインする。
            """
            drained: list[dict] = []
            while tracker.events:
                ev_type, tool_name = tracker.events.pop(0)
                drained.append(_sse(ev_type, {"name": tool_name}))
            return drained

        try:
            yield _sse("thought", {"text": f"{agent_label}面談エージェントを起動中..."})

            async for chunk in agent.invoke_stream(messages=user_message):
                # ツール呼び出し進捗を流す
                for ev in _drain_tool_events():
                    yield ev
                message = chunk.message
                for item in message.items:
                    if isinstance(item, StreamingTextContent):
                        text = item.text or ""
                        if text:
                            accumulated_text += text
                            yield _sse("message", {"text": text})

            # ループ後に残ったツールイベントを流し切る
            for ev in _drain_tool_events():
                yield ev

            # Filter から確実に document_url / meeting_id / invoked_tools を取得
            document_url = tracker.document_url
            if not document_url:
                # フォールバック: テキストから正規表現で抽出
                match = PPTX_URL_PATTERN.search(accumulated_text)
                if match:
                    document_url = match.group(0)

            warnings: list[str] = []
            required = (
                REQUIRED_TOOLS_FOLLOWUP
                if req.meeting_status == "followup"
                else REQUIRED_TOOLS_FIRST
            )
            missing = required - tracker.invoked_tools
            if missing:
                msg = f"必須ツールが呼ばれませんでした: {sorted(missing)}"
                warnings.append(msg)
                logger.warning(msg)

            # 資料は出たが必須ツールが欠けている場合は "partial"（警告付き完了）。
            # フロントは partial を「生成完了（警告あり）」として表示する。
            if not document_url:
                status = "error"
            elif missing:
                status = "partial"
            else:
                status = "success"

            yield _sse(
                "done",
                {
                    "status": status,
                    "data": {
                        "documentUrl": document_url,
                        "message": accumulated_text,
                        "invokedTools": sorted(tracker.invoked_tools),
                        "meetingId": tracker.meeting_id,
                        "warnings": warnings,
                    },
                    "error": None if document_url else {
                        "code": "NoDocument",
                        "message": "PPTX が生成されませんでした",
                    },
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("agent run failed")
            yield _sse(
                "done",
                {
                    "status": "error",
                    "data": None,
                    "error": {"code": type(e).__name__, "message": str(e)},
                },
            )

    return EventSourceResponse(event_stream())
