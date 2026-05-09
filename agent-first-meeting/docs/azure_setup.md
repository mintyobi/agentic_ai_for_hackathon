# Azure リソース セットアップ手順

`agent-first-meeting` を動かすために必要な Azure リソースを、Azure Portal の GUI で作成する手順です。

個人アカウント＋$200 無料クレジット前提で、最小コストになる選択肢で記載しています。

## 目次

- [前提](#前提)
- [作成順序とリージョン方針](#作成順序とリージョン方針)
- [1. リソースグループ](#1-リソースグループ)
- [2. Azure AI Foundry](#2-azure-ai-foundry)
- [3. Azure Cosmos DB for NoSQL](#3-azure-cosmos-db-for-nosql)
- [4. Azure Blob Storage](#4-azure-blob-storage)
- [5. .env への反映](#5-env-への反映)
- [6. Container Apps（後回し）](#6-container-apps後回し)
- [概算コスト](#概算コスト)
- [つまずきポイント](#つまずきポイント)

---

## 前提

- [ ] [Azure Portal](https://portal.azure.com) にサインインできる
- [ ] サブスクリプションが「無料試用版」または個人契約で有効
- [ ] [agent-first-meeting/.env.example](../.env.example) をコピーして `.env` を準備済み（最後に値を埋める）

---

## 作成順序とリージョン方針

後の手順で前のリソース情報が必要になるため、上から順に作成してください。

| 順 | リソース | 用途 |
|---|---|---|
| 1 | リソースグループ | 全リソースの入れ物 |
| 2 | Azure AI Foundry（Hub + Project + モデル） | GPT-4.1 / text-embedding-3-large |
| 3 | Cosmos DB for NoSQL | 顧客・面談・事例（vector search 込み） |
| 4 | Blob Storage | 生成 PowerPoint の保存先 |

### リージョン

**全リソースを `East US 2` で揃える** ことを推奨します。

- Foundry の Anthropic Claude モデルは East US 2 / West US 3 で配信されることが多く、リージョン依存
- 同一リージョンに揃えると **リソース間通信が無料 ＆ レイテンシ最小**

---

## 1. リソースグループ

ポータル → 「リソース グループ」→ **+ 作成**

| 項目 | 値 |
|---|---|
| サブスクリプション | 個人のもの |
| リソース グループ | `rg-sales-agent` |
| リージョン | `East US 2` |

→ 「確認及び作成」→ 作成

---

## 2. Azure AI Foundry

### 2-1. Foundry Hub と Project の作成

[https://ai.azure.com](https://ai.azure.com) にアクセス → 「**+ 新しいプロジェクト**」

| 項目 | 値 |
|---|---|
| Hub 名 | `hub-sales-agent` |
| Project 名 | `proj-sales-agent` |
| リソース グループ | `rg-sales-agent` |
| リージョン | `East US 2` |

> Hub 作成時に Storage Account / Key Vault / Application Insights が自動で一緒に作られます（Foundry の付帯リソース）。これらはそのまま残してOKです。

### 2-2. GPT-4.1 のデプロイ

Project 画面 → 左メニュー「**モデル + エンドポイント**」→ 「**+ モデルのデプロイ**」→ 「**ベースモデル**」

| 項目 | 値 |
|---|---|
| モデル | `gpt-4.1`（Azure OpenAI 提供） |
| デプロイ名 | **`gpt-4.1`**（`.env` の `AZURE_OPENAI_CHAT_DEPLOYMENT` と一致させる） |
| デプロイの種類 | **Standard / Global Standard (PAYG)**（従量課金、アイドル時0円） |
| コンテンツフィルター | 既定でOK |

> 当初設計では Claude Sonnet 4.6 を使う予定だったが、個人 Azure サブスクリプションでは Anthropic モデルが全リージョン・全バリアントでクオータ 0（要申請）だったため、確実に動く GPT-4.1 を採用。コードはモデル名を `.env` で抽象化しているため、後日 Claude のクオータが通れば 1 行変更で差し替え可能。
>
> GPT-4.1 もリージョンによってクオータ 0 のことがあるため、デプロイ可能なリージョンを `クォータ` 画面で事前に確認すること。

### 2-3. text-embedding-3-large のデプロイ

同じ手順で、もう一つデプロイします。

| 項目 | 値 |
|---|---|
| モデル | `text-embedding-3-large` |
| デプロイ名 | **`text-embedding-3-large`** |
| デプロイの種類 | Standard |
| TPM（1分あたりトークン数） | 30K |

### 2-4. エンドポイントとキーを取得

Project 画面 → 「**概要**」または「**設定**」→ Foundry エンドポイントと API キーをコピー。

メモする内容：

```
AZURE_OPENAI_ENDPOINT  ← エンドポイント URL
AZURE_OPENAI_API_KEY   ← キー
```

---

## 3. Azure Cosmos DB for NoSQL

### 3-1. アカウント作成

ポータル → 「Azure Cosmos DB」→ **+ 作成** → **Azure Cosmos DB for NoSQL** を選択

| 項目 | 値 |
|---|---|
| アカウント名 | `cosmos-sales-agent-<好きな文字列>`（グローバル一意） |
| リージョン | `East US 2` |
| 容量モード | **Serverless** ★コスト最小 |
| **Free Tier 割引適用** | **オン** ★1サブスクリプションに1個だけ無料 |

> **Free Tier** は 1000 RU/s + 25GB が無料になる枠です。1サブスクリプションに1個までしか作れないので、ぜひこのリソースで使ってください。

「**機能**」タブで **「Vector Search for NoSQL API」** を **有効化**（プレビュー機能）。

→ 「確認及び作成」→ 作成

### 3-2. データベース作成

作成完了後 → 「**データ エクスプローラー**」→ 「**+ New Database**」

| 項目 | 値 |
|---|---|
| Database id | **`sales-agent`** |
| スループット | （Serverless なので不要） |

### 3-3. コンテナを4つ作成

「**+ New Container**」を 4 回繰り返し、以下を作成：

| Container id | Partition key |
|---|---|
| `customers` | `/companyId` |
| `meetings` | `/companyId` |
| `documents` | `/companyId` |
| `cases` | `/industry` |

### 3-4. `cases` コンテナに Vector Index を設定（重要）

`cases` コンテナ → 「**Settings**」→ 「**Container Vector Policy**」 に以下を貼り付け：

```json
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
```

続いて「**Indexing Policy**」を編集して vector index を追加：

```json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [{"path": "/*"}],
  "excludedPaths": [
    {"path": "/_etag/?"},
    {"path": "/embedding/*"}
  ],
  "vectorIndexes": [
    {"path": "/embedding", "type": "diskANN"}
  ]
}
```

> **次元数 1536 にしている理由**：`text-embedding-3-large` のデフォルト出力は 3072 次元ですが、API 呼び出し時に `dimensions=1536` を指定すると 1536 次元に圧縮できます。1536 次元なら DiskANN の上限内で高速・省ストレージです。**コード側で必ず `dimensions=1536` を指定**してください。

### 3-5. エンドポイントとキーを取得

Cosmos DB アカウント → 「**Keys**」メニュー → **URI** と **Primary Key** をコピー。

メモする内容：

```
COSMOS_ENDPOINT  ← URI
COSMOS_KEY       ← Primary Key
```

---

## 4. Azure Blob Storage

### 4-1. アカウント作成

ポータル → 「ストレージ アカウント」→ **+ 作成**

| 項目 | 値 |
|---|---|
| ストレージ アカウント名 | `stsalesagent<random>`（小文字英数のみ、グローバル一意） |
| リージョン | `East US 2` |
| パフォーマンス | Standard |
| 冗長性 | **LRS** ★最安 |

→ 「確認及び作成」→ 作成

### 4-2. コンテナ作成

ストレージアカウント → 「**コンテナー**」→ **+ コンテナー**

| 項目 | 値 |
|---|---|
| 名前 | `generated-documents` |
| パブリックアクセスレベル | **プライベート** |

### 4-3. 接続情報を取得

ストレージアカウント → 「**エンドポイント**」メニュー → **Blob service** の URL をコピー。

メモする内容：

```
BLOB_ACCOUNT_URL  ← Blob service の URL
```

> 認証はコード側で `azure-identity` の `DefaultAzureCredential` を使うため、API キーは保存しません（次の 4-4 のロール付与で代替）。

### 4-4. 自分のアカウントにロールを付与

ストレージアカウント → 「**アクセス制御 (IAM)**」→ 「**+ 追加**」→ 「**ロールの割り当ての追加**」

| 項目 | 値 |
|---|---|
| ロール | **ストレージ BLOB データ共同作成者** |
| メンバー | 自分のユーザー（`mintyobi@gmail.com`） |

→ 保存

> このロール付与を忘れると、ローカル開発時に Blob 書き込みで 403 エラーになります。

---

## 5. .env への反映

[agent-first-meeting/.env.example](../.env.example) をコピーして `.env` を作り、上記でメモした値を埋めます。

```bash
cp agent-first-meeting/.env.example agent-first-meeting/.env
# エディタで .env を開いて値を埋める
```

| `.env` キー | 取得元 |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | 2-4 で取得 |
| `AZURE_OPENAI_API_KEY` | 2-4 で取得 |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | `claude-sonnet-4-6`（2-2 で付けたデプロイ名） |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | `text-embedding-3-large`（2-3 で付けたデプロイ名） |
| `AZURE_OPENAI_API_VERSION` | `2024-12-01-preview`（既定でOK） |
| `COSMOS_ENDPOINT` | 3-5 で取得 |
| `COSMOS_KEY` | 3-5 で取得 |
| `COSMOS_DATABASE` | `sales-agent` |
| `BLOB_ACCOUNT_URL` | 4-3 で取得 |
| `BLOB_CONTAINER` | `generated-documents` |

> ⚠️ `.env` は絶対に Git にコミットしないでください（`.gitignore` で除外済み）。

---

## 6. Container Apps（後回し）

PoC コードはローカルで動作確認するため、**Container Apps は PoC が動いてから** プロビジョニングします。順序的には Phase 3 の後で十分です。

---

## 概算コスト

個人クレジット $200 で十分賄える想定。

| リソース | 料金イメージ |
|---|---|
| Foundry: GPT-4.1 | 入力 $2 / 出力 $8（per 1M tokens）。デモ程度で月 $3〜$8 |
| Foundry: text-embedding-3-large | $0.13 / 1M tokens。ほぼ無視できる |
| Cosmos DB Serverless + Free Tier | 1000 RU/s + 25GB が **無料** |
| Blob Storage LRS | 数十GB 程度なら月 $1 未満 |
| **合計目安** | **月 $10〜$20**（$200 クレジットで余裕） |

---

## つまずきポイント

| 症状 | 原因と対処 |
|---|---|
| デプロイ画面で「クオータ不足」と出てモデルが選べない | クオータ画面（管理センター → Quota）でリージョン × モデルごとの割当量を確認。割当 0 の場合は別リージョン・別モデル（`gpt-4o-mini` 等）を試す or 「クォータの要求」から申請。 |
| Anthropic Claude モデルが選択肢にない／全リージョン 0 | 個人サブスクリプションでは Anthropic 系は初期クオータ 0 で要申請。本プロジェクトはこの理由で Claude を諦め GPT-4.1 を採用。 |
| Cosmos DB 作成時に Vector Search 設定項目が見当たらない | アカウント作成後でも「機能」タブから **「Vector Search for NoSQL API」** を有効化できる。 |
| Cosmos DB の Free Tier が選べない | 1サブスクリプションに 1 個まで。既に他で使っている場合は不可。Serverless だけでも十分安価。 |
| Blob 書き込みで 403 エラー | 4-4 のロール割り当て（**ストレージ BLOB データ共同作成者**）を自分のアカウントに付与し忘れている。 |
| `az login` していないとローカル開発で認証エラー | ターミナルで `az login` を実行（`azure-cli` のインストールが必要）。 |
