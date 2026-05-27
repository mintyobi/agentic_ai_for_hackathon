"""`.env` から読み込むアプリケーション設定."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Azure AI Foundry / Azure OpenAI
    # api_key は空なら Managed Identity（DefaultAzureCredential）に自動フォールバック
    azure_openai_endpoint: str
    azure_openai_api_key: str | None = None
    azure_openai_chat_deployment: str = "gpt-4.1"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    azure_openai_api_version: str = "2024-12-01-preview"

    # Azure Cosmos DB
    # key は空なら Managed Identity（データプレーン RBAC）に自動フォールバック
    cosmos_endpoint: str
    cosmos_key: str | None = None
    cosmos_database: str = "sales-agent"

    # Azure Blob Storage
    blob_account_url: str
    blob_container: str = "generated-documents"
    blob_account_key: str | None = None  # 空なら DefaultAzureCredential を使う

    # 提案資料の「自社商品 / 費用」スライドに入れる値。
    # 既定はプレースホルダ（価格 0 = 「別途お見積もり」）にしてあり、
    # 実際の商品・価格は .env で上書きする。コードに偽の金額を埋め込まない。
    default_product_name: str = "弊社ソリューション"
    default_product_price_jpy: int = 0

    # 顧客HP取得ツールの有効/無効。公開デプロイでプロンプトインジェクション経路を
    # 完全に断ちたい場合は false にする（エージェントから fetch ツールを外す）。
    web_fetch_enabled: bool = True

    # App
    app_log_level: str = "INFO"
    # CORS で受け付けるオリジン（カンマ区切り）。本番では Streamlit / フロントの
    # 実ドメインに絞ること。"*" を入れると wildcard 許可（開発時のみ推奨）。
    cors_allow_origins: str = "http://localhost:8501,http://127.0.0.1:8501"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


settings = Settings()
