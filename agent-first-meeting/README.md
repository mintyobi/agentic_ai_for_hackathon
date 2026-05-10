# agent-first-meeting

初回面談向け：類似事例検索・アポ資料生成エージェント

## 概要

営業担当者が顧客情報を入力すると、社内に蓄積された類似事例を検索し、初回アポ資料（PowerPoint）を自動生成します。

- **エージェント基盤**: Azure AI Foundry + Semantic Kernel（Python, single-agent, auto function calling）
- **LLM**: GPT-4.1（Azure OpenAI on Foundry にデプロイ）
- **埋め込みモデル**: text-embedding-3-large
- **データストア**: Azure Cosmos DB（顧客・面談・事例 + Vector Search）
- **資料生成**: python-pptx（MVP は表紙1枚のみ）
- **出力ストレージ**: Azure Blob Storage
- **デプロイ先**: Azure Container Apps

## ディレクトリ構成

```
agent-first-meeting/
├── pyproject.toml
├── README.md
├── .env.example
├── src/
│   └── agent_first_meeting/    # Python パッケージ本体
└── tests/                      # テストコード
└── docs/                       # このエージェントの仕様書
```

## セットアップ

### 0. Azure リソースの準備

Foundry / Cosmos DB / Blob Storage を Azure 上に作成します。手順は [docs/azure_setup.md](docs/azure_setup.md) を参照。

### 1. ローカル環境

```bash
# 仮想環境を作成
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 依存をインストール（開発用）
pip install -e ".[dev]"

# 環境変数を設定
cp .env.example .env
# .env を開いて Azure リソースの接続情報を記入
```

## エージェントのツール構成

| # | ツール名 | 役割 |
|---|---|---|
| ① | `search_similar_cases` | Cosmos DB の `cases` コンテナを vector + filter で検索 |
| ② | `get_customer_history` | `customers` / `meetings` から過去情報取得 |
| ③ | `draft_proposal_outline` | LLM がアウトライン JSON を生成 |
| ④ | `generate_pptx` | python-pptx でテンプレ穴埋め → Blob にアップロード |
| ⑤ | `save_meeting_record` | `meetings` コンテナに記録（follow-up エージェントへの引き継ぎ） |

## API

```
POST /api/first-meeting/generate
Content-Type: application/json
Accept: text/event-stream

Request:
{
  "companyName": "株式会社サンプル",
  "industry": "製造業",
  "scale": "中小企業",
  "knownInfo": "DX推進したいが何から手を付けるか不明",
  "salesperson": "ともや"
}
```

詳細は [docs/api.md](docs/api.md) を参照。
