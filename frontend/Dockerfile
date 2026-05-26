# 営業支援エージェント Streamlit フロントエンド（Azure Container Apps 向け）
# Easy Auth(Entra) の背後・external ingress で公開する想定。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install streamlit httpx
COPY main.py ./

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8501

# リバースプロキシ(Container Apps ingress + Easy Auth)の背後で動かすため
# headless / 0.0.0.0 / CORS・XSRF はプロキシ前提で無効化（アクセス制御は Easy Auth が担う）
CMD ["streamlit", "run", "main.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", "--browser.gatherUsageStats=false"]
