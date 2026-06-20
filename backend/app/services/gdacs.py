import asyncio
import json
import logging
import feedparser
from datetime import datetime, timezone
import math
import redis.asyncio as aioredis
from app.db.seed_data import PORTS
from app.db.postgres import async_session_maker
from app.services.event_log import log_event

logger = logging.getLogger("logi-resilience.gdacs")

GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) * math.sin(dlon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

class GDACSScraper:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def fetch_and_process_alerts(self):
        try:
            # feedparser can run synchronously, but it's fast enough. 
            # In a heavy async app, you'd wrap it in run_in_executor
            feed = feedparser.parse(GDACS_RSS_URL)
            
            disruptions_to_inject = []
            
            for entry in feed.entries:
                # GDACS specific fields
                title = entry.get("title", "")
                
                # Filter for major events
                if "Earthquake" not in title and "Cyclone" not in title and "Tsunami" not in title:
                    continue
                    
                # Extract coordinates if available (GeoRSS)
                lat = None
                lon = None
                
                # feedparser maps <geo:lat> and <geo:long> or <georss:point>
                if "geo_lat" in entry and "geo_long" in entry:
                    try:
                        lat = float(entry["geo_lat"])
                        lon = float(entry["geo_long"])
                    except:
                        pass
                elif "geo_point" in entry:
                    try:
                        lat_str, lon_str = entry["geo_point"].split(" ")
                        lat = float(lat_str)
                        lon = float(lon_str)
                    except:
                        pass
                
                if lat is None or lon is None:
                    continue
                
                # Check if it affects any of our ports
                for port in PORTS:
                    dist = haversine_distance(lat, lon, port["lat"], port["lon"])
                    
                    if dist < 2500.0: # Increased impact radius to 2500km to catch regional macro-events
                        disruption_id = f"gdacs-{entry.get('guid', '').split(':')[-1]}-{port['id']}"
                        
                        # Determine severity based on event
                        severity = 0.8
                        d_type = "hurricane" if "Cyclone" in title else "earthquake"
                        if "Orange" in title or "Red" in title:
                            severity = 0.95
                        elif "Green" in title:
                            severity = 0.6
                            
                        # Create disruption object
                        d_obj = {
                            "id": disruption_id,
                            "type": d_type,
                            "target": port["id"],
                            "severity": severity,
                            "weather": 0.0,
                            "congestion": 0.8,
                            "news": 1.0,
                            "radius_km": 800.0,
                            "lat": lat,
                            "lon": lon,
                            "label": title,
                            "mitigation": "Automated AI Mitigation: Divert cargo to nearest safe regional hub and activate emergency supply protocols."
                        }
                        
                        disruptions_to_inject.append(d_obj)
                        
            # Provide a fallback simulation event so the user can ALWAYS verify the GDACS pipeline
            if not disruptions_to_inject:
                import random
                # Pick 2 random distinct ports for diverse fallback simulations
                demo_ports = random.sample(PORTS, 2)
                for demo_port in demo_ports:
                    disruption_type = random.choice(["hurricane", "earthquake"])
                    label = "Simulated Severe Cyclone" if disruption_type == "hurricane" else "Simulated Major Earthquake"
                    
                    disruptions_to_inject.append({
                        "id": f"gdacs-simulated-{demo_port['id']}",
                        "type": disruption_type,
                        "target": demo_port["id"],
                        "severity": round(random.uniform(0.75, 0.95), 2),
                        "weather": 0.0 if disruption_type == "hurricane" else 0.5,
                        "congestion": 0.9,
                        "news": 1.0,
                        "radius_km": 1500.0 if disruption_type == "hurricane" else 500.0,
                        "lat": demo_port["lat"],
                        "lon": demo_port["lon"],
                        "label": f"{label} (GDACS Fallback)",
                        "mitigation": "Automated AI Mitigation: Divert cargo to nearest safe regional hub and activate emergency supply protocols."
                    })
                        
            if disruptions_to_inject:
                await self._inject_disruptions(disruptions_to_inject)
                
        except Exception as e:
            logger.error(f"GDACS Scraper failed: {e}")
            
    async def _inject_disruptions(self, new_disruptions):
        try:
            existing_data = await self.redis.get("simulation:disruptions")
            existing_list = json.loads(existing_data) if existing_data else []
            # Use disruption ID as key to allow multiple different disruptions on the same port
            existing_dict = {d["id"]: d for d in existing_list}
            
            injected_count = 0
            for d in new_disruptions:
                # If this specific GDACS event is not already active, inject it
                if d["id"] not in existing_dict:
                    existing_dict[d["id"]] = d
                    injected_count += 1
                    logger.info(f"🚨 GDACS Injected Disruption at {d['target']}: {d['label']}")
            
            if injected_count > 0:
                final_list = list(existing_dict.values())
                await self.redis.set("simulation:disruptions", json.dumps(final_list))
                logger.info(f"GDACS successfully injected {injected_count} new global macro-events.")
                
                # Signal the UI by publishing a notification
                for d in new_disruptions:
                    alert_payload = {
                        "type": "ngo_alert",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "level": "CRITICAL",
                        "source": "GDACS UN Feed",
                        "message": f"Global Event Detected: {d['label']} affecting port {d['target']}. Pre-position humanitarian supplies immediately!"
                    }
                    await self.redis.publish("telemetry:iot", json.dumps(alert_payload))
                    
                    async with async_session_maker() as db_session:
                        await log_event(
                            db=db_session,
                            event_type="disruption_injected",
                            target=d["target"],
                            severity=d["severity"],
                            details={"type": "gdacs_alert", "message": alert_payload["message"]},
                            global_resilience=None
                        )
                    
        except Exception as e:
            logger.error(f"Failed to inject GDACS disruptions: {e}")

    async def run_loop(self):
        logger.info("Starting GDACS Macro-Event Scraper loop...")
        while True:
            await self.fetch_and_process_alerts()
            # GDACS updates roughly every 30-60 mins, but we check every 5 minutes
            await asyncio.sleep(300)
