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
| `homepageUrl` | string | - | 顧客公式 HP。本文を取得して提案根拠に使う |
| `contactName` / `contactDepartment` / `contactPosition` | string | - | 取引相手の氏名 / 部署 / 役職 |
| `meetingStatus` | string | - | `"first"`（既定）= 初回、`"followup"` = 2回目以降 |
| `lastMeetingNotes` | string | - | （followup 時）前回面談の実績メモ。詳細は下記 |

> このエンドポイントは **初回（first）と 2回目以降（followup）の両モード** を `meetingStatus` で切り替える単一窓口です。

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
    "caseReferences": [
      {
        "id": "doc_001",
        "title": "技能継承課題に対する AI ナレッジベース導入",
        "type": "proposal",
        "industry": "製造業"
      }
    ],
    "generatedAt": "2026-05-09T..."
  },
  "error": null
}

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

## follow-up（2回目以降）モード

`meetingStatus: "followup"` を指定すると、継続提案用のエージェントが起動する。

### 前提チェック

過去の面談（`meetings`）が 1 件も無い顧客に対して followup を呼ぶと、エージェントを
起動せず即座にエラーを返す（`error.code = "NoPreviousMeeting"`）。先に初回（first）を
実施しておく必要がある。

### 前回実績（outcomes）の記録

`lastMeetingNotes` に前回面談で実際に起きたこと（反応・合意事項・宿題など）を渡すと、
エージェントが **`record_meeting_outcomes`** ツールで直近 meeting の `outcomes` を埋め、
`status` を `done` に更新する。これにより「前回の成果を踏まえた継続提案」が成立する。

- `lastMeetingNotes` を省略した場合は、既に `meetings` に記録済みの `outcomes` を根拠に使う。
- 今回生成した meeting の `outcomes` は `null` で保存され、次回の followup 呼び出し時に
  改めて `lastMeetingNotes` 経由で埋められる契約。

### リクエスト例（followup）

```json
{
  "companyName": "株式会社既存お得意様",
  "industry": "製造業",
  "scale": "中小企業",
  "salesperson": "佐々木",
  "meetingStatus": "followup",
  "lastMeetingNotes": "経営層は前向き。技能継承を最優先課題と再確認。RAG 事例の提示を依頼された。"
}
```

`done` イベントの `data.invokedTools` には、初回と異なり `get_customer_history` が必須で含まれる
（`lastMeetingNotes` を渡した場合は `record_meeting_outcomes` も呼ばれる）。
