from azure.cosmos import CosmosClient
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent.parent / ".env")

cosmos = CosmosClient(
    url=os.getenv("COSMOS_ENDPOINT"),
    credential=os.getenv("COSMOS_KEY")
)
db = cosmos.get_database_client("sales-knowledge-db")

for name in ["documents", "chunks"]:
    container = db.get_container_client(name)
    result = list(container.query_items(
        query="SELECT VALUE COUNT(1) FROM c",
        enable_cross_partition_query=True
    ))
    print(f"{name}: {result[0]} 件")