import logging

from app.db.neo4j import db
from app.db.seed_data import LANES, PORTS

logger = logging.getLogger(__name__)


async def seed_graph_if_empty() -> bool:
    """Load canonical port/lane topology when the database has no ports."""
    await db.connect()
    async with db.get_session() as session:
        result = await session.run("MATCH (p:Port) RETURN count(p) AS c")
        record = await result.single()
        if record and record["c"] > 0:
            logger.info("Graph already seeded (%s ports). Skipping.", record["c"])
            return False

        logger.info("Seeding Neo4j with %s ports and %s lanes...", len(PORTS), len(LANES))
        for port in PORTS:
            await session.run(
                """
                MERGE (p:Port {id: $id})
                SET p.name = $name, p.lat = $lat, p.lon = $lon,
                    p.capacity_teu = $capacity_teu, p.congestion = 0.15
                """,
                port,
            )

        for src, dst, dist, co2, risk, priority in LANES:
            lane_id = f"lane_{src}_{dst}".lower()
            await session.run(
                """
                MATCH (a:Port {id: $src}), (b:Port {id: $dst})
                MERGE (a)-[r:SHIPPING_LANE {id: $lane_id}]->(b)
                SET r.distance_km = $dist, r.co2_per_teu = $co2,
                    r.base_risk = $risk, r.essential_priority = $priority
                """,
                {
                    "src": src,
                    "dst": dst,
                    "lane_id": lane_id,
                    "dist": dist,
                    "co2": co2,
                    "risk": risk,
                    "priority": priority,
                },
            )

        logger.info("Graph seed complete.")
        return True
