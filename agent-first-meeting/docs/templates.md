# 自社フォーマット（PPTX テンプレート）の運用

生成される 6 スライド提案資料の**マスター・レイアウト・配色・フォント・ロゴ**を、
自社ブランドに合わせて差し替える方法。

## 仕組み（30秒）

1. `agent-first-meeting/templates/<id>.pptx` を置く。
2. `.env` で `DEFAULT_TEMPLATE_ID=<id>` を指定（例: `default`）。
3. API 起動時にテンプレを読み込み、各スライドはレイアウトを「**名前→インデックス**」の順で
   解決して値を流し込む（テンプレ無しなら python-pptx 既定の見た目）。

レイアウト解決のルール（`_pptx_builder._LAYOUT_RESOLUTION`）:

| スライド | 1st 候補（名前） | 2nd 候補（fallback） | 最終 fallback（idx） |
|---|---|---|---|
| 表紙 | `Cover` | `Title Slide` | 0 |
| 目次 | `Agenda` | `Title and Content` | 1 |
| 業界 | `Industry` | `Title and Content` | 1 |
| 役職 | `Position` | `Title and Content` | 1 |
| 商品 | `Product` | `Title and Content` | 1 |
| 費用 | `Cost` | `Title and Content` | 1 |

> いずれのレイアウトも `placeholder[0]=タイトル`、`placeholder[1]=本文/サブタイトル` を
> 期待します。PowerPoint で複製・改名する際はこの構造を壊さないでください。

## 自社テンプレを作る手順

1. **同梱の `templates/default.pptx` を PowerPoint で開く**（プレースホルダ規約のひな型）。
2. 「表示」→「スライドマスター」で**配色・フォント・ロゴ・余白**を編集。
3. 必要なら本文用レイアウトを複製して `Agenda` / `Industry` / `Position` / `Product` /
   `Cost` に改名（個別デザインしたい場合）。改名しない場合は全て同じ `Title and Content`
   を共有します（最小構成）。
4. 名前を付けて `templates/<id>.pptx` に保存（例: `templates/ourcorp.pptx`）。
5. `.env`（または Container Apps の env）に `DEFAULT_TEMPLATE_ID=ourcorp` を設定して再起動。

## 同梱テンプレを再生成する

`templates/default.pptx` は `scripts/build_default_template.py` で生成しています。
変更後の再生成:

```bash
python scripts/build_default_template.py
# → templates/default.pptx が再生成され、layout[0] が "Cover" に改名される
```

## 確認方法

- `python -c "from pptx import Presentation; p=Presentation('templates/default.pptx'); print([l.name for l in p.slide_layouts])"`
  で各レイアウト名を一覧表示。
- ユニットテスト: `pytest tests/test_pptx_builder.py` （テンプレ経路を含む9件）。

## デプロイ

API イメージのビルド時に `Dockerfile` が `COPY templates ./templates` でテンプレを
含めます。新しいテンプレを追加・更新した場合は API イメージを再ビルド・push し、
Container App を `--image` 更新するだけで反映されます（フロントは無関係）。
