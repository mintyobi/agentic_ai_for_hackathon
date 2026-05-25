# ===
# Library
# ===

# 3rd party
from azure.cosmos import CosmosClient
from openai import AzureOpenAI

# アプリと接続情報を統一（sales-agent DB / 1536 次元）
from agent_first_meeting.config import settings

# クライアント初期化
cosmos = CosmosClient(
    settings.cosmos_endpoint,
    credential=settings.cosmos_key,
)
openai_client = AzureOpenAI(
    azure_endpoint=settings.azure_openai_endpoint,
    api_key=settings.azure_openai_api_key,
    api_version=settings.azure_openai_api_version,
)

db = cosmos.get_database_client(settings.cosmos_database)
documents_container = db.get_container_client("documents")
chunks_container    = db.get_container_client("chunks")


# ----------------------------------------
# 共通：クエリテキストをベクトル化（アプリと同じ 1536 次元）
# ----------------------------------------
def get_query_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=text,
        dimensions=1536,
    )
    return response.data[0].embedding


# ----------------------------------------
# 検索1：ベクトル検索
#   意味的に近いチャンクを取得する
#   例）「コスト削減の事例を教えて」のような
#       曖昧なクエリに強い
# ----------------------------------------
def vector_search(query: str, top_k: int = 3) -> list[dict]:
    embedding = get_query_embedding(query)

    results = list(chunks_container.query_items(
        query="""
            SELECT TOP @top_k
                c.document_id,
                c.text,
                c.slide_number,
                VectorDistance(c.embedding, @embedding) AS score
            FROM c
            ORDER BY VectorDistance(c.embedding, @embedding)
        """,
        parameters=[
            {"name": "@top_k",    "value": top_k},
            {"name": "@embedding","value": embedding}
        ],
        enable_cross_partition_query=True
    ))
    return results


# ----------------------------------------
# 検索2：キーワード検索
#   業種・種別・タグで絞り込む
#   例）「製造業の提案書だけ取得したい」
#       のような条件検索に強い
# ----------------------------------------
def keyword_search(
    industry: str | None = None,
    doc_type: str | None = None,
    tag: str | None = None
) -> list[dict]:
    conditions = []
    parameters = []

    if industry:
        conditions.append("c.industry = @industry")
        parameters.append({"name": "@industry", "value": industry})
    if doc_type:
        conditions.append("c.type = @type")
        parameters.append({"name": "@type", "value": doc_type})
    if tag:
        conditions.append("ARRAY_CONTAINS(c.tags, @tag)")
        parameters.append({"name": "@tag", "value": tag})

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"SELECT c.id, c.title, c.type, c.industry, c.tags FROM c {where}"

    results = list(documents_container.query_items(
        query=query,
        parameters=parameters,
        enable_cross_partition_query=True
    ))
    return results


# ----------------------------------------
# 検索3：ハイブリッド検索
#   キーワード検索で対象ドキュメントを絞った上で
#   ベクトル検索を行う
#   例）「製造業向けの資料からコスト削減の
#       事例を探したい」のような組み合わせに強い
# ----------------------------------------
def hybrid_search(
    query: str,
    industry: str | None = None,
    doc_type: str | None = None,
    tag: str | None = None,
    top_k: int = 3
) -> list[dict]:
    # ① まずキーワード検索で対象ドキュメントIDを絞る
    matched_docs = keyword_search(industry=industry, doc_type=doc_type, tag=tag)
    if not matched_docs:
        print("  条件に一致するドキュメントが見つかりませんでした")
        return []

    doc_ids = [doc["id"] for doc in matched_docs]
    print(f"  キーワード絞り込み: {len(doc_ids)} 件のドキュメントが対象")

    # ② 絞り込んだドキュメントIDに対してベクトル検索
    embedding = get_query_embedding(query)
    placeholders = ", ".join([f"@id{i}" for i in range(len(doc_ids))])
    id_params = [{"name": f"@id{i}", "value": v} for i, v in enumerate(doc_ids)]

    results = list(chunks_container.query_items(
        query=f"""
            SELECT TOP @top_k
                c.document_id,
                c.text,
                c.slide_number,
                VectorDistance(c.embedding, @embedding) AS score
            FROM c
            WHERE c.document_id IN ({placeholders})
            ORDER BY VectorDistance(c.embedding, @embedding)
        """,
        parameters=[
            {"name": "@top_k",    "value": top_k},
            {"name": "@embedding","value": embedding},
            *id_params
        ],
        enable_cross_partition_query=True
    ))
    return results


# ----------------------------------------
# 結果を見やすく表示するユーティリティ
# ----------------------------------------
def print_results(label: str, results: list[dict]):
    print(f"\n{'='*50}")
    print(f"[{label}]  {len(results)} 件ヒット")
    print('='*50)
    for i, r in enumerate(results, 1):
        score = r.get("score", "-")
        score_str = f"{score:.4f}" if isinstance(score, float) else str(score)
        print(f"\n--- {i}件目  スコア: {score_str} ---")
        print(f"document_id : {r.get('document_id', r.get('id', '-'))}")
        print(f"slide_number: {r.get('slide_number', '-')}")
        text = r.get("text", r.get("title", "-"))
        print(f"テキスト    : {text[:120]}...")


# ----------------------------------------
# 動作確認用の実行例
# ----------------------------------------
if __name__ == "__main__":

    # --- ベクトル検索 ---
    results = vector_search("コスト削減の効果を教えて", top_k=3)
    print_results("ベクトル検索", results)

    # --- キーワード検索 ---
    results = keyword_search(industry="製造業", doc_type="proposal")
    print_results("キーワード検索（製造業 × 提案書）", results)

    # --- ハイブリッド検索 ---
    results = hybrid_search(
        query="セキュリティ対策の費用と効果",
        industry="IT",
        doc_type="proposal",
        top_k=3
    )
    print_results("ハイブリッド検索（IT × セキュリティ費用）", results)