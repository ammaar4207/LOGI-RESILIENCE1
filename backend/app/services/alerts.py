import logging
import httpx
import json
import redis.asyncio as aioredis
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

async def send_slack_notification(payload: dict):
    webhook_url = settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        logger.debug("Slack Webhook URL is not configured. Skipping alert.")
        return

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=5.0)
            resp.raise_for_status()
            logger.info("Sent Slack alert successfully.")
    except Exception as exc:
        logger.error("Failed to send Slack notification: %s", exc)

async def check_and_send_alerts(telemetry_payload: dict, redis_client = None):
    webhook_url = settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        return

    # Use Redis to de-duplicate alerts and avoid spamming
    created_client = False
    if redis_client is None:
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        created_client = True
    
    try:
        resilience = telemetry_payload.get("global_resilience_index")
        
        # 1. Check Global Resilience Alert (< 50)
        if resilience is not None and resilience < 50:
            alert_key = "simulation:alert:global_resilience"
            already_sent = await redis_client.get(alert_key)
            if not already_sent:
                # Set alert key with a 15-minute TTL
                await redis_client.setex(alert_key, 900, "sent")
                
                payload = {
                    "text": "🚨 *CRITICAL WARNING: Global Logistics Resilience Degraded!*",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"🚨 *CRITICAL WARNING: Global Logistics Resilience Degraded!*\n*Global Resilience Index:* `{resilience}/100`\nActive Port Count: `{telemetry_payload.get('network_density', {}).get('nodes', 0)}`\nActive Corridor Count: `{telemetry_payload.get('network_density', {}).get('edges', 0)}`"
                            }
                        }
                    ]
                }
                await send_slack_notification(payload)

        # 2. Check individual route failures (CRITICAL status)
        metrics = telemetry_payload.get("metrics", [])
        for m in metrics:
            if m.get("status") == "CRITICAL":
                lane_id = m.get("id")
                lane_name = m.get("name")
                risk_score = m.get("risk_score")
                
                alert_key = f"simulation:alert:route:{lane_id}"
                already_sent = await redis_client.get(alert_key)
                if not already_sent:
                    # Set alert key with a 15-minute TTL
                    await redis_client.setex(alert_key, 900, "sent")
                    
                    payload = {
                        "text": f"⚠️ *CRITICAL ROUTE BLOCKAGE: {lane_name}*",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"⚠️ *CRITICAL ROUTE BLOCKAGE DETECTED!*\n*Route:* `{lane_name}`\n*Lane ID:* `{lane_id}`\n*Current Risk Score:* `{risk_score}`\n*Congestion Level:* `{m.get('congestion')}%`"
                                }
                            }
                        ]
                    }
                    await send_slack_notification(payload)

    except Exception as exc:
        logger.warning("Error running alerting check: %s", exc)
    finally:
        if created_client and redis_client:
            await redis_client.close()
