# agent-first-meeting

初回面談向け：類似事例検索・アポ資料生成エージェント

## 概要

営業担当者が顧客情報を入力すると、社内に蓄積された類似事例を検索し、初回アポ資料（PowerPoint）を自動生成します。

- **エージェント基盤**: Azure AI Foundry + Semantic Kernel（Python, single-agent, auto function calling）
- **LLM**: GPT-4.1（Azure OpenAI on Foundry にデプロイ）
- **埋め込みモデル**: text-embedding-3-large
- **データストア**: Azure Cosmos DB（顧客・面談・事例 + Vector Search）
- **資料生成**: python-pptx（6 スライド構成：表紙 / 目次 / 業界向け / 役職向け / 自社商品 / 費用）
- **出力ストレージ**: Azure Blob Storage
- **デプロイ先**: Azure Container Apps

## システム構成図

```mermaid
flowchart LR
    User[営業担当者]

    subgraph Frontend["Streamlit フロント"]
        UI["frontend/main.py<br/>入力フォーム + SSE 表示"]
    end

    subgraph Backend["FastAPI バックエンド (agent-first-meeting)"]
        API["api.py<br/>POST /api/first-meeting/generate<br/>SSE: thought / tool / tool_result / message / done"]
        Agent["agent.py<br/>FirstMeetingAgent<br/>(Semantic Kernel ChatCompletionAgent)<br/>FunctionChoiceBehavior.Auto"]

        subgraph Plugins["SK Plugins (kernel_function)"]
            P1["CustomerHistoryPlugin<br/>get_customer_history"]
            P2["CaseSearchPlugin<br/>search_similar_cases"]
            P3["DocumentGenPlugin<br/>generate_pptx"]
            P4["MeetingRecordPlugin<br/>save_meeting_record"]
        end
    end

    subgraph Azure["Azure (East US 2)"]
        subgraph Foundry["Azure AI Foundry"]
            Chat["gpt-4.1<br/>(chat deployment)"]
            Emb["text-embedding-3-large<br/>dimensions=1536"]
        end

        subgraph Cosmos["Cosmos DB for NoSQL — sales-agent"]
            C1[("customers<br/>/companyId")]
            C2[("meetings<br/>/companyId")]
            C3[("documents<br/>/companyId")]
            C4[("cases<br/>/industry<br/>+ Vector Index (DiskANN)")]
        end

        Blob[("Blob Storage<br/>generated-documents<br/>proposals/*.pptx")]
    end

    User --> UI
    UI -- "httpx SSE" --> API
    API --> Agent
    Agent <--> Chat
    Agent --> P1 & P2 & P3 & P4

    P1 -- "SELECT companyName" --> C1
    P1 -- "ORDER BY round DESC" --> C2
    P2 -- "embed query" --> Emb
    P2 -- "VectorDistance ORDER BY" --> C4
    P3 -- "python-pptx upload + SAS 24h" --> Blob
    P4 -- "upsert (new company)" --> C1
    P4 -- "upsert record (outcomes=null)" --> C2
```

## 実行フロー

```mermaid
sequenceDiagram
    autonumber
    actor Sales as 営業担当者
    participant UI as Streamlit
    participant API as FastAPI<br/>(api.py)
    participant Agent as FirstMeetingAgent<br/>(SK + gpt-4.1)
    participant Cosmos as Cosmos DB
    participant Emb as text-embedding-3-large
    participant Blob as Blob Storage

    Sales->>UI: 会社名/業種/規模/課題感を入力
    UI->>API: POST /api/first-meeting/generate
    API->>Agent: invoke_stream(user_message)

    Note over Agent: auto function calling

    Agent->>Cosmos: get_customer_history(companyName)
    Cosmos-->>Agent: {customer, meetings[]} or null

    Agent->>Emb: embeddings.create(query, dim=1536)
    Emb-->>Agent: vector[1536]
    Agent->>Cosmos: search_similar_cases<br/>(VectorDistance TOP 3)
    Cosmos-->>Agent: cases[] with score

    Note over Agent: 履歴 + 類似事例から<br/>提案タイトル生成

    Agent->>Blob: generate_pptx(title, subtitle)
    Blob-->>Agent: SAS 付き URL (24h)

    Agent->>Cosmos: save_meeting_record<br/>(新規なら customers にも upsert)
    Cosmos-->>Agent: meeting id (mtg_xxx)

    Agent-->>API: streaming (tool / tool_result / message)
    API-->>UI: SSE events
    UI-->>Sales: PPTX URL + 提案根拠 + 次回アクション
```

## エージェントの判断ロジック

```mermaid
flowchart TD
    Start([顧客情報受領]) --> H[get_customer_history]
    H --> Q{customer == null?}
    Q -- "新規" --> S[search_similar_cases<br/>業界/規模/課題で自然文検索]
    Q -- "既存" --> S2["前回 outcomes / nextActions を加味<br/>+ search_similar_cases"]
    S --> T[提案タイトルを 1 つ考案<br/>事例の成果に言及]
    S2 --> T
    T --> G[generate_pptx<br/>表紙のみの PowerPoint]
    G --> R[save_meeting_record<br/>outcomes=null で書き出し]
    R --> Report["ユーザーへ報告<br/>履歴有無 / URL / タイトル根拠 /<br/>確認ポイント / レコード ID"]
    Report --> End([follow-up エージェントへ引き継ぎ])
```

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

エージェントは以下の Semantic Kernel プラグインを `FunctionChoiceBehavior.Auto` で自律的に呼び出します。

| # | ツール名 | プラグイン | 役割 |
|---|---|---|---|
| ① | `get_customer_history` | `CustomerHistoryPlugin` | `customers` / `meetings` から過去情報取得 |
| ② | `search_similar_cases` | `CaseSearchPlugin` | `cases` コンテナを vector 検索（TOP N, DiskANN） |
| ③ | `fetch_url_text` | `WebFetchPlugin` | 顧客 HP の URL を取得し本文テキスト化（最大4000字） |
| ④ | `generate_pptx` | `DocumentGenPlugin` | 6 スライド PPTX 生成 → Blob アップロード（SAS 24h） |
| ⑤ | `save_meeting_record` | `MeetingRecordPlugin` | `meetings` に upsert（follow-up エージェントへの引き継ぎ） |

## テスト

純粋ロジック（PPTX 組み立て / スキーマ / HTML→テキスト変換）は Azure / Semantic Kernel に依存せず単独で実行できます。

```bash
# 依存をインストール（一度だけ）
pip install -e ".[dev]"

# テスト実行
pytest tests/ -v
```

| テストファイル | 対象 | 依存 |
|---|---|---|
| `tests/test_pptx_builder.py` | `_pptx_builder.build_presentation_bytes` の 6 スライド構造 | `python-pptx` のみ |
| `tests/test_schemas.py` | `GenerateRequest` バリデーション / `to_user_message` 整形 | `pydantic` のみ |
| `tests/test_html_to_text.py` | `_html_to_text.strip_html` の HTML 整形 | `beautifulsoup4` のみ |

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
  "salesperson": "佐々木"
}
```

詳細は [docs/api.md](docs/api.md) を参照。
