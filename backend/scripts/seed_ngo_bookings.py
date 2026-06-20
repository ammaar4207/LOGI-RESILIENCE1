import asyncio
import json
import redis.asyncio as aioredis
from app.core.config import get_settings

settings = get_settings()

NGO_BOOKINGS = [
    {
        "booking_ref": "WFP-FOOD-001",
        "lane_id": "lane_egsuz_esvlc",
        "alternative_lanes": ["lane_egsuz_zadur", "lane_zadur_esvlc"],
        "email_content": "URGENT - HUMANITARIAN AID: WFP Food Rations re-routed to avoid Suez blockade. Pre-positioned distribution hubs at destination have been notified.",
        "is_essential": True
    },
    {
        "booking_ref": "RC-MED-993",
        "lane_id": "lane_cnsha_uslax",
        "alternative_lanes": ["lane_cnsha_jptyo", "lane_jptyo_uslax"],
        "email_content": "URGENT - HUMANITARIAN AID: Red Cross Medical Supplies re-routed via Tokyo to avoid severe storm front.",
        "is_essential": True
    },
    {
        "booking_ref": "UNICEF-SHL-412",
        "lane_id": "lane_twkhh_cnhkg",
        "alternative_lanes": ["lane_twkhh_phmni", "lane_phmni_cnhkg"],
        "email_content": "URGENT - HUMANITARIAN AID: UNICEF Shelter Kits diverted through Manila. ETA extended by 2 days.",
        "is_essential": True
    }
]

async def seed_ngo_bookings():
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        # Fetch existing bookings
        existing = await redis_client.get("simulations:bookings")
        bookings = json.loads(existing) if existing else []
        
        # Append NGO bookings
        bookings.extend(NGO_BOOKINGS)
        
        # Save back to redis
        await redis_client.set("simulations:bookings", json.dumps(bookings))
        print(f"Successfully seeded {len(NGO_BOOKINGS)} NGO bookings into Redis!")
    except Exception as e:
        print(f"Error seeding NGO bookings: {e}")
    finally:
        await redis_client.close()

if __name__ == "__main__":
    asyncio.run(seed_ngo_bookings())
