import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.neo4j import db
from app.db.graph_seed import seed_graph_if_empty

async def main():
    await db.connect()
    async with db.get_session() as session:
        print("Clearing Neo4j database...")
        await session.run("MATCH (n) DETACH DELETE n")
        print("Database cleared.")
    
    print("Re-seeding database...")
    await seed_graph_if_empty()
    print("Seeding complete.")
    
    nodes, _, _, _ = await db.get_dynamic_topology()
    print(f"Total nodes now: {len(nodes)}")
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
