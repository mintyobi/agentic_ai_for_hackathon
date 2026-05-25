# Azure リソース セットアップ手順（Azure CLI 版）

`agent-first-meeting` を動かすために必要な Azure リソースを **Azure CLI** で作成する手順です。

個人アカウント＋$200 無料クレジット前提で、最小コストになる選択肢で記載しています。
コマンドは Windows **PowerShell** 用に書いていますが、macOS/Linux の bash でも変数定義の構文を `VAR=value` / `$VAR` に置き換えるだけで同じように動きます。

## 目次

- [前提](#前提)
- [作成順序とリージョン方針](#作成順序とリージョン方針)
- [0. 準備（CLI セットアップと共通変数）](#0-準備cli-セットアップと共通変数)
- [1. リソースグループ](#1-リソースグループ)
- [2. Azure AI Foundry（Azure OpenAI）](#2-azure-ai-foundryazure-openai)
- [3. Azure Cosmos DB for NoSQL](#3-azure-cosmos-db-for-nosql)
- [4. Azure Blob Storage](#4-azure-blob-storage)
- [5. .env への反映](#5-env-への反映)
- [6. 後片付け（リソース削除）](#6-後片付けリソース削除)
- [概算コスト](#概算コスト)
- [つまずきポイント](#つまずきポイント)

---

## 前提

- [ ] Azure サブスクリプションが「無料試用版」または個人契約で有効
- [ ] [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (`az`) がインストール済み（`az --version` で 2.60 以上を推奨）
- [ ] [agent-first-meeting/.env.example](../.env.example) をコピーして `.env` を準備済み（最後に値を埋める）

---

## 作成順序とリージョン方針

| 順 | リソース | 用途 |
|---|---|---|
| 1 | リソースグループ | 全リソースの入れ物 |
| 2 | Azure OpenAI（Foundry のベース）＋ GPT-4.1 / text-embedding-3-large デプロイ | LLM・埋め込み |
| 3 | Cosmos DB for NoSQL | 顧客・面談・事例（vector search 込み） |
| 4 | Blob Storage | 生成 PowerPoint の保存先 |

### リージョン

**全リソースを `eastus2` で揃える** ことを推奨します。

- Foundry の GPT-4.1 / text-embedding-3-large は East US 2 で配信されていることが多い
- 同一リージョンに揃えると **リソース間通信が無料 ＆ レイテンシ最小**

---

## 0. 準備（CLI セットアップと共通変数）

### 0-1. ログインとサブスクリプション確認

```powershell
# Windows & Mac
az login
az account show --query "{name:name, id:id, user:user.name}" -o table
```

複数サブスクリプションがある場合は明示的に切り替え：

```powershell
# Windows & Mac
az account set --subscription "<subscription-id-or-name>"
```

### 0-2. プロバイダー登録（初回のみ）

```powershell
# Windows & Mac
az provider register --namespace Microsoft.CognitiveServices
az provider register --namespace Microsoft.DocumentDB
az provider register --namespace Microsoft.Storage

# 登録完了確認（"Registered" になるまで待つ）
"Microsoft.CognitiveServices","Microsoft.DocumentDB","Microsoft.Storage" | % {
  "$_ : $(az provider show -n $_ --query registrationState -o tsv)"
}
```

> ⏱️ **`Microsoft.Storage` は数分かかることがあります。** `Registering` 状態のまま次の Storage 作成に進むと `MissingSubscriptionRegistration` で落ちます。すべて `Registered` になってから先へ進んでください。

### 0-3. モデル可用性とクオータの事前確認（重要）

個人サブスクリプションでは特定モデルのクオータが **0** のことがあります。
リソースを作る前に必ずチェックしてください。

```powershell
# Windows
# eastus2 でリージョン提供されているモデル名・バージョンの一覧
az cognitiveservices model list --location eastus2 `
  --query "[?model.name=='gpt-4.1' || model.name=='gpt-4o' || model.name=='text-embedding-3-large'].{name:model.name, version:model.version}" `
  -o table

# このサブスクリプションに割り当てられているクオータ（limit > 0 のものだけ）
az cognitiveservices usage list --location eastus2 -o json `
  | ConvertFrom-Json `
  | ? { $_.limit -gt 0 -and ($_.name.value -like "*gpt-4*" -or $_.name.value -like "*embedding-3-large*") } `
  | % { "{0,-55} limit={1}" -f $_.name.value, $_.limit }
```

```bash
# Mac & Linux
az cognitiveservices model list --location eastus2 \
  --query "[?model.name=='gpt-4.1' || model.name=='gpt-4o' || model.name=='text-embedding-3-large'].{name:model.name, version:model.version}" \
  -o table

az cognitiveservices usage list --location eastus2 -o json \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
filtered = [x for x in data if x['limit'] > 0 and ('gpt-4' in x['name']['value'] or 'embedding-3-large' in x['name']['value'])]
for x in filtered:
    print(f\"{x['name']['value']:<55} limit={x['limit']}\")
"
```

> 🛑 **本ガイドは当初 `gpt-4.1` を想定していますが、`OpenAI.GlobalStandard.gpt-4.1` の limit が 0 のサブスクリプションが多数あります。** その場合は §2-2 で `gpt-4o` を代わりにデプロイしてください（コードは `.env` でモデル名を抽象化しているため変更箇所は 1 行）。

### 0-3. 共通変数（以降のコマンドで再利用）

リソース名のうち `<unique>` 部分はグローバル一意である必要があるので、自分のイニシャル＋日付などで置き換えてください（例: `mb20260518`）。

```powershell
$LOCATION       = "eastus2"
$RG             = "rg-sales-agent"

$AOAI_NAME      = "aoai-sales-agent-<unique>"   # Azure OpenAI アカウント名
$CHAT_DEPLOY    = "gpt-4o"                      # チャットデプロイ名（.env と一致させる）。クオータがあれば gpt-4.1 でも可
$EMBED_DEPLOY   = "text-embedding-3-large"      # 埋め込みデプロイ名（.env と一致させる）

$COSMOS_NAME    = "cosmos-sales-agent-<unique>" # Cosmos DB アカウント名
$COSMOS_DB      = "sales-agent"                 # データベース名

$STORAGE_NAME   = "stsalesagent<unique>"        # Storage アカウント名（小文字英数のみ・24文字以内）
$BLOB_CONTAINER = "generated-documents"
```

> 💡 同じシェルセッションを閉じる前に最後まで通すか、`.ps1` スクリプトとして保存しておくと楽です。

#### Mac の場合

```sh
LOCATION="eastus2"
RG="rg-sales-agent"

AOAI_NAME="aoai-sales-agent-<unique>"   # Azure OpenAI アカウント名
CHAT_DEPLOY="gpt-4o"                    # チャットデプロイ名（.env と一致させる）。クオータがあれば gpt-4.1 でも可
EMBED_DEPLOY="text-embedding-3-large"   # 埋め込みデプロイ名（.env と一致させる）

COSMOS_NAME="cosmos-sales-agent-<unique>" # Cosmos DB アカウント名
COSMOS_DB="sales-agent"                   # データベース名

STORAGE_NAME="stsalesagent<unique>"     # Storage アカウント名（小文字英数のみ・24文字以内）
BLOB_CONTAINER="generated-documents"
```

💡 同じターミナルセッションを閉じる前に最後まで通すか、.sh ファイルとして保存しておくと楽です。

```bash
source setup.sh
```

---

## 1. リソースグループ

```powershell
# Windows & Mac
az group create --name $RG --location $LOCATION
```

---

## 2. Azure AI Foundry（Azure OpenAI）

Foundry プロジェクトの実体は Azure OpenAI リソースなので、CLI からは `cognitiveservices account` として作成します。

### 2-1. Azure OpenAI アカウント作成

```powershell
# Windows
az cognitiveservices account create `
  --name $AOAI_NAME `
  --resource-group $RG `
  --location $LOCATION `
  --kind OpenAI `
  --sku S0 `
  --custom-domain $AOAI_NAME `
  --yes
```

```bash
# Mac & Linux
az cognitiveservices account create \
  --name $AOAI_NAME \
  --resource-group $RG \
  --location $LOCATION \
  --kind OpenAI \
  --sku S0 \
  --custom-domain $AOAI_NAME \
  --yes
```

> `--custom-domain` を付けると `https://<name>.openai.azure.com/` 形式の固定エンドポイントが発行され、`.env` の `AZURE_OPENAI_ENDPOINT` にそのまま入れられます。

### 2-2. チャットモデルのデプロイ

§0-3 で確認したクオータをもとに **デプロイするモデルを 1 つ選んでください**。

#### 推奨：`gpt-4o`（多くの個人サブスクで `GlobalStandard` が即使える）

```powershell
# Windows
az cognitiveservices account deployment create `
  --name $AOAI_NAME `
  --resource-group $RG `
  --deployment-name $CHAT_DEPLOY `
  --model-name "gpt-4o" `
  --model-version "2024-11-20" `
  --model-format OpenAI `
  --sku-name "GlobalStandard" `
  --sku-capacity 50
```

```bash
# Mac & Linux
az cognitiveservices account deployment create \
  --name $AOAI_NAME \
  --resource-group $RG \
  --deployment-name $CHAT_DEPLOY \
  --model-name "gpt-4o" \
  --model-version "2024-11-20" \
  --model-format OpenAI \
  --sku-name "GlobalStandard" \
  --sku-capacity 50
```

#### `gpt-4.1` が引ける場合

§0-3 で `OpenAI.GlobalStandard.gpt-4.1` の limit が正の値で表示されていれば、以下に差し替え可能です。`$CHAT_DEPLOY` を `"gpt-4.1"` に変更してから実行してください。

```powershell
# Windows
az cognitiveservices account deployment create `
  --name $AOAI_NAME `
  --resource-group $RG `
  --deployment-name $CHAT_DEPLOY `
  --model-name "gpt-4.1" `
  --model-version "2025-04-14" `
  --model-format OpenAI `
  --sku-name "GlobalStandard" `
  --sku-capacity 50
```

```bash
# Mac & Linux
az cognitiveservices account deployment create \
  --name $AOAI_NAME \
  --resource-group $RG \
  --deployment-name $CHAT_DEPLOY \
  --model-name "gpt-4.1" \
  --model-version "2025-04-14" \
  --model-format OpenAI \
  --sku-name "GlobalStandard" \
  --sku-capacity 50
```

> 📝 個人 Azure サブスクリプションは Anthropic Claude / GPT-4.1 などプレミアムモデルが初期クオータ 0 のことが多く、本ガイドでは確実に動く `gpt-4o` を既定にしています。コードは `.env` で `AZURE_OPENAI_CHAT_DEPLOYMENT` を読むので、後日上位モデルのクオータが通れば 1 行変更で差し替え可能。

### 2-3. text-embedding-3-large のデプロイ

```powershell
# Windows
az cognitiveservices account deployment create `
  --name $AOAI_NAME `
  --resource-group $RG `
  --deployment-name $EMBED_DEPLOY `
  --model-name "text-embedding-3-large" `
  --model-version "1" `
  --model-format OpenAI `
  --sku-name "Standard" `
  --sku-capacity 30
```

```bash
az cognitiveservices account deployment create \
  --name $AOAI_NAME \
  --resource-group $RG \
  --deployment-name $EMBED_DEPLOY \
  --model-name "text-embedding-3-large" \
  --model-version "1" \
  --model-format OpenAI \
  --sku-name "Standard" \
  --sku-capacity 30
```

### 2-4. エンドポイントとキーを取得

```powershell
$AOAI_ENDPOINT = az cognitiveservices account show `
  --name $AOAI_NAME --resource-group $RG `
  --query "properties.endpoint" -o tsv

$AOAI_KEY = az cognitiveservices account keys list `
  --name $AOAI_NAME --resource-group $RG `
  --query "key1" -o tsv

Write-Host "AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT"
Write-Host "AZURE_OPENAI_API_KEY=$AOAI_KEY"
```

```bash
AOAI_ENDPOINT=$(az cognitiveservices account show \
  --name $AOAI_NAME --resource-group $RG \
  --query "properties.endpoint" -o tsv)

AOAI_KEY=$(az cognitiveservices account keys list \
  --name $AOAI_NAME --resource-group $RG \
  --query "key1" -o tsv)

echo "AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT"
echo "AZURE_OPENAI_API_KEY=$AOAI_KEY"
```

---

## 3. Azure Cosmos DB for NoSQL

### 3-1. アカウント作成（Serverless + Vector Search 有効）

```powershell
# Windows
az cosmosdb create `
  --name $COSMOS_NAME `
  --resource-group $RG `
  --locations regionName=$LOCATION failoverPriority=0 isZoneRedundant=False `
  --capabilities EnableServerless EnableNoSQLVectorSearch `
  --default-consistency-level Session
```

```bash
# Mac & Linux
az cosmosdb create \
  --name $COSMOS_NAME \
  --resource-group $RG \
  --locations regionName=$LOCATION failoverPriority=0 isZoneRedundant=False \
  --capabilities EnableServerless EnableNoSQLVectorSearch \
  --default-consistency-level Session
```

> 💡 Serverless はアイドル時のコストが 0 になります。Free Tier 割引は Provisioned 専用のため Serverless とは併用不可。Serverless の方が個人利用にはむしろ安く済みます。

### 3-2. データベース作成

```powershell
# Windows
az cosmosdb sql database create `
  --account-name $COSMOS_NAME `
  --resource-group $RG `
  --name $COSMOS_DB
```

```bash
# Mac & Linux
az cosmosdb sql database create \
  --account-name $COSMOS_NAME \
  --resource-group $RG \
  --name $COSMOS_DB
```

### 3-3. コンテナ 3 つを作成（普通のコンテナ）

`documents` / `chunks` / `templates` の3つを作成する。

```powershell
# Windows
az cosmosdb sql container create `
  --account-name $COSMOS_NAME --resource-group $RG `
  --database-name $COSMOS_DB `
  --name documents --partition-key-path "/type"

az cosmosdb sql container create `
  --account-name $COSMOS_NAME --resource-group $RG `
  --database-name $COSMOS_DB `
  --name chunks --partition-key-path "/document_id"

az cosmosdb sql container create `
  --account-name $COSMOS_NAME --resource-group $RG `
  --database-name $COSMOS_DB `
  --name templates --partition-key-path "/target_industry"
```

```bash
# Mac & Linux
az cosmosdb sql container create \
  --account-name $COSMOS_NAME --resource-group $RG \
  --database-name $COSMOS_DB \
  --name documents --partition-key-path "/type"

az cosmosdb sql container create \
  --account-name $COSMOS_NAME --resource-group $RG \
  --database-name $COSMOS_DB \
  --name chunks --partition-key-path "/document_id"

az cosmosdb sql container create \
  --account-name $COSMOS_NAME --resource-group $RG \
  --database-name $COSMOS_DB \
  --name templates --partition-key-path "/target_industry"
```

### 3-4. `chunks` コンテナに Vector Index を設定

#### 3-4-1. ポリシーJSONを書き出す

```powershell
# Windows
@'
{
  "vectorEmbeddings": [{
    "path": "/embedding",
    "dataType": "float32",
    "distanceFunction": "cosine",
    "dimensions": 1536
  }]
}
'@ | Set-Content -Encoding utf8 vector-policy.json

@'
{
  "indexingMode": "consistent",
  "includedPaths": [{"path": "/*"}],
  "excludedPaths": [{"path": "/embedding/*"}],
  "vectorIndexes": [{
    "path": "/embedding",
    "type": "quantizedFlat"
  }]
}
'@ | Set-Content -Encoding utf8 index-policy.json
```

```bash
# Mac & Linux
cat > vector-policy.json << 'EOF'
{
  "vectorEmbeddings": [{
    "path": "/embedding",
    "dataType": "float32",
    "distanceFunction": "cosine",
    "dimensions": 1536
  }]
}
EOF

cat > index-policy.json << 'EOF'
{
  "indexingMode": "consistent",
  "includedPaths": [{"path": "/*"}],
  "excludedPaths": [{"path": "/embedding/*"}],
  "vectorIndexes": [{
    "path": "/embedding",
    "type": "quantizedFlat"
  }]
}
EOF
```

#### 3-4-2. `chunks` コンテナに適用

```powershell
# Windows
az cosmosdb sql container update `
  --account-name $COSMOS_NAME --resource-group $RG `
  --database-name $COSMOS_DB `
  --name chunks `
  --vector-embeddings @vector-policy.json `
  --idx @index-policy.json
```

```bash
# Mac & Linux
az cosmosdb sql container update \
  --account-name $COSMOS_NAME --resource-group $RG \
  --database-name $COSMOS_DB \
  --name chunks \
  --vector-embeddings @vector-policy.json \
  --idx @index-policy.json
```

### 3-5. エンドポイントとキーを取得

```powershell
# Windows
$COSMOS_ENDPOINT = az cosmosdb show `
  --name $COSMOS_NAME --resource-group $RG `
  --query "documentEndpoint" -o tsv

$COSMOS_KEY = az cosmosdb keys list `
  --name $COSMOS_NAME --resource-group $RG `
  --query "primaryMasterKey" -o tsv

Write-Host "COSMOS_ENDPOINT=$COSMOS_ENDPOINT"
Write-Host "COSMOS_KEY=$COSMOS_KEY"
```

```bash
# Mac & Linux
COSMOS_ENDPOINT=$(az cosmosdb show \
  --name $COSMOS_NAME --resource-group $RG \
  --query "documentEndpoint" -o tsv)

COSMOS_KEY=$(az cosmosdb keys list \
  --name $COSMOS_NAME --resource-group $RG \
  --query "primaryMasterKey" -o tsv)

echo "COSMOS_ENDPOINT=$COSMOS_ENDPOINT"
echo "COSMOS_KEY=$COSMOS_KEY"
```

---

## 4. Azure Blob Storage

### 4-1. ストレージアカウント作成

```powershell
# Windows
az storage account create `
  --name $STORAGE_NAME `
  --resource-group $RG `
  --location $LOCATION `
  --sku Standard_LRS `
  --kind StorageV2 `
  --allow-blob-public-access false
```

```bash
# Mac & Linux
az storage account create \
  --name $STORAGE_NAME \
  --resource-group $RG \
  --location $LOCATION \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false
```

### 4-2. コンテナ作成

```powershell
# Windows
az storage container create `
  --account-name $STORAGE_NAME `
  --name $BLOB_CONTAINER `
  --auth-mode login
```

```bash
# Mac & Linux
az storage container create \
  --account-name $STORAGE_NAME \
  --name $BLOB_CONTAINER \
  --auth-mode login
```

### 4-3. ロールを自分に付与（DefaultAzureCredential で書き込めるようにする）

```powershell
# Windows
$ME = az ad signed-in-user show --query id -o tsv
$STORAGE_ID = az storage account show `
  --name $STORAGE_NAME --resource-group $RG `
  --query id -o tsv

az role assignment create `
  --assignee $ME `
  --role "Storage Blob Data Contributor" `
  --scope $STORAGE_ID
```

```bash
# Mac & Linux
ME=$(az ad signed-in-user show --query id -o tsv)
STORAGE_ID=$(az storage account show \
  --name $STORAGE_NAME --resource-group $RG \
  --query id -o tsv)

az role assignment create \
  --assignee $ME \
  --role "Storage Blob Data Contributor" \
  --scope $STORAGE_ID
```

> 🛑 このロール付与を忘れると、ローカル開発時に Blob 書き込みで 403 エラーになります。

### 4-4. 接続情報を取得

```powershell
# Windows
$BLOB_URL = az storage account show `
  --name $STORAGE_NAME --resource-group $RG `
  --query "primaryEndpoints.blob" -o tsv

# SAS 付きダウンロード URL を発行したい場合はアカウントキーも取得
$BLOB_KEY = az storage account keys list `
  --account-name $STORAGE_NAME --resource-group $RG `
  --query "[0].value" -o tsv

Write-Host "BLOB_ACCOUNT_URL=$BLOB_URL"
Write-Host "BLOB_ACCOUNT_KEY=$BLOB_KEY"
```

```bash
# Mac & Linux
BLOB_URL=$(az storage account show \
  --name $STORAGE_NAME --resource-group $RG \
  --query "primaryEndpoints.blob" -o tsv)

# SAS 付きダウンロード URL を発行したい場合はアカウントキーも取得
BLOB_KEY=$(az storage account keys list \
  --account-name $STORAGE_NAME --resource-group $RG \
  --query "[0].value" -o tsv)

echo "BLOB_ACCOUNT_URL=$BLOB_URL"
echo "BLOB_ACCOUNT_KEY=$BLOB_KEY"
```

> 💡 `BLOB_ACCOUNT_KEY` を `.env` に入れると、生成 PowerPoint のダウンロード URL が SAS 付き（24時間有効）になります。空にすると `DefaultAzureCredential` で認証だけ通り、URL は素のものを返します（プライベートコンテナなので URL 直叩きでは開けません）。**ローカル開発では Key を入れる**のが手っ取り早いです。

---

## 5. .env への反映

ここまでで取得した値を `.env` に書き込みます。

```powershell
cp agent-first-meeting/.env.example agent-first-meeting/.env
```

エディタで `agent-first-meeting/.env` を開いて以下のように記入：

| `.env` キー | 値 |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | `$AOAI_ENDPOINT` の値 |
| `AZURE_OPENAI_API_KEY` | `$AOAI_KEY` の値 |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | §2-2 でデプロイ名（既定 `gpt-4o`） |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | `text-embedding-3-large` |
| `AZURE_OPENAI_API_VERSION` | `2024-12-01-preview` |
| `COSMOS_ENDPOINT` | `$COSMOS_ENDPOINT` の値 |
| `COSMOS_KEY` | `$COSMOS_KEY` の値 |
| `COSMOS_DATABASE` | `sales-agent` |
| `BLOB_ACCOUNT_URL` | `$BLOB_URL` の値 |
| `BLOB_CONTAINER` | `generated-documents` |
| `BLOB_ACCOUNT_KEY` | `$BLOB_KEY` の値（任意、SAS 発行用） |

PowerShell から `.env` を自動生成したい場合はこんな書き方も可能（PS 5.1 でも BOM 無し UTF-8 で書き出します）：

```powershell
$envText = @"
AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT
AZURE_OPENAI_API_KEY=$AOAI_KEY
AZURE_OPENAI_CHAT_DEPLOYMENT=$CHAT_DEPLOY
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$EMBED_DEPLOY
AZURE_OPENAI_API_VERSION=2024-12-01-preview
COSMOS_ENDPOINT=$COSMOS_ENDPOINT
COSMOS_KEY=$COSMOS_KEY
COSMOS_DATABASE=$COSMOS_DB
BLOB_ACCOUNT_URL=$BLOB_URL
BLOB_CONTAINER=$BLOB_CONTAINER
BLOB_ACCOUNT_KEY=$BLOB_KEY
APP_LOG_LEVEL=INFO
"@

[System.IO.File]::WriteAllText(
  "$PWD\agent-first-meeting\.env",
  $envText,
  [System.Text.UTF8Encoding]::new($false)
)
```

```bash
# Mac & Linux
cat > agent-first-meeting/.env << EOF
AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT
AZURE_OPENAI_API_KEY=$AOAI_KEY
AZURE_OPENAI_CHAT_DEPLOYMENT=$CHAT_DEPLOY
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$EMBED_DEPLOY
AZURE_OPENAI_API_VERSION=2024-12-01-preview
COSMOS_ENDPOINT=$COSMOS_ENDPOINT
COSMOS_KEY=$COSMOS_KEY
COSMOS_DATABASE=$COSMOS_DB
BLOB_ACCOUNT_URL=$BLOB_URL
BLOB_CONTAINER=$BLOB_CONTAINER
BLOB_ACCOUNT_KEY=$BLOB_KEY
APP_LOG_LEVEL=INFO
EOF
```

> ⚠️ `.env` は絶対に Git にコミットしないでください（`.gitignore` で除外済み）。

### 動作確認用シードデータの投入

`.env` を埋めたら、最初のスモークテスト用にダミーデータを入れておきます。

```powershell
cd agent-first-meeting
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip wheel setuptools
pip install -e ".[dev]"

python scripts/check_foundry.py        # Foundry 疎通
python scripts/ingest_documents.py     # data/ の PPTX を documents/chunks へ取り込み（chunks も自動作成）
python scripts/seed_customer.py        # customers / meetings に既存顧客 1件 投入
python scripts/check_vector_search.py  # vector 検索が動くことを確認
python scripts/check_pptx_blob.py      # Blob への pptx アップロードを確認
```

```bash
cd agent-first-meeting
~/.pyenv/versions/3.11.9/bin/python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -e ".[dev]"

python scripts/check_foundry.py        # Foundry 疎通
python scripts/ingest_documents.py     # data/ の PPTX を documents/chunks へ取り込み
python scripts/check_vector_search.py  # vector 検索が動くことを確認
python scripts/check_pptx_blob.py      # Blob への pptx アップロードを確認
```

> 💡 `scripts/ingest_documents.py` は `chunks` コンテナをベクトルポリシー付きで自動作成する
> （Python SDK の `create_container_if_not_exists(..., vector_embedding_policy=...)` を使用）。
> §3-4 の `az rest` による手動作成を行わなくても、このスクリプトだけで `documents`/`chunks` が揃う。

---

## 6. 後片付け（リソース削除）

ハッカソン終了後にコストを止めたい場合、リソースグループごと一気に消すのが安全・確実です。

```powershell
az group delete --name $RG --yes --no-wait
```

---

## 概算コスト

個人クレジット $200 で十分賄える想定。

| リソース | 料金イメージ |
|---|---|
| Foundry: GPT-4.1 | 入力 $2 / 出力 $8（per 1M tokens）。デモ程度で月 $3〜$8 |
| Foundry: text-embedding-3-large | $0.13 / 1M tokens。ほぼ無視できる |
| Cosmos DB Serverless | $0.25 / 1M RU、25GB まで $0.25/GB/月。デモ用途は月 $1 程度 |
| Blob Storage LRS | 数十GB 程度なら月 $1 未満 |
| **合計目安** | **月 $10〜$20**（$200 クレジットで余裕） |

---

## つまずきポイント

| 症状 | 原因と対処 |
|---|---|
| `az cognitiveservices account deployment create` で「クオータ不足」 | §0-3 のクオータ確認コマンドでリージョン × SKU × モデルの割当量を確認。`OpenAI.GlobalStandard.gpt-4.1` などが limit=0 なら、本ガイドが既定にしている `gpt-4o` に切り替え。 |
| Anthropic Claude / GPT-4.1 などプレミアムモデルが全リージョンでクオータ 0 | 個人サブスクリプションでは多くの上位モデルが初期クオータ 0 で要申請。本ガイドは確実に動く `gpt-4o` を既定としている。 |
| `--vector-embedding-policy` が認識されない | **Azure CLI は `az cosmosdb sql container create --vector-embedding-policy` を 2026 年 5 月時点で未サポート**（`cosmosdb-preview` 拡張を入れても同じ）。§3-4 の `az rest` 経由で ARM REST API を直接叩くこと。 |
| `Cosmos DB 作成時に `EnableNoSQLVectorSearch` が unknown` と言われる | Azure CLI 本体が古い。`az upgrade` で最新版（2.60+）へ。 |
| Storage アカウント作成が `MissingSubscriptionRegistration` で失敗 | §0-2 の `Microsoft.Storage` 登録が `Registering` のまま。`az provider show -n Microsoft.Storage --query registrationState -o tsv` が `Registered` になるまで（数分かかることあり）待つ。 |
| Cosmos DB の Free Tier を使いたい | Free Tier は Provisioned 専用なので Serverless とは併用不可。デモ用途は Serverless だけで十分安価。どうしても Free Tier 使いたい場合は `--capabilities` から `EnableServerless` を外し、`--enable-free-tier true` を付け、各コンテナに `--throughput 400` 等を指定する。 |
| `cases-container.json` を `az rest` に渡したら JSON パースエラー | `Out-File -Encoding utf8` が PowerShell 5.1 で BOM 付き UTF-8 を出力したのが原因。§3-4-1 の `[System.IO.File]::WriteAllText` で BOM 無しで書き出すこと。 |
| Blob 書き込みで 403 エラー | (a) `.env` に `BLOB_ACCOUNT_KEY` を入れていれば本来不要だが、Managed Identity 系で動かしているなら 4-3 のロール割り当て（**Storage Blob Data Contributor**）忘れ。ロール反映には数十秒〜数分かかることも。 |
| ローカル開発で `DefaultAzureCredential` が失敗する | ターミナルで `az login` が必要。ロール反映待ちなら数分置いてから再実行。`.env` に `BLOB_ACCOUNT_KEY` を入れる方が手っ取り早い（ローカル開発限定）。 |
| `--custom-domain` を指定し忘れた | `https://<region>.api.cognitive.microsoft.com/` 形式になり、Foundry の OpenAI クライアントから叩けない。`az cognitiveservices account update --custom-domain $AOAI_NAME` で後付け可能。 |
