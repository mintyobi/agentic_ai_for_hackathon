"""類似事例検索プラグイン (Cosmos DB Vector Search - ナレッジベース版)."""

import json
from typing import Annotated

from azure.cosmos import CosmosClient
from openai import AzureOpenAI
from semantic_kernel.functions import kernel_function

from agent_first_meeting.config import settings


class CaseSearchPlugin:
    """`documents` / `chunks` コンテナをハイブリッド検索する SK プラグイン."""

    def __init__(self) -> None:
        # ── 既存コードと同じ初期化方法を踏襲 ──────────────────
        self._openai = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        cosmos = CosmosClient(
            settings.cosmos_endpoint,
            credential=settings.cosmos_key,
        )
        db = cosmos.get_database_client(settings.cosmos_database)

        # ── 変更点：参照コンテナを cases → documents / chunks に変更 ──
        self._documents = db.get_container_client("documents")
        self._chunks    = db.get_container_client("chunks")

    @kernel_function(
        description=(
            "社内に蓄積された過去の営業資料（提案書・製品カタログ）を類似度検索する。"
            "顧客の業界・規模・課題感などを自由記述のクエリで渡すと、"
            "意味的に近い資料のテキストと出典情報を返す。"
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

        # ── ① 業種が指定されていればキーワードで対象ドキュメントを絞る ──
        doc_ids: list[str] | None = None
        if industry:
            docs = list(
                self._documents.query_items(
                    query="SELECT c.id FROM c WHERE c.industry = @industry",
                    parameters=[{"name": "@industry", "value": industry}],
                    enable_cross_partition_query=True,
                )
            )
            doc_ids = [d["id"] for d in docs] if docs else None

        # ── ② ベクトル生成（既存コードと同じモデル・次元数を使用）──
        embedding = (
            self._openai.embeddings.create(
                model=settings.azure_openai_embedding_deployment,
                input=query,
                dimensions=1536,
            )
            .data[0]
            .embedding
        )

        # ── ③ ベクトル検索（業種絞り込みあり / なし で分岐）──
        if doc_ids:
            placeholders = ", ".join([f"@id{i}" for i in range(len(doc_ids))])
            id_params = [
                {"name": f"@id{i}", "value": v} for i, v in enumerate(doc_ids)
            ]
            sql = (
                f"SELECT TOP @top "
                f"c.document_id, c.text, c.slide_number, "
                f"VectorDistance(c.embedding, @vec) AS score "
                f"FROM c "
                f"WHERE c.document_id IN ({placeholders}) "
                f"ORDER BY VectorDistance(c.embedding, @vec)"
            )
            parameters = [
                {"name": "@top", "value": top},
                {"name": "@vec", "value": embedding},
                *id_params,
            ]
        else:
            sql = (
                "SELECT TOP @top "
                "c.document_id, c.text, c.slide_number, "
                "VectorDistance(c.embedding, @vec) AS score "
                "FROM c "
                "ORDER BY VectorDistance(c.embedding, @vec)"
            )
            parameters = [
                {"name": "@top", "value": top},
                {"name": "@vec", "value": embedding},
            ]

        results = list(
            self._chunks.query_items(
                query=sql,
                parameters=parameters,
                enable_cross_partition_query=True,
            )
        )

        # ── ④ 既存コードと同じ形式（JSON文字列）で返す ──
        return json.dumps(results, ensure_ascii=False)