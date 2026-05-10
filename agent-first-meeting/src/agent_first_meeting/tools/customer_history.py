"""顧客情報・面談履歴の取得プラグイン (Cosmos DB)."""
import json
from typing import Annotated

from azure.cosmos import CosmosClient
from semantic_kernel.functions import kernel_function

from agent_first_meeting.config import settings


_INTERNAL_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}


def _strip_internal(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in _INTERNAL_FIELDS}


class CustomerHistoryPlugin:
    """`customers` / `meetings` コンテナから顧客情報と過去面談を取得する SK プラグイン."""

    def __init__(self) -> None:
        cosmos = CosmosClient(
            settings.cosmos_endpoint,
            credential=settings.cosmos_key,
        )
        db = cosmos.get_database_client(settings.cosmos_database)
        self._customers = db.get_container_client("customers")
        self._meetings = db.get_container_client("meetings")

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

        customer = _strip_internal(customers[0])
        company_id = customer["companyId"]

        meetings = [
            _strip_internal(m)
            for m in self._meetings.query_items(
                query=(
                    "SELECT * FROM c WHERE c.companyId = @id ORDER BY c.round DESC"
                ),
                parameters=[{"name": "@id", "value": company_id}],
                partition_key=company_id,
            )
        ]

        return json.dumps(
            {"customer": customer, "meetings": meetings},
            ensure_ascii=False,
            default=str,
        )
