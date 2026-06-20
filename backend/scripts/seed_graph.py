#!/usr/bin/env python3
"""CLI: seed Neo4j with global port/lane topology."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.graph_seed import seed_graph_if_empty
from app.db.neo4j import db


async def main():
    await db.connect()
    seeded = await seed_graph_if_empty()
    await db.close()
    print("Seeded new graph." if seeded else "Graph already populated.")


if __name__ == "__main__":
    asyncio.run(main())
