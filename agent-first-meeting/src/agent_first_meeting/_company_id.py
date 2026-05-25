"""会社名から決定的に companyId を導出する共有ユーティリティ.

ここを 1 箇所にまとめることで、`MeetingRecordPlugin` と seed スクリプトが
同じ計算式を使えることを保証する。
"""
import hashlib


def deterministic_company_id(company_name: str) -> str:
    """会社名 → 決定的 companyId（`cus_` + SHA1 先頭12文字）.

    並行作成のレースを避けるため、同じ会社名は必ず同じ ID になるように決定的に算出。
    SHA1 を使うのは「短くて衝突確率が事実上ゼロ」だから。暗号学的強度は要求していない。
    """
    normalized = company_name.strip()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"cus_{digest}"
