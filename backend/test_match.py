import asyncio
from app.services.analytics import AnalyticsEngine
from app.db.neo4j import db
import json
import logging

logging.basicConfig(level=logging.ERROR)

async def run():
    engine = AnalyticsEngine()
    disruptions = [{"id": "test", "target": "CNSHA-USLAX", "severity": 0.8}, {"id": "test2", "target": "AEJEA-EGSUZ", "severity": 0.8}]
    geo_nodes, sources, targets, edge_meta = await db.get_dynamic_topology()
    strains = {}
    metrics = engine._compile_lane_metrics(geo_nodes, sources, targets, edge_meta, None, strains, disruptions)
    for m in metrics:
        if m["source_id"] == "CNSHA" and m["target_id"] == "USLAX":
            print(f"MATCHED CNSHA->USLAX: id={m['id']}, risk_score={m['risk_score']}, status={m['status']}")
        if m["source_id"] == "AEJEA" and m["target_id"] == "EGSUZ":
            print(f"MATCHED AEJEA->EGSUZ: id={m['id']}, risk_score={m['risk_score']}, status={m['status']}")

asyncio.run(run())
