import asyncio
import json
import logging
import random
import math
from datetime import datetime, timezone
import redis.asyncio as aioredis
from app.core.config import get_settings
from app.db.seed_data import PORTS, LANES

logger = logging.getLogger("logi-resilience.ais")

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) * math.sin(dlon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_heading(lat1, lon1, lat2, lon2):
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon_rad = math.radians(lon2 - lon1)
    
    x = math.sin(dlon_rad) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - (math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad))
    initial_bearing = math.atan2(x, y)
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360
    return compass_bearing

class AISTelemetrySimulator:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.ships = []
        self.port_map = {p["id"]: p for p in PORTS}
        self.settings = get_settings()
        self._initialize_fleet()
        
    def _initialize_fleet(self):
        mmsi_counter = 200000000
        # Spawn ships on each lane
        for src_id, tgt_id, dist, _, _, _ in LANES:
            if src_id not in self.port_map or tgt_id not in self.port_map:
                continue
            
            src = self.port_map[src_id]
            tgt = self.port_map[tgt_id]
            
            # Spawn 3 to 8 ships per lane for dense traffic
            num_ships = random.randint(3, 8)
            for _ in range(num_ships):
                # Random position along the lane (0.0 to 1.0)
                progress = random.uniform(0.0, 1.0)
                lat = src["lat"] + (tgt["lat"] - src["lat"]) * progress
                lon = src["lon"] + (tgt["lon"] - src["lon"]) * progress
                
                # Speed in knots (typical container ship 15-24 knots) -> km/h
                speed_knots = random.uniform(15.0, 24.0)
                speed_kmh = speed_knots * 1.852
                
                # Heading
                heading = calculate_heading(src["lat"], src["lon"], tgt["lat"], tgt["lon"])
                
                self.ships.append({
                    "mmsi": str(mmsi_counter),
                    "vessel_name": f"LR-{mmsi_counter}",
                    "src": src_id,
                    "tgt": tgt_id,
                    "lat": lat,
                    "lon": lon,
                    "heading": heading,
                    "speed_knots": speed_knots,
                    "speed_kmh": speed_kmh,
                    "progress": progress
                })
                mmsi_counter += 1
                
        logger.info(f"Initialized AIS fleet with {len(self.ships)} simulated vessels.")

    async def _tick_vessels(self, dt_seconds: float):
        for ship in self.ships:
            src = self.port_map[ship["src"]]
            tgt = self.port_map[ship["tgt"]]
            
            # Distance moved in this tick
            dist_moved_km = ship["speed_kmh"] * (dt_seconds / 3600.0)
            total_dist = haversine_distance(src["lat"], src["lon"], tgt["lat"], tgt["lon"])
            
            # Avoid division by zero
            if total_dist == 0:
                continue
                
            progress_delta = dist_moved_km / total_dist
            ship["progress"] += progress_delta
            
            # If reached destination, reset to start or reverse direction
            if ship["progress"] >= 1.0:
                ship["progress"] = 0.0
                # Swap src and tgt to make them bounce back and forth
                ship["src"], ship["tgt"] = ship["tgt"], ship["src"]
                ship["heading"] = calculate_heading(tgt["lat"], tgt["lon"], src["lat"], src["lon"])
            
            # Interpolate new position
            ship["lat"] = src["lat"] + (tgt["lat"] - src["lat"]) * ship["progress"]
            ship["lon"] = src["lon"] + (tgt["lon"] - src["lon"]) * ship["progress"]

    async def start_broadcasting(self):
        logger.info("Starting AIS Telemetry Broadcast Loop...")
        tick_rate = 2.0 # Update every 2 seconds
        
        while True:
            try:
                await self._tick_vessels(tick_rate * 10) # Multiply by 10 to speed up simulation visually
                
                # Create AIS payloads
                timestamp = datetime.now(timezone.utc).isoformat()
                ais_payloads = []
                for s in self.ships:
                    ais_payloads.append({
                        "mmsi": s["mmsi"],
                        "vessel_name": s["vessel_name"],
                        "lat": s["lat"],
                        "lon": s["lon"],
                        "heading": s["heading"],
                        "speed": s["speed_knots"],
                        "timestamp": timestamp,
                        "status": "Under way using engine",
                        "destination": s["tgt"],
                        "cargo_type": "Containers"
                    })
                
                # Broadcast via Redis PubSub
                await self.redis.publish("telemetry:ais", json.dumps(ais_payloads))
                
            except Exception as e:
                logger.error(f"Error in AIS broadcast loop: {e}")
                
            await asyncio.sleep(tick_rate)
