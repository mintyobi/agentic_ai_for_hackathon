"""FastAPI アプリ：初回面談エージェントの SSE エンドポイント."""
import json
import re
from typing import AsyncGenerator

PPTX_URL_PATTERN = re.compile(r"https://[^\s)\]」]+?\.pptx(?:\?[^\s)\]」]*)?")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from semantic_kernel.contents import (
    FunctionCallContent,
    FunctionResultContent,
    StreamingTextContent,
)
from sse_starlette.sse import EventSourceResponse

from agent_first_meeting.agent import build_agent
from agent_first_meeting.schemas import GenerateRequest, to_user_message

app = FastAPI(title="agent-first-meeting", version="0.1.0")

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


@app.post("/api/first-meeting/generate")
async def generate(req: GenerateRequest) -> EventSourceResponse:
    user_message = to_user_message(req)

    async def event_stream() -> AsyncGenerator[dict, None]:
        agent = build_agent()
        document_url: str | None = None
        accumulated_text = ""

        try:
            yield _sse("thought", {"text": "エージェントを起動中..."})

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
                        if item.function_name and "generate_pptx" in item.function_name:
                            document_url = result_str
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

            if not document_url:
                match = PPTX_URL_PATTERN.search(accumulated_text)
                if match:
                    document_url = match.group(0)

            yield _sse(
                "done",
                {
                    "status": "success",
                    "data": {
                        "documentUrl": document_url,
                        "message": accumulated_text,
                    },
                    "error": None,
                },
            )
        except Exception as e:  # noqa: BLE001
            yield _sse(
                "done",
                {
                    "status": "error",
                    "data": None,
                    "error": {"code": type(e).__name__, "message": str(e)},
                },
            )

    return EventSourceResponse(event_stream())
