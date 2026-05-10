# agent-first-meeting API 仕様

## POST /api/first-meeting/generate

初回面談向けアポ資料を生成する。エージェントの思考プロセスは SSE でストリーミングされる。

### リクエスト

```json
{
  "companyName": "株式会社サンプル",
  "industry": "製造業",
  "scale": "中小企業",
  "knownInfo": "DX推進したいが何から手を付けるか不明",
  "salesperson": "佐々木"
}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `companyName` | string | ✅ | 顧客企業名 |
| `industry` | string | ✅ | 業種（例: 製造業, 小売業） |
| `scale` | string | ✅ | 企業規模（例: 中小企業, 大企業） |
| `knownInfo` | string | - | 事前に分かっている課題感などのフリーテキスト |
| `salesperson` | string | - | 担当営業名 |

### レスポンス（SSE）

```
event: thought      data: {"step":"類似事例を探します"}
event: tool         data: {"name":"search_similar_cases","args":{...}}
event: tool_result  data: {"hits": 5}
event: thought      data: {"step":"アウトラインを作成中"}
...
event: done         data: {
  "status": "success",
  "data": {
    "documentUrl": "https://....pptx",
    "meetingId": "mtg_xxx",
    "caseReferences": [{"id":"case_001","title":"..."}],
    "generatedAt": "2026-05-09T..."
  },
  "error": null
}
```

### エラー時

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "...",
    "message": "..."
  }
}
```
