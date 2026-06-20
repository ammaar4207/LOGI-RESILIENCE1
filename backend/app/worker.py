import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import redis.asyncio as aioredis
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.db.graph_seed import seed_graph_if_empty
from app.db.neo4j import db
from app.services.analytics import AnalyticsEngine
from app.services.ais import AISTelemetrySimulator
from app.services.iot_mqtt import IoTTelemetryService
from app.services.gdacs import GDACSScraper
from app.services.pricing import SCFIPricingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AnalyticsWorker")
settings = get_settings()

RAW_TELEMETRY_TOPIC = "logistics.raw_telemetry"


class TelemetryPublisher:
    def __init__(self):
        self.redis_client = None
        self.kafka_producer = None
        self.kafka_consumer = None
        self.engine: AnalyticsEngine | None = None
        self.risk_history: list = []
        self.running = True

    async def initialize(self):
        await db.connect()
        await seed_graph_if_empty()
        self.redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self.engine = AnalyticsEngine(redis_client=self.redis_client)

        if settings.KAFKA_ENABLED:
            try:
                from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

                self.kafka_producer = AIOKafkaProducer(
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
                )
                await self.kafka_producer.start()
                logger.info("Kafka producer connected.")

                self.kafka_consumer = AIOKafkaConsumer(
                    settings.KAFKA_TELEMETRY_TOPIC,
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    group_id="logi-resilience-workers",
                    auto_offset_reset="latest"
                )
                await self.kafka_consumer.start()
                logger.info("Kafka consumer connected to %s.", settings.KAFKA_TELEMETRY_TOPIC)
            except Exception as exc:
                logger.warning("Kafka disabled after initialization failure: %s", exc)
                self.kafka_producer = None
                self.kafka_consumer = None

    @retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5))
    async def publish_cycle(self):
        assert self.engine is not None
        payload = await self.engine.run_and_publish_telemetry()
        avg_risk = payload.get("global_risk", 0.5)

        if self.kafka_producer:
            body = json.dumps(payload)
            await self.kafka_producer.send_and_wait(
                settings.KAFKA_TELEMETRY_TOPIC,
                body.encode("utf-8"),
            )

        logger.info(
            "Published telemetry | lanes=%s global_risk=%.3f resilience=%s",
            len(payload.get("metrics", [])),
            avg_risk,
            payload.get("global_resilience_index"),
        )

    async def _kafka_scraper_producer_loop(self):
        """Periodically scrape environmental data and post it to Kafka as raw telemetry."""
        assert self.engine is not None
        logger.info("Kafka Scraper Loop started.")
        while self.running:
            try:
                # Trigger a scrape of the nodes
                geo_nodes, _, _, _ = await db.get_dynamic_topology()
                if geo_nodes:
                    strains = await self.engine.scraper.fetch_environmental_state(geo_nodes)
                    raw_payload = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "strains": strains
                    }
                    if self.kafka_producer:
                        await self.kafka_producer.send_and_wait(
                            RAW_TELEMETRY_TOPIC,
                            json.dumps(raw_payload).encode("utf-8")
                        )
                        logger.debug("Scraped and published raw telemetry to Kafka.")
            except Exception as e:
                logger.error("Scraper loop failed: %s", e)
            await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)

    async def run_forever(self):
        await self.initialize()
        
        self.ais_simulator = AISTelemetrySimulator(self.redis_client)
        asyncio.create_task(self.ais_simulator.start_broadcasting())
        
        self.iot_service = IoTTelemetryService(self.redis_client)
        asyncio.create_task(self.iot_service.listen_for_telemetry())
        asyncio.create_task(self.iot_service._simulate_iot_telemetry())
        
        self.gdacs_scraper = GDACSScraper(self.redis_client)
        asyncio.create_task(self.gdacs_scraper.run_loop())
        
        self.pricing_service = SCFIPricingService(self.redis_client)
        asyncio.create_task(self.pricing_service.run_loop())

        from app.services.dcsa import DCSATrackingSimulator
        self.dcsa_simulator = DCSATrackingSimulator(self.redis_client)
        asyncio.create_task(self.dcsa_simulator.run_loop())
        
        if settings.KAFKA_ENABLED and self.kafka_consumer:
            logger.info("Worker online (Kafka Stream Mode) — listening to %s", settings.KAFKA_TELEMETRY_TOPIC)
            # Start background scraping loop to feed Kafka
            asyncio.create_task(self._kafka_scraper_producer_loop())
            
            # Consume loop
            try:
                async for msg in self.kafka_consumer:
                    try:
                        raw_data = msg.value.decode("utf-8")
                        data = json.loads(raw_data)
                        strains = data.get("enriched_strains") or data.get("strains")
                        if strains and self.redis_client:
                            await self.redis_client.setex(
                                "ingestion:environmental_v1",
                                settings.REDIS_CACHE_TTL_SECONDS,
                                json.dumps(strains)
                            )
                            logger.info("Cached Flink-enriched telemetry in Redis.")
                        await self.publish_cycle()
                    except Exception as exc:
                        logger.exception("Failed to process consumed Kafka message: %s", exc)
            finally:
                await self.kafka_consumer.stop()
                if self.kafka_producer:
                    await self.kafka_producer.stop()
        else:
            logger.info("Worker online (Polling Mode) — interval %.1fs", settings.WORKER_POLL_INTERVAL_SECONDS)
            while True:
                try:
                    await self.publish_cycle()
                    await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)
                except Exception as exc:
                    logger.exception("Worker cycle failed: %s", exc)
                    await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(TelemetryPublisher().run_forever())
