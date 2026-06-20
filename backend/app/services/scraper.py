import asyncio
import json
import logging
import random
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

DISRUPTION_KEYWORDS = re.compile(
    r"\b(strike|blockade|tsunami|typhoon|hurricane|piracy|sanction|closure|congestion|delay|embargo)\b",
    re.IGNORECASE,
)

USER_AGENTS = [
    "Logi-Resilience/4.0 (+https://github.com/logi-resilience; enterprise-ingestion)",
]


class LogisticsDataScraper:
    """Multi-source ingestion: maritime RSS, optional OpenWeather, keyword NLP."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._memory_cache: Dict = {}
        self._last_scrape = 0.0
        self._cache_ttl = settings.REDIS_CACHE_TTL_SECONDS
        self.maritime_rss_url = "https://gcaptain.com/feed/"
        self.weather_base = settings.OPENWEATHER_BASE_URL

    async def fetch_environmental_state(self, nodes: List[Dict]) -> Dict[str, Dict[str, float]]:
        loop = asyncio.get_event_loop()
        now = loop.time()
        if self._memory_cache and (now - self._last_scrape) < self._cache_ttl:
            return self._memory_cache

        cache_key = "ingestion:environmental_v1"
        if self.redis:
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as exc:
                logger.warning("Redis cache read failed: %s", exc)

        rss_pressure = await self._fetch_maritime_rss_pressure()
        state_map: Dict[str, Dict[str, float]] = {}

        # Fetch active disruptions from Redis
        disruptions = []
        if self.redis:
            try:
                disruptions_raw = await self.redis.get("simulation:disruptions")
                if disruptions_raw:
                    disruptions = json.loads(disruptions_raw)
            except Exception as exc:
                logger.warning("Failed to fetch disruptions from Redis: %s", exc)

        async with httpx.AsyncClient(timeout=12.0) as client:
            for node in nodes:
                n_id = str(node["id"]).strip().lower()
                lat = float(node.get("lat") or 0)
                lon = float(node.get("lon") or 0)

                weather = await self._weather_strain(client, lat, lon)
                sar_anomaly = self._fetch_sar_anomalies(lat, lon)
                congestion = min(1.0, float(node.get("congestion", 0.15)) + rss_pressure * 0.2 + sar_anomaly * 0.3)
                news = min(1.0, rss_pressure + random.uniform(0.05, 0.15))

                # Apply active disruptions
                for d in disruptions:
                    dtype = d.get("type")
                    target = d.get("target", "").strip().lower()
                    severity = float(d.get("severity", 0.8))

                    # Direct node-based target matching
                    if target == n_id or target == str(node.get("name", "")).strip().lower():
                        if dtype == "strike":
                            congestion = max(congestion, severity)
                            news = max(news, severity)
                        elif dtype == "hurricane":
                            weather = max(weather, severity)
                            congestion = max(congestion, severity * 0.8)
                            news = max(news, severity * 0.7)
                        elif dtype == "custom":
                            weather = max(weather, float(d.get("weather", 0.0)))
                            congestion = max(congestion, float(d.get("congestion", 0.0)))
                            news = max(news, float(d.get("news", 0.0)))

                    # Coordinate-based hurricane radius matching
                    elif dtype == "hurricane" and "lat" in d and "lon" in d:
                        try:
                            d_lat = float(d["lat"])
                            d_lon = float(d["lon"])
                            radius = float(d.get("radius_km", 1000))
                            import math
                            dist = math.sqrt((lat - d_lat)**2 + (lon - d_lon)**2) * 111.0
                            if dist <= radius:
                                factor = 1.0 - (dist / radius)
                                weather = max(weather, severity * factor)
                                congestion = max(congestion, severity * 0.8 * factor)
                                news = max(news, severity * 0.7 * factor)
                        except Exception as e:
                            logger.warning("Error calculating hurricane distance: %s", e)

                state_map[n_id] = {
                    "weather": round(weather, 3),
                    "congestion": round(congestion, 3),
                    "news": round(news, 3),
                    "sar_anomaly": round(sar_anomaly, 3),
                }

        self._memory_cache = state_map
        self._last_scrape = now

        if self.redis:
            try:
                await self.redis.setex(cache_key, self._cache_ttl, json.dumps(state_map))
            except Exception as exc:
                logger.warning("Redis cache write failed: %s", exc)

        return state_map

    def _fetch_sar_anomalies(self, lat: float, lon: float) -> float:
        """
        Simulates Synthetic Aperture Radar (SAR) Sentinel-1 data fusion.
        Detects 'dark ships' or radar-measured traffic density near the node.
        Returns anomaly value between 0.0 and 1.0.
        """
        # Create a coordinate-based mock anomaly
        try:
            val = (abs(lat) * 7 + abs(lon) * 13) % 1.0
            # If standard random threshold is met, spike it
            if val > 0.95:
                return float(0.6 + (val % 0.4))
            return float(0.05 + (val % 0.2))
        except Exception:
            return 0.1

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    async def _fetch_maritime_rss_pressure(self) -> float:
        """0–1 global disruption pressure from maritime news RSS."""
        headers = {"User-Agent": USER_AGENTS[0]}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self.maritime_rss_url, headers=headers)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            items = root.findall(".//item") or root.findall(".//{*}item")
            if not items:
                return 0.2

            hits = 0
            for item in items[:25]:
                title_el = item.find("title") or item.find("{*}title")
                desc_el = item.find("description") or item.find("{*}description")
                blob = ""
                if title_el is not None and title_el.text:
                    blob += title_el.text
                if desc_el is not None and desc_el.text:
                    blob += " " + desc_el.text
                if DISRUPTION_KEYWORDS.search(blob):
                    hits += 1

            return min(1.0, 0.15 + (hits / max(len(items), 1)) * 0.85)

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    async def _weather_strain(self, client: httpx.AsyncClient, lat: float, lon: float) -> float:
        if not settings.WEATHER_API_KEY or settings.WEATHER_API_KEY == "mock":
            return random.uniform(0.1, 0.45)

        try:
            resp = await client.get(
                self.weather_base,
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": settings.WEATHER_API_KEY,
                    "units": "metric",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            wind = float(data.get("wind", {}).get("speed", 0))
            weather_main = (data.get("weather") or [{}])[0].get("main", "").lower()
            base = min(1.0, wind / 25.0)
            if weather_main in ("thunderstorm", "snow", "squall"):
                base = min(1.0, base + 0.4)
            elif weather_main in ("rain", "drizzle"):
                base = min(1.0, base + 0.2)
            return base
        except Exception as exc:
            logger.debug("Weather API fallback for (%.2f, %.2f): %s", lat, lon, exc)
            return random.uniform(0.1, 0.4)
