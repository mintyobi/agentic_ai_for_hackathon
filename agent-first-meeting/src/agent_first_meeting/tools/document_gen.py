"""PowerPoint 生成プラグイン (python-pptx + Azure Blob).

Phase 3: 表紙 / 目次 / 対業界向け / 役職向け / 自社商品 / 費用 の 6 スライド構成。
PPTX 組み立て本体は `_pptx_builder.build_presentation_bytes` に分離。
Blob アップロードと SAS 発行は `_blob_sas` に分離。本ファイルは両者の接続に専念する。
"""
import logging
import uuid
from typing import Annotated

from semantic_kernel.functions import kernel_function

from agent_first_meeting.config import settings
from agent_first_meeting.tools._blob_sas import (
    BlobSasSigner,
    make_blob_service_client,
)
from agent_first_meeting.tools._pptx_builder import build_presentation_bytes

logger = logging.getLogger(__name__)


class DocumentGenPlugin:
    """6 スライド構成の PowerPoint を生成し Blob にアップロードする SK プラグイン."""

    def __init__(self) -> None:
        svc = make_blob_service_client()
        self._signer = BlobSasSigner(svc)
        self._container = svc.get_container_client(settings.blob_container)

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
            product_name=settings.default_product_name,
            product_price_jpy=settings.default_product_price_jpy,
        )

        blob_name = f"proposals/{uuid.uuid4().hex}.pptx"
        blob_client = self._container.get_blob_client(blob_name)
        blob_client.upload_blob(pptx_bytes, overwrite=True)
        # 即時ダウンロード用に時限 SAS 付き URL を返す（永続保存は meeting_record 側で blob 名に正規化）
        return self._signer.sign_blob_name(blob_name)
