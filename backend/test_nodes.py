import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.neo4j import db

async def main():
    await db.connect()
    nodes, _, _, _ = await db.get_dynamic_topology()
    print("NODES:")
    print([n['id'] for n in nodes if 'id' in n])
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
