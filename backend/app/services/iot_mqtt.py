import asyncio
import json
import logging
from datetime import datetime, timezone
import aiomqtt
import redis.asyncio as aioredis
from app.core.config import get_settings
from app.db.postgres import async_session_maker
from app.services.event_log import log_event

logger = logging.getLogger("logi-resilience.iot")

class IoTTelemetryService:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.settings = get_settings()
        # For local Docker-compose, mosquitto is at 'mosquitto' 
        self.mqtt_broker = "mosquitto"
        self.mqtt_port = 1883
        
    async def listen_for_telemetry(self):
        logger.info(f"Connecting to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}...")
        
        while True:
            try:
                # Need to use the async context manager to connect
                async with aiomqtt.Client(hostname=self.mqtt_broker, port=self.mqtt_port) as client:
                    logger.info("Successfully connected to Mosquitto MQTT broker.")
                    await client.subscribe("telemetry/reefer/#")
                    
                    async for message in client.messages:
                        await self.process_message(message)
                        
            except aiomqtt.MqttError as error:
                logger.warning(f"MQTT connection lost: {error}. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as exc:
                logger.error(f"Unexpected MQTT error: {exc}")
                await asyncio.sleep(5)

    async def _simulate_iot_telemetry(self):
        """Background task to simulate high-frequency IoT telemetry and occasionally inject anomalies."""
        await asyncio.sleep(10) # wait for startup
        logger.info("Starting IoT Telemetry Simulation loop...")
        while True:
            try:
                async with aiomqtt.Client(hostname=self.mqtt_broker, port=self.mqtt_port) as client:
                    container_id = "MSCU1234567"
                    # normal temp is ~2.0, anomaly is 7.5
                    import random
                    if random.random() < 0.1:
                        temp = 7.5 + random.uniform(0, 1)
                    else:
                        temp = 2.0 + random.uniform(-0.5, 0.5)
                        
                    payload = json.dumps({
                        "temperature": temp,
                        "humidity": 45.0 + random.uniform(-2, 2)
                    })
                    
                    await client.publish(f"telemetry/reefer/{container_id}", payload=payload)
                    await asyncio.sleep(15) # Publish every 15 seconds
            except Exception as exc:
                logger.debug(f"IoT Simulator connection error: {exc}")
                await asyncio.sleep(5)

    async def process_message(self, message: aiomqtt.Message):
        try:
            payload = json.loads(message.payload.decode())
            topic = message.topic.value
            
            # Extract container ID from topic e.g., telemetry/reefer/MSCU1234567
            container_id = topic.split("/")[-1]
            
            # Anomaly Detection: Temperature Threshold for Pharmaceuticals
            temperature = payload.get("temperature", 0.0)
            
            if temperature > 5.0:
                logger.warning(f"🚨 COLD CHAIN ALERT: Container {container_id} temp spike detected: {temperature}°C")
                
                alert_payload = {
                    "type": "iot_alert",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "CRITICAL",
                    "source": "Cold Chain Sensor",
                    "container_id": container_id,
                    "message": f"Temperature deviation detected ({temperature}°C). Target: 2.0°C - 5.0°C. High risk of spoilage.",
                    "temperature": temperature,
                    "humidity": payload.get("humidity", 0)
                }
                
                # Publish to Redis so WebSockets can pick it up and push to frontend
                await self.redis.publish("telemetry:iot", json.dumps(alert_payload))
                
                # Write to the Postgres Audit Log Timeline
                async with async_session_maker() as db_session:
                    await log_event(
                        db=db_session,
                        event_type="alert_fired",
                        target=f"Container {container_id}",
                        severity=0.8,
                        details={"type": "iot_alert", "message": alert_payload["message"]},
                        global_resilience=None
                    )
                
        except json.JSONDecodeError:
            logger.error("Failed to decode MQTT message payload.")
        except Exception as exc:
            logger.error(f"Error processing MQTT message: {exc}")
