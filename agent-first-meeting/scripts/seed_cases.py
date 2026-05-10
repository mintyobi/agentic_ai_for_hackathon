"""ダミー事例を埋め込み計算とともに Cosmos DB cases コンテナに投入する.

Step 3〜4 のスモーク：
  1. text-embedding-3-large で 1536 次元の埋め込みを計算
  2. Cosmos DB sales-agent.cases に upsert
  3. 読み戻して確認
"""
import sys

from azure.cosmos import CosmosClient
from openai import AzureOpenAI

from agent_first_meeting.config import settings

sys.stdout.reconfigure(encoding="utf-8")


DUMMY_CASE: dict = {
    "id": "case_001",
    "industry": "製造業",
    "scale": "中小企業",
    "title": "技能継承課題に対する AI ナレッジベース導入",
    "summary": "ベテラン技術者の暗黙知を LLM で形式知化し、若手の生産性 30% 向上を実現",
    "challenges": ["技能継承", "人材不足"],
    "solutions": ["RAG ベースのナレッジ検索システム"],
    "outcomes": "若手育成期間を 6 ヶ月から 3 ヶ月に短縮",
}


def build_embedding_text(case: dict) -> str:
    """埋め込みに使うテキスト：タイトル + 要約 + 解決策 を連結."""
    return "\n".join(
        [
            case["title"],
            case["summary"],
            " ".join(case.get("solutions", [])),
        ]
    )


def main() -> None:
    print(f"[case] id={DUMMY_CASE['id']} industry={DUMMY_CASE['industry']}")

    openai_client = AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )
    text = build_embedding_text(DUMMY_CASE)
    embedding_response = openai_client.embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=text,
        dimensions=1536,
    )
    embedding = embedding_response.data[0].embedding
    print(f"[embedding] dim={len(embedding)} sample[:3]={embedding[:3]}")

    cosmos_client = CosmosClient(
        settings.cosmos_endpoint,
        credential=settings.cosmos_key,
    )
    database = cosmos_client.get_database_client(settings.cosmos_database)
    container = database.get_container_client("cases")

    case_doc = {**DUMMY_CASE, "embedding": embedding}
    container.upsert_item(case_doc)
    print(f"[upsert] OK ({settings.cosmos_database}.cases)")

    retrieved = container.read_item(
        item=DUMMY_CASE["id"],
        partition_key=DUMMY_CASE["industry"],
    )
    print(f"[read-back] id={retrieved['id']} title={retrieved['title']}")
    print(f"[read-back] embedding_dim={len(retrieved['embedding'])}")


if __name__ == "__main__":
    main()
