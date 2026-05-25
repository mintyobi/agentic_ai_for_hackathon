import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from azure.cosmos import CosmosClient
from openai import AzureOpenAI
from pptx import Presentation
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# 環境変数の確認（None のままだとエラーになるため早期検出）
_endpoint = os.getenv("COSMOS_ENDPOINT")
_key      = os.getenv("COSMOS_KEY")
if not _endpoint or not _key:
    raise ValueError(".env に COSMOS_ENDPOINT と COSMOS_KEY が設定されているか確認してください")

# クライアント初期化（credential にキー文字列を直接渡す）
cosmos = CosmosClient(url=_endpoint, credential=_key)

openai_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-02-01"
)

db = cosmos.get_database_client("sales-knowledge-db")
documents_container = db.get_container_client("documents")
chunks_container    = db.get_container_client("chunks")

# ----------------------------------------
# ① PPTXからテキストを抽出
#    スライドごとにタイトル→本文の順で取得
# ----------------------------------------
def extract_text_from_pptx(file_path: str) -> str:
    prs = Presentation(file_path)
    slide_texts = []

    for i, slide in enumerate(prs.slides):
        parts = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                line = para.text.strip()
                if line:
                    parts.append(line)
        if parts:
            slide_texts.append(f"[スライド{i+1}]\n" + "\n".join(parts))

    return "\n\n".join(slide_texts)

# ----------------------------------------
# ② テキストをチャンクに分割
#    （500文字ごと、100文字オーバーラップ）
# ----------------------------------------
def split_into_chunks(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100
    )
    return splitter.split_text(text)

# ----------------------------------------
# ③ OpenAIでベクトルを生成
# ----------------------------------------
def get_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),  # デプロイ名を指定
        input=text
    )
    return response.data[0].embedding

# ----------------------------------------
# メイン：1ファイルを投入する関数
# ----------------------------------------
def ingest_document(
    file_path: str,
    title: str,
    doc_type: str,       # "proposal"（提案書）or "catalog"（製品カタログ）
    industry: str,       # 例: "製造業", "金融", "IT"
    tags: list[str]
):
    print(f"処理開始: {title}")

    # documentコンテナにメタ情報を保存
    doc_id = str(uuid.uuid4())
    documents_container.upsert_item({
        "id": doc_id,
        "title": title,
        "type": doc_type,        # パーティションキー
        "industry": industry,
        "tags": tags,
        "created_at": datetime.now().isoformat(),
        "file_path": file_path
    })
    print(f"  ✓ documents に登録: {doc_id}")

    # テキスト抽出 → チャンク分割
    text = extract_text_from_pptx(file_path)
    chunks = split_into_chunks(text)
    print(f"  ✓ チャンク数: {len(chunks)}")

    # 各チャンクをベクトル化してchunksコンテナに保存
    for i, chunk_text in enumerate(chunks):
        embedding = get_embedding(chunk_text)
        chunks_container.upsert_item({
            "id": str(uuid.uuid4()),
            "document_id": doc_id,   # パーティションキー
            "text": chunk_text,
            "embedding": embedding,
            "slide_number": i,
            "section": f"chunk_{i}"
        })

    print(f"  ✓ chunks に登録完了（{len(chunks)}件）")
    print(f"処理完了: {title}\n")

# ----------------------------------------
# 実行例：サンプル3ファイルを投入
# ----------------------------------------
if __name__ == "__main__":
    files = [
        {
            "path":     "./data/proposal_manufacturing_2024.pptx",
            "title":    "製造業向け生産管理DX提案書 2024年版",
            "type":     "proposal",
            "industry": "製造業",
            "tags":     ["DX", "IoT", "コスト削減", "予防保全"]
        },
        {
            "path":     "./data/proposal_it_security_2024.pptx",
            "title":    "中堅企業向けセキュリティ強化提案書 2024年版",
            "type":     "proposal",
            "industry": "IT",
            "tags":     ["セキュリティ", "MFA", "EDR", "ランサムウェア対策"]
        },
        {
            "path":     "./data/catalog_cloud_services_2024.pptx",
            "title":    "クラウドサービス製品カタログ 2024",
            "type":     "catalog",
            "industry": "全業種",
            "tags":     ["クラウド", "IoT", "セキュリティ", "データ分析"]
        },
    ]

    for f in files:
        ingest_document(
            file_path=f["path"],
            title=f["title"],
            doc_type=f["type"],
            industry=f["industry"],
            tags=f["tags"]
        )