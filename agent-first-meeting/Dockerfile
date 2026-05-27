# 初回/2回目以降 面談支援エージェント API（FastAPI）コンテナ
# Azure Container Apps 向け。ビルドは `az acr build`（ローカル Docker 不要）想定。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 依存解決に必要なメタ情報＋ソースのみコピーしてインストール
# （.dockerignore で .env / .venv / tests / scripts などは除外）
COPY pyproject.toml ./
COPY src ./src
RUN pip install .

# 非 root 実行（セキュリティ・ハードニング）
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Container Apps の target-port に合わせ 0.0.0.0:8000 で待受
# （scripts/run_server.py は 127.0.0.1 固定なのでコンテナでは uvicorn を直接起動）
CMD ["uvicorn", "agent_first_meeting.api:app", "--host", "0.0.0.0", "--port", "8000"]
