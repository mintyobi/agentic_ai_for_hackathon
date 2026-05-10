"""面談レコードを Cosmos DB meetings コンテナに保存するプラグイン."""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from azure.cosmos import CosmosClient
from semantic_kernel.functions import kernel_function

from agent_first_meeting.config import settings


class MeetingRecordPlugin:
    """生成資料と次回アクションを meetings コンテナに保存する SK プラグイン."""

    def __init__(self) -> None:
        cosmos = CosmosClient(
            settings.cosmos_endpoint,
            credential=settings.cosmos_key,
        )
        db = cosmos.get_database_client(settings.cosmos_database)
        self._customers = db.get_container_client("customers")
        self._meetings = db.get_container_client("meetings")

    def _resolve_company_id(self, company_name: str) -> str:
        existing = list(
            self._customers.query_items(
                query="SELECT * FROM c WHERE c.companyName = @name",
                parameters=[{"name": "@name", "value": company_name}],
                enable_cross_partition_query=True,
            )
        )
        if existing:
            return existing[0]["companyId"]

        new_id = f"cus_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        self._customers.upsert_item(
            {
                "id": new_id,
                "companyId": new_id,
                "companyName": company_name,
                "createdAt": now_iso,
                "updatedAt": now_iso,
            }
        )
        return new_id

    def _next_round(self, company_id: str) -> int:
        rows = list(
            self._meetings.query_items(
                query="SELECT VALUE COUNT(1) FROM c WHERE c.companyId = @id",
                parameters=[{"name": "@id", "value": company_id}],
                partition_key=company_id,
            )
        )
        existing_count = rows[0] if rows else 0
        return existing_count + 1

    @kernel_function(
        description=(
            "生成した提案資料と面談予定を meetings コンテナに保存し、"
            "面談レコード ID を返す。新規顧客の場合は customers にも自動登録する。"
            "outcomes は null で書き出し、follow-up エージェント側が後で更新する契約。"
        ),
    )
    def save_meeting_record(
        self,
        company_name: Annotated[str, "顧客企業の正式名称"],
        document_url: Annotated[str, "生成された提案資料の Blob URL"],
        proposed_title: Annotated[str, "提案資料の表紙タイトル"],
        next_actions: Annotated[
            list[str],
            "初回面談で確認すべきポイントや次回アクション項目のリスト",
        ],
    ) -> Annotated[str, "保存された meetings ドキュメントの ID"]:
        company_id = self._resolve_company_id(company_name)
        round_num = self._next_round(company_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        record = {
            "id": f"mtg_{uuid.uuid4().hex}",
            "companyId": company_id,
            "round": round_num,
            "scheduledAt": now_iso,
            "status": "scheduled",
            "preMeetingDocumentUrl": document_url,
            "proposedTitle": proposed_title,
            "outcomes": None,
            "nextActions": next_actions,
            "createdAt": now_iso,
        }
        self._meetings.upsert_item(record)
        return record["id"]
