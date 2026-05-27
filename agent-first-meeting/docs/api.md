# agent-first-meeting API 仕様

## POST /api/first-meeting/generate

初回・2回目以降のアポ/継続提案資料を生成する**単一の窓口**。`meetingStatus` でモードを切り替える。
エージェントの進捗・最終レポートは SSE（Server-Sent Events）でストリーミングされる。

> 実行フローの図解（初回/followup のシーケンス、ファイル・ツール単位）は [flow.md](./flow.md) を参照。

### リクエスト

```json
{
  "companyName": "株式会社サンプル",
  "industry": "製造業",
  "scale": "中小企業",
  "knownInfo": "DX推進したいが何から手を付けるか不明",
  "salesperson": "佐々木",
  "homepageUrl": "https://example.co.jp",
  "contactName": "山田太郎",
  "contactDepartment": "経営企画部",
  "contactPosition": "部長",
  "meetingStatus": "first"
}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `companyName` | string | ✅ | 顧客企業名 |
| `industry` | string | ✅ | 業種（例: 製造業, 小売業） |
| `scale` | string | ✅ | 企業規模（例: 中小企業, 大企業） |
| `knownInfo` | string | - | 事前に分かっている課題感などのフリーテキスト |
| `salesperson` | string | - | 担当営業名 |
| `homepageUrl` | string | - | 顧客公式 HP。本文を取得して提案根拠に使う（**取得はこのホストに限定**） |
| `contactName` / `contactDepartment` / `contactPosition` | string | - | 取引相手の氏名 / 部署 / 役職 |
| `meetingStatus` | string | - | `"first"`（既定）= 初回、`"followup"` = 2回目以降 |
| `lastMeetingNotes` | string | - | （followup 時）前回面談の実績メモ。詳細は下記 |

### レスポンス（SSE イベント）

| event | data | 説明 |
|---|---|---|
| `thought` | `{"text": "..."}` | 進捗メッセージ（起動中・サーバ側記録中など） |
| `tool` | `{"name": "ツール名"}` | ツール呼び出し開始（Filter 捕捉分をチャンク間で配信） |
| `tool_result` | `{"name": "ツール名"}` | ツール完了 |
| `message` | `{"text": "..."}` | エージェントの最終レポート（逐次） |
| `done` | 下記 | 完了（成功 / 部分成功 / エラー） |

`done` の `data`（成功・部分成功時）:

```json
{
  "status": "success",
  "data": {
    "documentUrl": "https://....pptx?<SAS>",
    "message": "（エージェントの最終レポート全文）",
    "invokedTools": ["generate_pptx", "get_customer_history", "save_meeting_record", "search_similar_cases"],
    "meetingId": "mtg_cus_xxxx_0001",
    "warnings": []
  },
  "error": null
}
```

#### `status` の意味

| status | 条件 |
|---|---|
| `success` | 資料が生成され、必須ツールがすべて呼ばれた |
| `partial` | 資料は生成されたが必須ツールが欠けている（`warnings` に詳細）。完全成功にすると次回 followup の前提が静かに壊れるため区別する |
| `error` | 資料が生成されなかった（`error.code = "NoDocument"`）等 |

必須ツール:
- 初回: `generate_pptx`, `save_meeting_record`
- followup: `get_customer_history`, `generate_pptx`, `save_meeting_record`

### エラー時

```json
{
  "status": "error",
  "data": null,
  "error": { "code": "NoPreviousMeeting", "message": "..." }
}
```

代表的な `error.code`: `NoPreviousMeeting`（followup で過去面談なし）、`NoDocument`（資料未生成）、その他は例外型名。

## follow-up（2回目以降）モード

`meetingStatus: "followup"` で継続提案エージェントが起動する。

### 前提チェック
過去の面談（`meetings`）が 1 件も無い顧客に followup を呼ぶと、**エージェントを起動せず**即座に
`error.code = "NoPreviousMeeting"` を返す。先に初回（first）を実施しておく必要がある。

### 前回実績（outcomes）の記録 — サーバ側で確定
`lastMeetingNotes` に前回面談で起きたこと（反応・合意事項・宿題など）を渡すと、**API がエージェント
実行前に、履歴の直近 round を明示して `record_meeting_outcomes` を呼び**、前回 meeting の `outcomes`
を確定し `status` を `done` に更新する。

- これは **LLM の呼び出し順に依存させない**ための設計（エージェント自身は `record_meeting_outcomes` を呼ばない）。新しい面談レコードに前回メモが誤って書き込まれる事故を防ぐ。
- `lastMeetingNotes` を省略した場合は、既に `meetings` に記録済みの `outcomes` を根拠に使う。
- 今回生成した meeting の `outcomes` は `null` で保存され、次回 followup 呼び出し時に改めて確定される契約。

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

## セキュリティ・運用上の挙動

- **資料URLの再署名**: 面談レコードには SAS を外した素URL + blob 名を保存し、`get_customer_history`
  が履歴を返すたびに SAS を再発行する（保存済みURLが失効して 401 になるのを防ぐ）。
- **HP取得の限定**: `fetch_url_text` はリクエストで指定された顧客HPのホスト宛のみ許可し、取得本文は
  「信頼できない外部データ」として扱う（プロンプトインジェクションでの別ホストへのデータ持ち出しを抑止）。
  `WEB_FETCH_ENABLED=false` で取得ツール自体を無効化できる。
- **認証**: 公開フロントエンド（Streamlit）はアクセスコードで保護（`APP_ACCESS_CODE`、デプロイ設定）。
  バックエンド API は internal ingress（インターネット非公開）。
