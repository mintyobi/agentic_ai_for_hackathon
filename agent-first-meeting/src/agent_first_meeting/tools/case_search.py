"""類似事例検索プラグイン (Cosmos DB Vector Search - ナレッジベース版).

過去の営業資料（提案書・カタログ）を PPTX から取り込んだ `documents`（メタ情報）/
`chunks`（本文チャンク＋埋め込み）コンテナに対してベクトル検索する。
取り込みは scripts/ingest_documents.py を参照。
"""
import json
from typing import Annotated

from semantic_kernel.functions import kernel_function

from agent_first_meeting._azure_clients import make_azure_openai, make_cosmos_client
from agent_first_meeting.config import settings


class CaseSearchPlugin:
    """`documents` / `chunks` コンテナをハイブリッド検索する SK プラグイン."""

    def __init__(self) -> None:
        self._openai = make_azure_openai()
        db = make_cosmos_client().get_database_client(settings.cosmos_database)
        self._documents = db.get_container_client("documents")
        self._chunks = db.get_container_client("chunks")

    @kernel_function(
        description=(
            "社内に蓄積された過去の営業資料（提案書・製品カタログ）を類似度検索する。"
            "顧客の業界・規模・課題感などを自由記述のクエリで渡すと、"
            "意味的に近い資料チャンクのテキストと出典情報を返す。"
            "industry（業種）を指定すると、その業種の資料に絞り込んでから検索する。"
        ),
    )
    def search_similar_cases(
        self,
        query: Annotated[
            str,
            "検索クエリ。顧客の業界・規模・抱える課題などを自然言語で自由記述。",
        ],
        industry: Annotated[
            str,
            "絞り込む業種（例: 製造業, IT, 金融）。指定しない場合は全業種が対象。",
        ] = "",
        top: Annotated[int, "取得件数。既定は 3。"] = 3,
    ) -> Annotated[str, "類似資料チャンクの JSON 配列文字列。"]:
        # ① 業種指定があれば documents から対象 doc を絞る
        #    UI の業種値（例「IT・ソフトウェア」）と取り込み時の値（例「IT」）が
        #    完全一致しないため、双方向 CONTAINS で吸収する。加えて全業種カタログは
        #    どの業種でも参考になるので常に対象へ含める。一致が無ければ doc_ids=None
        #    として全件検索にフォールバックする（後段の else 分岐）。
        doc_ids: list[str] | None = None
        if industry:
            docs = list(
                self._documents.query_items(
                    query=(
                        "SELECT c.id FROM c WHERE "
                        "CONTAINS(@industry, c.industry) "
                        "OR CONTAINS(c.industry, @industry) "
                        "OR c.industry = '全業種'"
                    ),
                    parameters=[{"name": "@industry", "value": industry}],
                    enable_cross_partition_query=True,
                )
            )
            doc_ids = [d["id"] for d in docs] if docs else None

        # ② クエリを埋め込み化（アプリ全体で 1536 次元に統一）
        embedding = (
            self._openai.embeddings.create(
                model=settings.azure_openai_embedding_deployment,
                input=query,
                dimensions=1536,
            )
            .data[0]
            .embedding
        )

        # ③ chunks をベクトル検索（業種絞り込みあり/なしで分岐）
        select = (
            "SELECT TOP @top c.document_id, c.text, c.slide_number, "
            "VectorDistance(c.embedding, @vec) AS score FROM c "
        )
        parameters: list[dict] = [
            {"name": "@top", "value": top},
            {"name": "@vec", "value": embedding},
        ]
        if doc_ids:
            placeholders = ", ".join(f"@id{i}" for i in range(len(doc_ids)))
            parameters += [
                {"name": f"@id{i}", "value": v} for i, v in enumerate(doc_ids)
            ]
            sql = (
                f"{select}WHERE c.document_id IN ({placeholders}) "
                "ORDER BY VectorDistance(c.embedding, @vec)"
            )
        else:
            sql = f"{select}ORDER BY VectorDistance(c.embedding, @vec)"

        results = list(
            self._chunks.query_items(
                query=sql,
                parameters=parameters,
                enable_cross_partition_query=True,
            )
        )
        return json.dumps(results, ensure_ascii=False)
