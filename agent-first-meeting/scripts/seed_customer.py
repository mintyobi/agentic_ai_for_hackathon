"""ダミー顧客と過去面談を投入する（D4 動作確認用）.

「既存顧客」シナリオで get_customer_history が履歴を返せるよう、
1 件の customer + 過去 1 件の meeting を seed する。
"""
import sys

from azure.cosmos import CosmosClient

from agent_first_meeting.config import settings

sys.stdout.reconfigure(encoding="utf-8")


CUSTOMER = {
    "id": "cus_existing01",
    "companyId": "cus_existing01",
    "companyName": "株式会社既存お得意様",
    "industry": "製造業",
    "scale": "中小企業",
    "knownChallenges": ["人材不足", "原材料費高騰", "技能継承"],
    "tags": ["既存", "東京"],
    "createdAt": "2025-10-01T09:00:00Z",
    "updatedAt": "2026-01-15T18:00:00Z",
}

PRIOR_MEETING = {
    "id": "mtg_prior01",
    "companyId": "cus_existing01",
    "round": 1,
    "scheduledAt": "2026-01-15T10:00:00Z",
    "status": "done",
    "preMeetingDocumentUrl": None,
    "proposedTitle": "DX 推進の方向性ご提案",
    "outcomes": (
        "経営層は DX に前向きだが具体策がなく動けていない。"
        "技能継承を最重要課題と認識。RAG 系の事例があれば次回までに準備してほしいとの依頼。"
    ),
    "nextActions": [
        "RAG 事例の整理",
        "技能継承の現状ヒアリング",
        "経営層・現場双方の温度感確認",
    ],
    "createdAt": "2026-01-15T11:30:00Z",
}


def main() -> None:
    cosmos = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
    db = cosmos.get_database_client(settings.cosmos_database)
    db.get_container_client("customers").upsert_item(CUSTOMER)
    db.get_container_client("meetings").upsert_item(PRIOR_MEETING)
    print(f"[seeded] customer={CUSTOMER['companyName']} ({CUSTOMER['companyId']})")
    print(f"[seeded] prior_meeting={PRIOR_MEETING['id']} round={PRIOR_MEETING['round']}")


if __name__ == "__main__":
    main()
