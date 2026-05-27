"""顧客情報・面談履歴の取得プラグイン (Cosmos DB)."""
import json
import logging
from typing import Annotated

from semantic_kernel.functions import kernel_function

from agent_first_meeting._azure_clients import make_cosmos_client, strip_internal
from agent_first_meeting.config import settings
from agent_first_meeting.tools._blob_sas import BlobSasSigner, extract_blob_name

logger = logging.getLogger(__name__)

class CustomerHistoryPlugin:
    """`customers` / `meetings` コンテナから顧客情報と過去面談を取得する SK プラグイン."""

    def __init__(self) -> None:
        db = make_cosmos_client().get_database_client(settings.cosmos_database)
        self._customers = db.get_container_client("customers")
        self._meetings = db.get_container_client("meetings")
        # 履歴中の preMeetingDocumentUrl を読み出し時に再署名するための signer。
        # Blob を使わない経路では作らないよう遅延初期化する。
        self._signer: BlobSasSigner | None = None

    def _refresh_document_url(self, meeting: dict) -> None:
        """meeting の preMeetingDocumentUrl を、blob 名から新しい SAS URL に差し替える.

        保存されている URL は SAS を落とした素の URL（または旧データでは失効 SAS 付き）
        なので、blob 名から都度発行し直す。失敗しても履歴取得は止めない（best-effort）。
        """
        blob_name = meeting.get("documentBlob") or extract_blob_name(
            meeting.get("preMeetingDocumentUrl") or ""
        )
        if not blob_name:
            return
        try:
            if self._signer is None:
                self._signer = BlobSasSigner()
            meeting["preMeetingDocumentUrl"] = self._signer.sign_blob_name(blob_name)
        except Exception:  # noqa: BLE001
            logger.warning(
                "failed to re-sign preMeetingDocumentUrl (blob=%s)",
                blob_name,
                exc_info=True,
            )

    @kernel_function(
        description=(
            "社内に蓄積された顧客の基本情報と過去の面談履歴を取得する。"
            "存在しない場合は customer=null, meetings=[] を返す（新規顧客）。"
            "存在する場合は前回までの outcomes / nextActions を含めて返すので、"
            "提案の継続性を保つために必ず参照すること。"
        ),
    )
    def get_customer_history(
        self,
        company_name: Annotated[str, "顧客企業の正式名称（例: '株式会社サンプル製作所'）"],
    ) -> Annotated[str, "顧客情報と過去面談履歴の JSON 文字列"]:
        customers = list(
            self._customers.query_items(
                query="SELECT * FROM c WHERE c.companyName = @name",
                parameters=[{"name": "@name", "value": company_name}],
                enable_cross_partition_query=True,
            )
        )

        if not customers:
            return json.dumps(
                {"customer": None, "meetings": []},
                ensure_ascii=False,
            )

        customer = strip_internal(customers[0])
        company_id = customer["companyId"]

        meetings = [
            strip_internal(m)
            for m in self._meetings.query_items(
                query=(
                    "SELECT * FROM c WHERE c.companyId = @id ORDER BY c.round DESC"
                ),
                parameters=[{"name": "@id", "value": company_id}],
                partition_key=company_id,
            )
        ]
        for meeting in meetings:
            self._refresh_document_url(meeting)

        return json.dumps(
            {"customer": customer, "meetings": meetings},
            ensure_ascii=False,
            default=str,
        )
