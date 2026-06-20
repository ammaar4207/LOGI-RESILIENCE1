import logging
from typing import Any, Dict, List, Tuple

from neo4j import AsyncGraphDatabase
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class Neo4jDriverWrapper:
    def __init__(self):
        self.uri = settings.NEO4J_URI
        self.user = settings.NEO4J_USER
        self.password = settings.NEO4J_PASSWORD
        self.driver = None

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    async def connect(self):
        if not self.driver:
            self.driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_timeout=30.0,
            )
            async with self.driver.session() as session:
                await session.run("CREATE INDEX port_id_idx IF NOT EXISTS FOR (p:Port) ON (p.id)")
                await session.run("CREATE INDEX port_name_idx IF NOT EXISTS FOR (p:Port) ON (p.name)")
                await session.run("CREATE INDEX lane_id_idx IF NOT EXISTS FOR ()-[r:SHIPPING_LANE]-() ON (r.id)")

    async def close(self):
        if self.driver:
            await self.driver.close()
            self.driver = None

    def get_session(self):
        if not self.driver:
            raise RuntimeError("Neo4j driver not connected. Call connect() first.")
        return self.driver.session()

    async def get_dynamic_topology(
        self,
    ) -> Tuple[List[Dict[str, Any]], List[int], List[int], List[Dict[str, Any]]]:
        """
        Returns geo_nodes, source indices, target indices, and raw edge metadata.
        """
        if not self.driver:
            await self.connect()

        query = """
        MATCH (p:Port)
        WITH collect(p) AS ports
        OPTIONAL MATCH (p1:Port)-[r:SHIPPING_LANE]->(p2:Port)
        RETURN ports,
               collect({
                 id: r.id,
                 source: p1.id,
                 target: p2.id,
                 distance_km: coalesce(r.distance_km, 5000),
                 co2_per_teu: coalesce(r.co2_per_teu, 150),
                 base_risk: coalesce(r.base_risk, 0.5),
                 essential_priority: coalesce(r.essential_priority, 0.5)
               }) AS edges
        """
        async with self.get_session() as session:
            result = await session.run(query)
            record = await result.single()
            if not record or not record["ports"]:
                return [], [], [], []

            ports = record["ports"]
            edges_data = [e for e in record["edges"] if e.get("source") and e.get("target")]

            port_map = {p["id"]: idx for idx, p in enumerate(ports)}
            geo_nodes = [
                {
                    "id": p["id"],
                    "lat": p.get("lat"),
                    "lon": p.get("lon"),
                    "name": p.get("name", p["id"]),
                    "congestion": float(p.get("congestion") or 0.15),
                    "capacity_teu": p.get("capacity_teu"),
                }
                for p in ports
            ]

            sources, targets, edge_meta = [], [], []
            for e in edges_data:
                if e["source"] in port_map and e["target"] in port_map:
                    sources.append(port_map[e["source"]])
                    targets.append(port_map[e["target"]])
                    edge_meta.append(e)

            return geo_nodes, sources, targets, edge_meta

    async def list_ports(self) -> List[Dict[str, Any]]:
        async with self.get_session() as session:
            result = await session.run(
                """
                MATCH (p:Port)
                RETURN p.id AS id, p.name AS name, p.lat AS lat, p.lon AS lon,
                       p.capacity_teu AS capacity_teu, p.congestion AS congestion
                ORDER BY p.name
                """
            )
            return await result.data()


db = Neo4jDriverWrapper()
