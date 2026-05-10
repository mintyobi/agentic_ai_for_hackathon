"""PowerPoint 生成プラグイン (python-pptx + Azure Blob)."""
import uuid
from io import BytesIO
from typing import Annotated

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from pptx import Presentation
from semantic_kernel.functions import kernel_function

from agent_first_meeting.config import settings


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
    """表紙 1 枚の PowerPoint を生成し Blob にアップロードする SK プラグイン."""

    def __init__(self) -> None:
        self._container = _make_blob_service_client().get_container_client(
            settings.blob_container
        )

    @kernel_function(
        description=(
            "表紙だけの初回提案資料 (PowerPoint) を生成し、"
            "Azure Blob にアップロードしてダウンロード可能な URL を返す。"
        ),
    )
    def generate_pptx(
        self,
        title: Annotated[
            str,
            "表紙のメインタイトル。例: '製造業のDX：技能継承課題への AI ナレッジ活用ご提案'",
        ],
        subtitle: Annotated[
            str,
            "表紙のサブタイトル。例: '株式会社サンプル製作所 様向け / 2026年5月'",
        ] = "",
    ) -> Annotated[str, "生成された PowerPoint の Blob URL."]:
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = title
        slide.placeholders[1].text = subtitle

        buf = BytesIO()
        prs.save(buf)

        blob_name = f"proposals/{uuid.uuid4().hex}.pptx"
        blob_client = self._container.get_blob_client(blob_name)
        blob_client.upload_blob(buf.getvalue(), overwrite=True)
        return blob_client.url
