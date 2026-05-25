"""FastAPI 開発サーバーを uvicorn で起動する."""
import sys

import uvicorn

sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    uvicorn.run(
        "agent_first_meeting.api:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
