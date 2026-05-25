# CaseSearchPlugin 変更内容まとめ

## 概要

`tools/case_search.py` の検索先を、既存の `cases` コンテナから  
新たに構築した営業資料ナレッジベース（`documents` / `chunks` コンテナ）に切り替えました。  
`agent.py` は変更不要です。

---

## 変更ファイル

```
agent-first-meeting/src/agent_first_meeting/tools/case_search.py  ← このファイルのみ変更
```

---

## 変更点詳細

### 1. 参照コンテナの変更

検索先のコンテナを `cases`（1つ）から `documents` / `chunks`（2つ）に変更しました。

```python
# 変更前
self._container = db.get_container_client("cases")

# 変更後
self._documents = db.get_container_client("documents")
self._chunks    = db.get_container_client("chunks")
```

**背景：** 過去の営業資料（提案書・製品カタログ）を `.pptx` 単位で取り込み、  
500文字ごとに分割したチャンクとベクトルを `chunks` コンテナに格納する構成に変わりました。  
`documents` は資料のメタ情報（タイトル・業種・タグなど）を管理します。

---

### 2. 引数に `industry`（業種）を追加

```python
# 変更前
def search_similar_cases(self, query: str, top: int = 3) -> str:

# 変更後
def search_similar_cases(self, query: str, industry: str = "", top: int = 3) -> str:
```

`industry` を指定すると、その業種の資料に絞り込んでからベクトル検索を行います。  
省略した場合は全資料を対象に検索します。  
エージェントの instructions に「顧客の業界を含めたクエリで」とあるため、  
エージェントが自動的に `industry` を渡してくれます。

---

### 3. 検索ロジックをハイブリッド検索に変更

```
変更前：ベクトル検索のみ（casesコンテナに対して1クエリ）

変更後：① キーワード検索（documentsコンテナで業種を絞り込む）
              ↓
        ② ベクトル検索（絞り込んだ範囲でchunksコンテナを検索）
```

**効果：** 例えば「製造業」を指定すると、製造業の資料の中から意味的に近いチャンクだけを取得できます。  
業種を指定しない場合は従来通り全件ベクトル検索にフォールバックします。

---

### 4. 返却フィールドの変更

```python
# 変更前（casesコンテナのフィールド）
# id, title, summary, industry, solutions, outcomes, score

# 変更後（chunksコンテナのフィールド）
# document_id, text, slide_number, score
```

返却形式は従来と同じ **JSON配列文字列** を維持しています。

---

## 追加が必要な `.env` の設定

既存の `.env` に以下を追記してください。  
`settings` オブジェクトが参照する変数名（`cosmos_endpoint` / `cosmos_key`）に合わせて確認をお願いします。

```env
# Cosmos DB ナレッジベース接続情報
COSMOS_ENDPOINT=https://<your-cosmosdb-account-name>.documents.azure.com:443/
COSMOS_KEY=<your-primary-master-key>
```

---

## ナレッジベースのコンテナ構成（参考）

| コンテナ | 役割 | パーティションキー |
|---|---|---|
| `documents` | 資料のメタ情報（タイトル・業種・タグなど） | `/type` |
| `chunks` | 500文字単位のテキスト＋ベクトル | `/document_id` |

データの投入方法・ベクトル検索の有効化手順については  
`knowledge_materials/README.md` を参照してください。

---

## agent.py への影響

**変更不要です。**  
`CaseSearchPlugin` のクラス名・メソッド名（`search_similar_cases`）は変わっていないため、  
`agent.py` 側の `plugins` リストへの登録はそのままで動作します。

```python
# agent.py（変更なし）
plugins=[
    CustomerHistoryPlugin(),
    CaseSearchPlugin(),        # ← クラス名はそのまま
    WebFetchPlugin(),
    DocumentGenPlugin(),
    MeetingRecordPlugin(),
],
```

---

## 動作確認手順

1. `.env` に `COSMOS_ENDPOINT` と `COSMOS_KEY` を追記する
2. `case_search.py` を差し替える
3. エージェントを起動して、顧客情報に「業種」を含めて実行する
4. `search_similar_cases` が呼ばれ、ナレッジベースから関連チャンクが返ってくることを確認する