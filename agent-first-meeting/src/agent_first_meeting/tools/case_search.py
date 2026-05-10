"""類似事例検索プラグイン (Cosmos DB Vector Search)."""
import json
from typing import Annotated

from azure.cosmos import CosmosClient
from openai import AzureOpenAI
from semantic_kernel.functions import kernel_function

from agent_first_meeting.config import settings


class CaseSearchPlugin:
    """`cases` コンテナを vector 検索する SK プラグイン."""

    def __init__(self) -> None:
        self._openai = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        cosmos = CosmosClient(
            settings.cosmos_endpoint,
            credential=settings.cosmos_key,
        )
        self._container = (
            cosmos.get_database_client(settings.cosmos_database)
            .get_container_client("cases")
        )

    @kernel_function(
        description=(
            "社内に蓄積された過去の事例を類似度検索する。"
            "顧客の業界・規模・課題感などを自由記述のクエリで渡すと、"
            "意味的に近い事例の id, title, summary, industry, solutions, outcomes, score を返す。"
        ),
    )
    def search_similar_cases(
        self,
        query: Annotated[
            str,
            "検索クエリ。顧客の業界・規模・抱える課題などを自然言語で自由記述。",
        ],
        top: Annotated[int, "取得件数。既定は 3。"] = 3,
    ) -> Annotated[str, "類似事例の JSON 配列文字列。"]:
        embedding = (
            self._openai.embeddings.create(
                model=settings.azure_openai_embedding_deployment,
                input=query,
                dimensions=1536,
            )
            .data[0]
            .embedding
        )

        sql = (
            "SELECT TOP @top c.id, c.title, c.summary, c.industry, "
            "c.solutions, c.outcomes, "
            "VectorDistance(c.embedding, @vec) AS score "
            "FROM c "
            "ORDER BY VectorDistance(c.embedding, @vec)"
        )
        results = list(
            self._container.query_items(
                query=sql,
                parameters=[
                    {"name": "@top", "value": top},
                    {"name": "@vec", "value": embedding},
                ],
                enable_cross_partition_query=True,
            )
        )
        return json.dumps(results, ensure_ascii=False)
