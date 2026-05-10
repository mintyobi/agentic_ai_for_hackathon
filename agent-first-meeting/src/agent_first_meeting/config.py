"""`.env` から読み込むアプリケーション設定."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Azure AI Foundry / Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_chat_deployment: str = "gpt-4.1"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    azure_openai_api_version: str = "2024-12-01-preview"

    # Azure Cosmos DB
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "sales-agent"

    # Azure Blob Storage
    blob_account_url: str
    blob_container: str = "generated-documents"

    # App
    app_log_level: str = "INFO"


settings = Settings()
