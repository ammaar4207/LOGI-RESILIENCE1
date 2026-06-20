import asyncio
from app.db.neo4j import db

async def get():
    await db.connect()
    n, s, t, m = await db.get_dynamic_topology()
    for x in m:
        if x['target'] == 'USLAX':
            print("TO USLAX:", x)
    await db.close()

asyncio.run(get())
