"""ダミー資料データを Cosmos DB documents / chunks コンテナに投入する.

スモークテスト：
  1. documents コンテナにメタ情報を upsert
  2. text-embedding-3-large で 1536 次元の埋め込みを計算
  3. chunks コンテナに分割テキスト＋ベクトルを upsert
  4. 両コンテナから読み戻して確認
"""
import sys

from azure.cosmos import CosmosClient
from openai import AzureOpenAI

from agent_first_meeting.config import settings

sys.stdout.reconfigure(encoding="utf-8")


DUMMY_DOCUMENT: dict = {
    "id": "doc_001",
    "type": "proposal",
    "title": "技能継承課題に対する AI ナレッジベース導入",
    "industry": "製造業",
    "tags": ["技能継承", "RAG", "LLM"],
}

DUMMY_CHUNKS: list[dict] = [
    {
        "id": "chunk_001",
        "document_id": "doc_001",
        "text": "ベテラン技術者の暗黙知を LLM で形式知化し、若手の生産性 30% 向上を実現",
        "page": 1,
    },
    {
        "id": "chunk_002",
        "document_id": "doc_001",
        "text": "RAG ベースのナレッジ検索システムにより、若手育成期間を 6 ヶ月から 3 ヶ月に短縮",
        "page": 2,
    },
]


def main() -> None:
    openai_client = AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )
    cosmos_client = CosmosClient(
        settings.cosmos_endpoint,
        credential=settings.cosmos_key,
    )
    database = cosmos_client.get_database_client(settings.cosmos_database)

    # --- 1. documents コンテナにメタ情報を投入 ---
    documents_container = database.get_container_client("documents")
    documents_container.upsert_item(DUMMY_DOCUMENT)
    print(f"[documents] upsert OK id={DUMMY_DOCUMENT['id']} type={DUMMY_DOCUMENT['type']}")

    retrieved_doc = documents_container.read_item(
        item=DUMMY_DOCUMENT["id"],
        partition_key=DUMMY_DOCUMENT["type"],
    )
    print(f"[documents] read-back OK title={retrieved_doc['title']}")

    # --- 2. chunks コンテナに埋め込み＋テキストを投入 ---
    chunks_container = database.get_container_client("chunks")

    for chunk in DUMMY_CHUNKS:
        # 埋め込みを計算
        embedding_response = openai_client.embeddings.create(
            model=settings.azure_openai_embedding_deployment,
            input=chunk["text"],
            dimensions=1536,
        )
        embedding = embedding_response.data[0].embedding
        print(f"[embedding] id={chunk['id']} dim={len(embedding)} sample[:3]={embedding[:3]}")

        # chunks コンテナに upsert
        chunk_doc = {**chunk, "embedding": embedding}
        chunks_container.upsert_item(chunk_doc)
        print(f"[chunks] upsert OK id={chunk['id']}")

        # 読み戻して確認
        retrieved_chunk = chunks_container.read_item(
            item=chunk["id"],
            partition_key=chunk["document_id"],
        )
        print(f"[chunks] read-back OK id={retrieved_chunk['id']} embedding_dim={len(retrieved_chunk['embedding'])}")


if __name__ == "__main__":
    main()