import asyncio
import json
import logging
import random
from datetime import datetime, timezone
import redis.asyncio as aioredis
from app.db.seed_data import PORTS
from app.db.postgres import async_session_maker
from app.services.event_log import log_event

logger = logging.getLogger("logi-resilience.dcsa")

class DCSATrackingSimulator:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def run_loop(self):
        logger.info("Starting DCSA Container Tracking simulator...")
        events = ["GATE_IN", "CONTAINER_LOADED", "CONTAINER_DISCHARGED", "GATE_OUT"]
        while True:
            try:
                # Randomly fire off a DCSA standard tracking event
                if random.random() > 0.3:
                    port = random.choice(PORTS)["id"]
                    event = random.choice(events)
                    container_id = f"MSCU{random.randint(1000000, 9999999)}"
                    
                    alert_payload = {
                        "type": "dcsa_event",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "level": "INFO",
                        "source": "DCSA Open API",
                        "message": f"Container {container_id} recorded event {event} at {port}."
                    }
                    await self.redis.publish("telemetry:iot", json.dumps(alert_payload))
                    
                    async with async_session_maker() as db_session:
                        await log_event(
                            db=db_session,
                            event_type="alert_fired",
                            target=port,
                            severity=0.1,
                            details={"type": "dcsa_event", "message": alert_payload["message"]},
                            global_resilience=None
                        )
            except Exception as e:
                logger.error(f"DCSA Tracking Simulator failed: {e}")
            
            # Fire an event every 45 seconds on average
            await asyncio.sleep(45)
