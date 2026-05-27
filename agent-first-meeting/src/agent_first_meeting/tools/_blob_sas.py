"""Blob のダウンロード URL（SAS 署名）を発行する共有ヘルパ.

`document_gen.py`（生成時）と `customer_history.py`（履歴読み出し時の再署名）で
共用する。SAS トークンは時限なので、永続データには blob 名だけを保存し、
URL は読み出すたびにここで再発行する設計にすることで「保存した URL が失効して
401 になる」問題を避ける。
"""
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlparse

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    UserDelegationKey,
    generate_blob_sas,
)

from agent_first_meeting.config import settings

logger = logging.getLogger(__name__)

SAS_EXPIRY_HOURS = 24
# User delegation key は最大 7 日有効。キャッシュして再利用し、
# 有効期限の少し前に再取得することで Managed Identity のロール変更にも追従する。
_DELEGATION_KEY_TTL_HOURS = 24
_DELEGATION_KEY_REFRESH_MARGIN = timedelta(minutes=10)


def make_blob_service_client() -> BlobServiceClient:
    """account key があればキー認証、無ければ DefaultAzureCredential で接続する."""
    if settings.blob_account_key:
        return BlobServiceClient(
            account_url=settings.blob_account_url,
            credential=settings.blob_account_key,
        )
    return BlobServiceClient(
        account_url=settings.blob_account_url,
        credential=DefaultAzureCredential(),
    )


def extract_blob_name(url: str) -> str | None:
    """SAS/クエリ付きの Blob URL から blob 名（コンテナ以下のパス）を取り出す.

    例: https://acct.blob.core.windows.net/generated-documents/proposals/x.pptx?sig=...
        -> "proposals/x.pptx"
    コンテナ配下でなければ None。
    """
    if not url:
        return None
    path = urlparse(url).path  # /{container}/proposals/x.pptx
    prefix = f"/{settings.blob_container}/"
    if path.startswith(prefix):
        return unquote(path[len(prefix):])
    return None


class BlobSasSigner:
    """blob 名から時限ダウンロード URL を発行する. delegation key を短期キャッシュ."""

    def __init__(self, service_client: BlobServiceClient | None = None) -> None:
        self._svc = service_client or make_blob_service_client()
        self._delegation_key: UserDelegationKey | None = None
        self._delegation_key_expiry: datetime | None = None

    def _get_user_delegation_key(self) -> UserDelegationKey:
        now = datetime.now(timezone.utc)
        if (
            self._delegation_key is not None
            and self._delegation_key_expiry is not None
            and now + _DELEGATION_KEY_REFRESH_MARGIN < self._delegation_key_expiry
        ):
            return self._delegation_key

        start = now - timedelta(minutes=5)  # クロックスキュー吸収
        expiry = now + timedelta(hours=_DELEGATION_KEY_TTL_HOURS)
        self._delegation_key = self._svc.get_user_delegation_key(
            key_start_time=start,
            key_expiry_time=expiry,
        )
        self._delegation_key_expiry = expiry
        logger.info(
            "BlobSasSigner: refreshed user delegation key, expires=%s",
            expiry.isoformat(),
        )
        return self._delegation_key

    def sign_blob_name(self, blob_name: str) -> str:
        """blob 名に対して読み取り専用の SAS 付き URL を発行する."""
        blob_client = self._svc.get_blob_client(
            container=settings.blob_container, blob=blob_name
        )
        common_kwargs = dict(
            account_name=self._svc.account_name,
            container_name=settings.blob_container,
            blob_name=blob_name,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=SAS_EXPIRY_HOURS),
        )
        if settings.blob_account_key:
            sas_token = generate_blob_sas(
                **common_kwargs,
                account_key=settings.blob_account_key,
            )
        else:
            sas_token = generate_blob_sas(
                **common_kwargs,
                user_delegation_key=self._get_user_delegation_key(),
            )
        return f"{blob_client.url}?{sas_token}"
