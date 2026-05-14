"""FastAPI アプリ：初回面談エージェントの SSE エンドポイント."""
import json
import logging
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from semantic_kernel.contents import (
    FunctionCallContent,
    FunctionResultContent,
    StreamingTextContent,
)
from sse_starlette.sse import EventSourceResponse

from agent_first_meeting.agent import build_agent, build_followup_agent
from agent_first_meeting.config import settings
from agent_first_meeting.logging_config import setup_logging
from agent_first_meeting.schemas import GenerateRequest, to_user_message
from agent_first_meeting.tools.customer_history import CustomerHistoryPlugin

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
    allow_origins=["*"],
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
) -> tuple[bool, str | None]:
    """follow-up モードで前提となる過去面談があるか確認する.

    Returns:
        (ok, error_message). ok=False のとき error_message に理由が入る。
    """
    history_json = history_plugin.get_customer_history(company_name)
    try:
        history = json.loads(history_json)
    except json.JSONDecodeError as e:
        logger.exception("invalid history json: %s", e)
        return False, "履歴の取得に失敗しました"
    meetings = history.get("meetings") or []
    if not meetings:
        return False, (
            f"「{company_name}」の過去面談が見つかりません。"
            "「初回」を選択して初回面談を先に実施してください。"
        )
    return True, None


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
            ok, reason = _check_followup_precondition(
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
            agent, tracker = build_followup_agent()
            agent_label = "2回目以降"
        else:
            agent, tracker = build_agent()
            agent_label = "初回"

        document_url: str | None = None
        accumulated_text = ""

        try:
            yield _sse("thought", {"text": f"{agent_label}面談エージェントを起動中..."})

            async for chunk in agent.invoke_stream(messages=user_message):
                message = chunk.message
                for item in message.items:
                    if isinstance(item, FunctionCallContent):
                        yield _sse(
                            "tool",
                            {
                                "name": item.function_name,
                                "args": item.arguments or "",
                            },
                        )
                    elif isinstance(item, FunctionResultContent):
                        result_str = str(item.result)
                        yield _sse(
                            "tool_result",
                            {
                                "name": item.function_name,
                                "result": result_str[:300],
                            },
                        )
                    elif isinstance(item, StreamingTextContent):
                        text = item.text or ""
                        if text:
                            accumulated_text += text
                            yield _sse("message", {"text": text})

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

            yield _sse(
                "done",
                {
                    "status": "success" if document_url else "error",
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
