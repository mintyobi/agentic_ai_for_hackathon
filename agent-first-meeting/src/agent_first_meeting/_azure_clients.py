"""Azure クライアント生成: キー（ローカル .env）か Managed Identity（Container Apps）を自動選択.

`settings` にキーがあればキー認証を優先し、無ければ `DefaultAzureCredential`
（Container Apps では Managed Identity）にフォールバックする。これにより
**同じイメージ**をローカル（キー）とクラウド（MI）の両方でそのまま動かせる。

- Cosmos: `make_cosmos_client()`
- Azure OpenAI（同期クライアント）: `make_azure_openai()`
- semantic-kernel など自前で OpenAI クライアントを組む側: `openai_token_provider()`
"""
from collections.abc import Callable

from azure.cosmos import CosmosClient

from agent_first_meeting.config import settings

# Azure OpenAI / Cognitive Services 用の AAD スコープ
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"

# Cosmos が返すシステム項目（API レスポンスや再 upsert からは除外する）
INTERNAL_FIELDS = frozenset({"_rid", "_self", "_etag", "_attachments", "_ts"})


def strip_internal(item: dict) -> dict:
    """Cosmos ドキュメントからシステム項目（_rid 等）を除いた dict を返す."""
    return {k: v for k, v in item.items() if k not in INTERNAL_FIELDS}

_credential = None


def _get_credential():
    """DefaultAzureCredential を遅延生成して使い回す（生成コストとトークンキャッシュのため）."""
    global _credential
    if _credential is None:
        from azure.identity import DefaultAzureCredential

        _credential = DefaultAzureCredential()
    return _credential


def make_cosmos_client() -> CosmosClient:
    """Cosmos クライアント. キーがあればキー、無ければ Managed Identity."""
    if settings.cosmos_key:
        return CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
    return CosmosClient(settings.cosmos_endpoint, credential=_get_credential())


def openai_token_provider() -> Callable[[], str] | None:
    """OpenAI 用の Entra トークンプロバイダ. キーがあるとき（=キー認証）は None を返す."""
    if settings.azure_openai_api_key:
        return None
    from azure.identity import get_bearer_token_provider

    return get_bearer_token_provider(_get_credential(), COGNITIVE_SCOPE)


def make_azure_openai():
    """同期 AzureOpenAI クライアント. キーがあればキー、無ければ MI トークンプロバイダ."""
    from openai import AzureOpenAI

    common = dict(
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )
    if settings.azure_openai_api_key:
        return AzureOpenAI(api_key=settings.azure_openai_api_key, **common)
    return AzureOpenAI(azure_ad_token_provider=openai_token_provider(), **common)
