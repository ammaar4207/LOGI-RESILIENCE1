import httpx
import logging

logger = logging.getLogger(__name__)

async def fetch_live_weather(lat: float, lon: float) -> dict:
    """
    Fetch live weather data from Open-Meteo API.
    Returns a dictionary with wind_speed_10m (km/h), precipitation (mm), and weather_code.
    """
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,precipitation,weather_code,wind_speed_10m&wind_speed_unit=kmh"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            current = data.get("current", {})
            return {
                "wind_speed_kmh": current.get("wind_speed_10m", 0.0),
                "precipitation_mm": current.get("precipitation", 0.0),
                "weather_code": current.get("weather_code", 0),
                "temperature_c": current.get("temperature_2m", 0.0)
            }
    except Exception as e:
        logger.error(f"Failed to fetch live weather for ({lat}, {lon}): {e}")
        return {
            "wind_speed_kmh": 0.0,
            "precipitation_mm": 0.0,
            "weather_code": 0,
            "temperature_c": 0.0
        }
