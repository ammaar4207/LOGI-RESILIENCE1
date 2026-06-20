import asyncio
import logging
import random
import json
from datetime import datetime, timezone
import redis.asyncio as aioredis
from app.db.seed_data import LANES

logger = logging.getLogger("logi-resilience.pricing")

class SCFIPricingService:
    """
    Mocks the Shanghai Containerized Freight Index (SCFI).
    Generates realistic, fluctuating spot rates for the shipping lanes.
    """
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.base_rates = {}
        self._initialize_base_rates()

    def _initialize_base_rates(self):
        # Generate a base rate for each lane based on distance (roughly $0.10 to $0.20 per km)
        for src, tgt, distance, _, _, _ in LANES:
            lane_id = f"{src}-{tgt}"
            base_rate = max(500, int(distance * random.uniform(0.05, 0.09)))
            self.base_rates[lane_id] = base_rate

    async def update_prices(self):
        try:
            current_rates = {}
            for lane_id, base_rate in self.base_rates.items():
                # Random walk: max 5% daily swing
                swing = random.uniform(-0.05, 0.05)
                new_rate = int(base_rate * (1 + swing))
                
                # Update base rate for next iteration (creates trend)
                self.base_rates[lane_id] = new_rate
                
                current_rates[lane_id] = new_rate
                
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "index_name": "SCFI_MOCK",
                "rates": current_rates
            }
            
            # Store the latest rates in Redis
            await self.redis.set("pricing:scfi_latest", json.dumps(payload))
            logger.debug("Updated SCFI mock pricing indices.")
            
        except Exception as e:
            logger.error(f"Failed to update SCFI pricing: {e}")

    async def run_loop(self):
        logger.info("Starting SCFI Freight Pricing loop...")
        while True:
            await self.update_prices()
            # Update rates every hour (mocking daily SCFI updates, but faster for demo)
            await asyncio.sleep(3600)
