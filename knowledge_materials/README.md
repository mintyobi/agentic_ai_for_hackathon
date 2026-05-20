# 営業資料ナレッジベース 構築ガイド

Azure Cosmos DB for NoSQL を使って営業資料（提案書・製品カタログ）をベクトル検索可能なナレッジベースとして構築するためのガイドです。資料作成エージェントが過去資料を参照してコンテキストを取得することを目的としています。

---

## 目次

1. [システム構成](#1-システム構成)
2. [前提条件](#2-前提条件)
3. [環境構築](#3-環境構築)
4. [Azure リソースのセットアップ](#4-azure-リソースのセットアップ)
5. [データ投入](#5-データ投入)
6. [動作確認](#6-動作確認)
7. [検索クエリの使い方](#7-検索クエリの使い方)
8. [ファイル構成](#8-ファイル構成)

---

## 1. システム構成

```
営業資料（.pptx）
        ↓
  ingest_documents.py
  ├── テキスト抽出（python-pptx）
  ├── チャンク分割（langchain-text-splitters）
  └── ベクトル化（Azure OpenAI）
        ↓
  Azure Cosmos DB for NoSQL
  ├── documents   # 資料のメタ情報
  ├── chunks      # 分割テキスト＋ベクトル
  └── templates   # 構成テンプレート（将来利用）
        ↓
  search_knowledge.py
  ├── ベクトル検索
  ├── キーワード検索
  └── ハイブリッド検索
        ↓
  資料作成エージェント（今後実装）
```

### コンテナ設計

| コンテナ | 役割 | パーティションキー |
|---|---|---|
| `documents` | 資料のタイトル・業種・タグなどのメタ情報 | `/type` |
| `chunks` | 500文字単位に分割したテキストとベクトル | `/document_id` |
| `templates` | スライド構成テンプレート（将来利用） | `/target_industry` |

---

## 2. 前提条件

- Python 3.11 以上
- [uv](https://docs.astral.sh/uv/) がインストール済み
- [Azure CLI](https://learn.microsoft.com/ja-jp/cli/azure/install-azure-cli) がインストール済み
- Azure サブスクリプションへのアクセス権

---

## 3. 環境構築

```bash
# リポジトリのルートで仮想環境を作成・ライブラリをインストール
uv sync
```

`pyproject.toml` に記載された以下のライブラリが自動インストールされます。

| ライブラリ | 用途 |
|---|---|
| `azure-cosmos` | Cosmos DB への接続・操作 |
| `openai` | Azure OpenAI でのベクトル生成 |
| `python-dotenv` | `.env` ファイルの読み込み |
| `python-pptx` | PPTXからのテキスト抽出 |
| `langchain-text-splitters` | テキストのチャンク分割 |

---

## 4. Azure リソースのセットアップ

### 4-1. Azure にログイン

```bash
az login

# 複数サブスクリプションがある場合は対象を指定
az account set --subscription "<サブスクリプションIDまたは名前>"

# 現在のサブスクリプションを確認
az account show
```

### 4-2. Cosmos DB アカウントとデータベースの作成

```bash
# アカウント作成
az cosmosdb create \
  --name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --locations regionName=japaneast failoverPriority=0 \
  --default-consistency-level Session

# データベース作成
az cosmosdb sql database create \
  --account-name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --name sales-knowledge-db
```

### 4-3. ベクトル検索機能の有効化

```bash
az cosmosdb update \
  --name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --capabilities EnableNoSQLVectorSearch

# 有効化の確認（EnableNoSQLVectorSearch が表示されればOK）
az cosmosdb show \
  --name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --query "capabilities"
```

### 4-4. コンテナの作成

```bash
# documents コンテナ
az cosmosdb sql container create \
  --account-name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --database-name sales-knowledge-db \
  --name documents \
  --partition-key-path /type \
  --throughput 400

# chunks コンテナ
az cosmosdb sql container create \
  --account-name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --database-name sales-knowledge-db \
  --name chunks \
  --partition-key-path /document_id \
  --throughput 400

# templates コンテナ
az cosmosdb sql container create \
  --account-name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --database-name sales-knowledge-db \
  --name templates \
  --partition-key-path /target_industry \
  --throughput 400
```

### 4-5. chunksコンテナにベクトルインデックスを設定

```bash
# vector-policy.json を作成
cat > vector-policy.json << 'POLICY'
{
  "vectorEmbeddings": [
    {
      "path": "/embedding",
      "dataType": "float32",
      "distanceFunction": "cosine",
      "dimensions": 1536
    }
  ]
}
POLICY

# index-policy.json を作成
cat > index-policy.json << 'POLICY'
{
  "indexingMode": "consistent",
  "includedPaths": [{ "path": "/*" }],
  "excludedPaths": [{ "path": "/embedding/*" }],
  "vectorIndexes": [
    {
      "path": "/embedding",
      "type": "quantizedFlat"
    }
  ]
}
POLICY

# chunksコンテナに適用
az cosmosdb sql container update \
  --account-name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --database-name sales-knowledge-db \
  --name chunks \
  --vector-embeddings @vector-policy.json \
  --idx @index-policy.json
```

### 4-6. Azure OpenAI リソースの作成

```bash
# プロバイダー登録確認（"Registered" と表示されればOK）
az provider show \
  --namespace Microsoft.CognitiveServices \
  --query "registrationState"

# OpenAI リソース作成
az cognitiveservices account create \
  --name <your-openai-resource-name> \
  --resource-group <your-resource-group> \
  --kind OpenAI \
  --sku S0 \
  --location japaneast

# text-embedding-3-small モデルをデプロイ
az cognitiveservices account deployment create \
  --name <your-openai-resource-name> \
  --resource-group <your-resource-group> \
  --deployment-name text-embedding-3-small \
  --model-name text-embedding-3-small \
  --model-version "1" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name Standard
```

---

## 5. データ投入

### 5-1. 接続情報を `.env` に設定

`src/.env` を作成して以下を記載します。

```env
# Cosmos DB
COSMOS_ENDPOINT=https://<your-cosmosdb-account-name>.documents.azure.com:443/
COSMOS_KEY=<your-primary-master-key>

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<your-openai-resource-name>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-azure-openai-key>
AZURE_OPENAI_DEPLOYMENT=text-embedding-3-small
```

各値の取得コマンドは以下の通りです。

```bash
# Cosmos DB エンドポイント
az cosmosdb show \
  --name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --query "documentEndpoint" --output tsv

# Cosmos DB キー
az cosmosdb keys list \
  --name <your-cosmosdb-account-name> \
  --resource-group <your-resource-group> \
  --query "primaryMasterKey" --output tsv

# Azure OpenAI エンドポイント
az cognitiveservices account show \
  --name <your-openai-resource-name> \
  --resource-group <your-resource-group> \
  --query "properties.endpoint" --output tsv

# Azure OpenAI キー
az cognitiveservices account keys list \
  --name <your-openai-resource-name> \
  --resource-group <your-resource-group> \
  --query "key1" --output tsv
```

### 5-2. PPTXファイルを配置してスクリプトを実行

投入したい `.pptx` ファイルを `src/` に置き、`ingest_documents.py` の末尾にある `files` リストを編集します。

```python
files = [
    {
        "path":     "your_file.pptx",   # src/ からの相対パス
        "title":    "資料のタイトル",
        "type":     "proposal",          # "proposal" or "catalog"
        "industry": "製造業",
        "tags":     ["DX", "IoT"]
    },
    # 必要なだけ追加
]
```

編集が完了したら実行します。

```bash
uv run python src/ingest_documents.py
```

正常に動作すると以下のように出力されます。

```
処理開始: 資料のタイトル
  ✓ documents に登録: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  ✓ チャンク数: 8
  ✓ chunks に登録完了（8件）
処理完了: 資料のタイトル
```

---

## 6. 動作確認

### データ件数の確認

```bash
uv run python src/check_count.py
```

```
documents: 3 件
chunks: 12 件
```

### Azure Portal で中身を確認

1. [Azure Portal](https://portal.azure.com) にアクセス
2. 検索バーで `<your-cosmosdb-account-name>` を検索
3. 左メニュー「データエクスプローラー」を開く
4. `sales-knowledge-db` → `chunks` → `Items` をクリック
5. アイテムを選択し `embedding` フィールドに1536個の数値が入っていれば成功

---

## 7. 検索クエリの使い方

`search_knowledge.py` に3種類の検索関数が実装されています。

### ベクトル検索（意味的に近いチャンクを取得）

```python
from search_knowledge import vector_search

results = vector_search("コスト削減の効果を教えて", top_k=3)
```

曖昧なクエリや自然文での検索に強いです。スコアはコサイン距離なので値が小さいほど類似度が高い結果です。

### キーワード検索（条件で絞り込み）

```python
from search_knowledge import keyword_search

results = keyword_search(industry="製造業", doc_type="proposal", tag="DX")
```

`industry` / `doc_type` / `tag` はすべて省略可能です。複数条件はAND検索になります。

### ハイブリッド検索（絞り込み＋意味検索）

```python
from search_knowledge import hybrid_search

results = hybrid_search(
    query="セキュリティ対策の費用と効果",
    industry="IT",
    doc_type="proposal",
    top_k=3
)
```

まずキーワードで対象ドキュメントを絞り込み、その中でベクトル検索を行います。精度と効率のバランスが最も良い方法です。

---

## 8. ファイル構成

```
knowledge_materials/
├── pyproject.toml          # 依存ライブラリの定義
├── README.md               # このファイル
└── src/
    ├── .env                # 接続情報（Gitに含めないこと）
    ├── ingest_documents.py # データ投入スクリプト
    ├── search_knowledge.py # 検索クエリスクリプト
    ├── check_count.py      # データ件数確認スクリプト
    └── *.pptx              # 投入する資料ファイル
```

> **注意：** `.env` には機密情報が含まれます。`.gitignore` に追加してGitリポジトリに含めないようにしてください。

```bash
echo ".env" >> .gitignore
```