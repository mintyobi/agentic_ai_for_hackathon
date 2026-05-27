# アーキテクチャ図（Microsoft Agent Hackathon 提出用）

> Zenn は mermaid コードブロックをそのまま図として描画します。以下をそのまま記事に貼れば「アーキテクチャ図の埋め込み」要件を満たせます。

## 1. システム全体（デプロイ / データフロー）

```mermaid
flowchart TB
    User["営業担当者"]

    subgraph Azure["Microsoft Azure（eastus2）"]
        subgraph ACA["Azure Container Apps 環境: cae-sales-agent"]
            FE["ca-frontend<br/>Streamlit UI<br/>external ingress + Entra Easy Auth"]
            API["ca-agent-first-meeting<br/>FastAPI + Semantic Kernel<br/>internal ingress（非公開）"]
        end
        AOAI["Azure OpenAI (Microsoft Foundry)<br/>gpt-4.1 / text-embedding-3-large"]
        COSMOS[("Azure Cosmos DB（serverless）<br/>customers / meetings<br/>documents / chunks（Vector Search）")]
        BLOB[("Azure Blob Storage<br/>generated-documents")]
        ACR["Azure Container Registry"]
        ENTRA["Microsoft Entra ID<br/>Easy Auth / Managed Identity"]
    end

    User -->|"HTTPS（要ログイン）"| FE
    FE -->|"内部HTTPS / SSE<br/>POST /api/first-meeting/generate"| API
    API -->|"ChatCompletion（gpt-4.1）"| AOAI
    API -->|"埋め込み生成 + ベクトル検索"| COSMOS
    API -->|"顧客・面談履歴 読み書き"| COSMOS
    API -->|"PPTX アップロード + SAS 発行"| BLOB
    FE -.->|"Easy Auth"| ENTRA
    API -.->|"Managed Identity で各サービス認証"| ENTRA
    ACR -.->|"イメージ pull（MI / AcrPull）"| ACA
```

## 2. エージェント内部（Semantic Kernel + ツール群）

```mermaid
flowchart LR
    AGENT["Semantic Kernel<br/>ChatCompletionAgent<br/>gpt-4.1 / Auto function calling"]
    AGENT --> T1["get_customer_history<br/>Cosmos: customers / meetings"]
    AGENT --> T2["search_similar_cases<br/>Cosmos Vector Search（過去事例）"]
    AGENT --> T3["fetch_url_text<br/>顧客HP取得（SSRF対策）"]
    AGENT --> T4["generate_pptx<br/>python-pptx → Blob + SAS URL"]
    AGENT --> T5["save_meeting_record<br/>Cosmos: meetings（引き継ぎ点）"]
```

## 3. 「初回 → 2回目以降」のデータ引き継ぎ

```mermaid
flowchart TD
    A["初回面談"] --> B["save_meeting_record<br/>outcomes=null で保存"]
    B --> C["面談実施"]
    C --> D["2回目以降：前回メモを入力"]
    D --> E["サーバ側で record_meeting_outcomes<br/>前回 round に outcomes を確定"]
    E --> F["get_customer_history で<br/>前回 outcomes / nextActions を参照"]
    F --> G["継続提案として一歩進めた資料を生成"]
    G --> B
```

## コンポーネントと採用技術（ハッカソン要件との対応）

| レイヤ | 採用技術 | ハッカソン要件 |
|---|---|---|
| 実行基盤 | **Azure Container Apps**（API / フロント） | 【必須】Azure 実行基盤 ✅ |
| 生成AI / エージェント | **Azure OpenAI(Foundry) gpt-4.1 + Semantic Kernel** | 【必須】Microsoft AI 技術 ✅ |
| データ × AI（RAG） | **Azure Cosmos DB Vector Search**（1536次元） | 【推奨】Cosmos DB 申告 ✅ |
| 認証 | **Microsoft Entra ID**（Easy Auth + Managed Identity） | 【推奨】Entra ID 申告 ✅ |
| ストレージ | Azure Blob Storage（生成PPTX） | — |
| レジストリ | Azure Container Registry | — |
