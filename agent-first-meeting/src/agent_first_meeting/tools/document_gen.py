"""PowerPoint 生成プラグイン (python-pptx + Azure Blob).

Phase 3: 表紙 / 目次 / 対業界向け / 役職向け / 自社商品 / 費用 の 6 スライド構成。
PPTX 組み立て本体は `_pptx_builder.build_presentation_bytes` に分離。
本ファイルは「Blob アップロードと SAS 発行」に専念する。
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobClient,
    BlobSasPermissions,
    BlobServiceClient,
    UserDelegationKey,
    generate_blob_sas,
)
from semantic_kernel.functions import kernel_function

from agent_first_meeting.config import settings
from agent_first_meeting.tools._pptx_builder import build_presentation_bytes

logger = logging.getLogger(__name__)

SAS_EXPIRY_HOURS = 24
# User delegation key は最大 7 日有効。
# キャッシュして再利用し、有効期限の少し前に再取得する。
_DELEGATION_KEY_TTL_HOURS = 24
_DELEGATION_KEY_REFRESH_MARGIN = timedelta(minutes=10)


def _make_blob_service_client() -> BlobServiceClient:
    if settings.blob_account_key:
        return BlobServiceClient(
            account_url=settings.blob_account_url,
            credential=settings.blob_account_key,
        )
    return BlobServiceClient(
        account_url=settings.blob_account_url,
        credential=DefaultAzureCredential(),
    )


class DocumentGenPlugin:
    """6 スライド構成の PowerPoint を生成し Blob にアップロードする SK プラグイン."""

    def __init__(self) -> None:
        self._blob_service = _make_blob_service_client()
        self._container = self._blob_service.get_container_client(
            settings.blob_container
        )
        # Managed Identity 経路で user delegation SAS を発行するときの key キャッシュ
        self._delegation_key: UserDelegationKey | None = None
        self._delegation_key_expiry: datetime | None = None

    def _get_user_delegation_key(self) -> UserDelegationKey:
        """user delegation key を取得（短期キャッシュ付き）.

        TTL いっぱいに長く保持すると Managed Identity のロール剥奪に追従できない
        ため、_DELEGATION_KEY_TTL_HOURS で再取得して常に新しいキーを使う。
        """
        now = datetime.now(timezone.utc)
        if (
            self._delegation_key is not None
            and self._delegation_key_expiry is not None
            and now + _DELEGATION_KEY_REFRESH_MARGIN < self._delegation_key_expiry
        ):
            return self._delegation_key

        start = now - timedelta(minutes=5)  # クロックスキュー吸収
        expiry = now + timedelta(hours=_DELEGATION_KEY_TTL_HOURS)
        self._delegation_key = self._blob_service.get_user_delegation_key(
            key_start_time=start,
            key_expiry_time=expiry,
        )
        self._delegation_key_expiry = expiry
        logger.info(
            "DocumentGenPlugin: refreshed user delegation key, expires=%s",
            expiry.isoformat(),
        )
        return self._delegation_key

    def _build_download_url(self, blob_client: BlobClient) -> str:
        """アップロードした Blob のダウンロード URL を返す.

        - blob_account_key がある場合：account-key SAS を付与した時限 URL
        - 無い場合（Managed Identity / DefaultAzureCredential 想定）：
          user delegation key ベースの SAS を発行する。素の Blob URL を返すと
          匿名アクセスがコンテナで無効化されているケースで 401 になる。
        """
        common_kwargs = dict(
            account_name=self._blob_service.account_name,
            container_name=settings.blob_container,
            blob_name=blob_client.blob_name,
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

    @kernel_function(
        description=(
            "6 スライド構成の初回提案資料 (PowerPoint) を生成し、"
            "Azure Blob にアップロードしてダウンロード可能な URL を返す。"
            "スライド構成は固定で「表紙 / 目次 / 業界向け / 役職向け / 自社商品 / 費用」。"
            "自社商品と費用の中身は呼び出し側では指定不要（既定値あり）。"
        ),
    )
    def generate_pptx(
        self,
        cover_title: Annotated[
            str,
            "表紙のメインタイトル。例: '製造業のDX：技能継承課題への AI ナレッジ活用ご提案'",
        ],
        cover_subtitle: Annotated[
            str,
            "表紙のサブタイトル。例: '株式会社サンプル製作所 様向け / 2026年5月 / 担当: 佐々木'",
        ],
        industry_body: Annotated[
            str,
            (
                "「業界トレンドとお客様の課題」スライドの本文。"
                "顧客の業界に共通する潮流・課題感を 3〜5 行の箇条書きで。"
                "改行ごとに 1 つの箇条書き項目になる。"
            ),
        ],
        position_body: Annotated[
            str,
            (
                "「ご担当者向けのご提案」スライドの本文。"
                "取引相手の役職（経営層 / 部門責任者 / 担当者）に響く論点を 3〜5 行の箇条書きで。"
                "改行ごとに 1 つの箇条書き項目になる。"
            ),
        ],
    ) -> Annotated[str, "生成された PowerPoint の Blob URL."]:
        pptx_bytes = build_presentation_bytes(
            cover_title=cover_title,
            cover_subtitle=cover_subtitle,
            industry_body=industry_body,
            position_body=position_body,
            # product / cost は固定値（Phase 3 ではダミー）
        )

        blob_name = f"proposals/{uuid.uuid4().hex}.pptx"
        blob_client = self._container.get_blob_client(blob_name)
        blob_client.upload_blob(pptx_bytes, overwrite=True)
        return self._build_download_url(blob_client)
