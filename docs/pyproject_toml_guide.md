# pyproject.toml ガイド

各エージェントの `pyproject.toml` に何を記載するかをまとめたドキュメントです。

---

## そもそも pyproject.toml とは？

`pyproject.toml` は「プロジェクトの履歴書」です。
このプロジェクトが何者で、何を必要としていて、どんなルールで動くかを一か所にまとめたファイルです。

---

## 各セクションの役割

| セクション | 役割 |
|---|---|
| `[project]` | プロジェクトの基本情報（名前・バージョン・対応Pythonバージョン） |
| `dependencies` | 本番環境で必要なライブラリ一覧 |
| `[project.optional-dependencies]` | 開発時のみ必要なライブラリ（テスト・Linterなど） |
| `[tool.setuptools...]` | `src/` 配下をPythonパッケージとして認識させる設定 |
| `[tool.ruff]` | コードフォーマット・Lintのルール |
| `[tool.pytest...]` | テストの対象ディレクトリや動作設定 |

---

## テンプレート

### （仮）`agent-first-meeting/pyproject.toml`

```toml
[project]
name = "agent-first-meeting"
version = "0.1.0"
description = "初回面談向け：類似事例検索・アポ資料生成エージェント"
requires-python = ">=3.11"

dependencies = [
    "fastapi",           # WebAPI フレームワーク
    "uvicorn",           # FastAPI を動かすサーバー
    "anthropic",         # Claude API
    "langchain",         # エージェント構築
    "sqlalchemy",        # DB操作
    "psycopg2-binary",   # PostgreSQL 接続
    "pydantic-settings", # 環境変数の管理
    "alembic",           # DB マイグレーション
]

[project.optional-dependencies]
dev = [
    "pytest",            # テストフレームワーク
    "pytest-asyncio",    # 非同期テスト対応
    "httpx",             # FastAPI テスト用クライアント
    "ruff",              # コードフォーマッター・Linter
]

[tool.setuptools.packages.find]
where = ["src"]          # src/ 配下をパッケージとして認識させる

[tool.ruff]
line-length = 88         # 1行の最大文字数
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I"] # エラー・未使用変数・import順序をチェック

[tool.pytest.ini_options]
testpaths = ["tests"]    # テストの対象ディレクトリ
asyncio_mode = "auto"    # 非同期テストを自動認識
```

### （仮）`agent-follow-up/pyproject.toml`

```toml
[project]
name = "agent-follow-up"
version = "0.1.0"
description = "フォローアップ向け：顧客情報参照・提案資料生成エージェント"
requires-python = ">=3.11"

dependencies = [
    "fastapi",
    "uvicorn",
    "anthropic",
    "langchain",
    "sqlalchemy",
    "psycopg2-binary",
    "pydantic-settings",
    "alembic",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "httpx",
    "ruff",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

## インストールコマンド

```bash
# 開発時（推奨）：開発用ライブラリも含めてインストール
pip install -e ".[dev]"

# 本番時：本番用ライブラリのみインストール
pip install -e .
```

> **`-e`（編集可能モード）について**：`src/` のコードを変更したとき、再インストール不要で即反映されます。開発時は必ず `-e` をつけてください。

---

## ライブラリのカスタマイズについて

エージェントによって必要なライブラリが異なる場合は、`dependencies` を個別に調整してください。

追加が想定されるライブラリの例：

| ライブラリ | 用途 |
|---|---|
| `chromadb` | ベクトル検索（類似事例の検索精度向上） |
| `tiktoken` | トークン数のカウント |
| `python-docx` | Word形式での資料出力 |
| `boto3` | AWS S3への資料アップロード |