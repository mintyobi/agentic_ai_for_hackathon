"""Cosmos DB chunks コンテナで vector search を試す（動作確認）.

クエリテキストを埋め込み化し、VectorDistance() で類似チャンク TOP N を取得する。
"""
import sys

from azure.cosmos import CosmosClient
from openai import AzureOpenAI

from agent_first_meeting.config import settings

sys.stdout.reconfigure(encoding="utf-8")


QUERY_TEXT = (
    "製造業のDX推進、技能継承で困っている。"
    "ベテラン社員のノウハウをどう若手に伝えるかが課題。"
)
TOP_N = 5


def main() -> None:
    print(f"[query] {QUERY_TEXT}")

    openai_client = AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )
    embedding_response = openai_client.embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=QUERY_TEXT,
        dimensions=1536,
    )
    query_vec = embedding_response.data[0].embedding
    print(f"[query_embedding] dim={len(query_vec)}")

    cosmos_client = CosmosClient(
        settings.cosmos_endpoint,
        credential=settings.cosmos_key,
    )
    database = cosmos_client.get_database_client(settings.cosmos_database)
    container = database.get_container_client("chunks")

    query = (
        "SELECT TOP @top c.id, c.document_id, c.text, c.slide_number, "
        "VectorDistance(c.embedding, @vec) AS score "
        "FROM c "
        "ORDER BY VectorDistance(c.embedding, @vec)"
    )
    parameters = [
        {"name": "@top", "value": TOP_N},
        {"name": "@vec", "value": query_vec},
    ]
    results = list(
        container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True,
        )
    )

    print(f"[results] {len(results)} hits")
    for i, item in enumerate(results, 1):
        print(
            f"  {i}. score={item['score']:.4f} "
            f"id={item['id']} document_id={item['document_id']} "
            f"slide={item.get('slide_number')} text={item['text'][:50]}..."
        )


if __name__ == "__main__":
    main()
