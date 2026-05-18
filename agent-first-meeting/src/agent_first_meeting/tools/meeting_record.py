"""面談レコードを Cosmos DB meetings コンテナに保存するプラグイン.

並行制御:
- companyId は会社名から決定的に導出（SHA1 先頭12文字）。
  → 同じ会社名なら必ず同じ ID になるので「並行 upsert で別 ID」問題が起きない。
- meeting の id は f"mtg_{company_id}_{round:04d}" で一意性が保証される。
  並行 create で 409 が返ったら round を +1 してリトライする。
"""
import logging
from datetime import datetime, timezone
from typing import Annotated

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import (
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)
from semantic_kernel.functions import kernel_function

from agent_first_meeting._company_id import deterministic_company_id
from agent_first_meeting.config import settings

logger = logging.getLogger(__name__)

_MAX_ROUND_RETRY = 50


def _meeting_doc_id(company_id: str, round_num: int) -> str:
    return f"mtg_{company_id}_{round_num:04d}"


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

    def _ensure_customer(self, company_name: str) -> str:
        """会社マスタを upsert（決定的 ID で衝突を防ぐ）.

        既存顧客の場合は createdAt や seed で投入された industry / scale /
        knownChallenges などのフィールドを保持し、updatedAt のみを差し替える。
        以前は upsert に渡したフィールドが既存ドキュメントを丸ごと置換していたため、
        save_meeting_record が呼ばれる度に createdAt や属性情報が失われていた。
        """
        company_id = deterministic_company_id(company_name)
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            existing = self._customers.read_item(
                item=company_id, partition_key=company_id
            )
        except CosmosResourceNotFoundError:
            existing = None

        if existing is None:
            record = {
                "id": company_id,
                "companyId": company_id,
                "companyName": company_name.strip(),
                "createdAt": now_iso,
                "updatedAt": now_iso,
            }
        else:
            record = {**existing, "updatedAt": now_iso}
            # 会社名の表記揺れがあれば最新を反映、createdAt は必ず維持
            record["companyName"] = company_name.strip()
            record.setdefault("createdAt", now_iso)

        self._customers.upsert_item(record)
        return company_id

    def _estimate_initial_round(self, company_id: str) -> int:
        """次の round 番号の初期推定値を返す。並行時は create_item の 409 でリトライされる."""
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
        company_id = self._ensure_customer(company_name)
        now_iso = datetime.now(timezone.utc).isoformat()
        initial_round = self._estimate_initial_round(company_id)

        # round 番号を +1 しつつリトライ（並行 create で 409 が返ったら次の番号に進む）
        for round_num in range(initial_round, initial_round + _MAX_ROUND_RETRY):
            record = {
                "id": _meeting_doc_id(company_id, round_num),
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
            try:
                self._meetings.create_item(record)
            except CosmosResourceExistsError:
                logger.info(
                    "MeetingRecordPlugin: round %d already exists for %s, retrying",
                    round_num, company_id,
                )
                continue

            logger.info(
                "MeetingRecordPlugin: saved id=%s company_id=%s round=%d",
                record["id"], company_id, round_num,
            )
            return record["id"]

        raise RuntimeError(
            f"failed to allocate meeting round number for {company_id} "
            f"after {_MAX_ROUND_RETRY} attempts"
        )
