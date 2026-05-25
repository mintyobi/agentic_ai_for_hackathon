"""documents / chunks の件数を確認する簡易ツール（アプリと同じ sales-agent DB）."""
import sys

from azure.cosmos import CosmosClient

from agent_first_meeting.config import settings

sys.stdout.reconfigure(encoding="utf-8")

db = CosmosClient(
    settings.cosmos_endpoint, credential=settings.cosmos_key
).get_database_client(settings.cosmos_database)

for name in ["documents", "chunks"]:
    container = db.get_container_client(name)
    result = list(
        container.query_items(
            query="SELECT VALUE COUNT(1) FROM c",
            enable_cross_partition_query=True,
        )
    )
    print(f"{name}: {result[0]} 件")
