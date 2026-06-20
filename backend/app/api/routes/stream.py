"""Hardened WebSocket stream endpoint.

Features:
  - Multi-client connection registry (fan-out broadcast)
  - Heartbeat ping/pong with configurable interval
  - Graceful disconnect with cleanup
  - Per-connection Redis pubsub channel (avoids shared state issues)
  - Client-to-server message handling (run_simulation action)
"""
import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings

router = APIRouter(tags=["stream"])
settings = get_settings()
logger = logging.getLogger(__name__)

# ─── Connection Registry ──────────────────────────────────────────────────────
# Tracks all active WebSocket clients for observability and fan-out
_active_connections: set = set()


@router.websocket("/api/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _active_connections.add(websocket)
    client_id = id(websocket)
    logger.info("WebSocket client connected [id=%s] total=%d", client_id, len(_active_connections))

    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel = settings.REDIS_STREAM_CHANNEL

    try:
        await pubsub.subscribe(channel, "stream:agent_proposals", "telemetry:ais", "telemetry:iot", "telemetry:disruptions")

        async def read_from_redis():
            """Forwards Redis pub/sub messages to the WebSocket client."""
            while True:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=0.5
                    )
                    if message and message.get("type") == "message":
                        await websocket.send_text(message["data"])
                    else:
                        # Heartbeat keeps the connection alive through proxies
                        await websocket.send_text(json.dumps({"type": "heartbeat"}))
                    await asyncio.sleep(0.1)
                except WebSocketDisconnect:
                    break
                except Exception as exc:
                    logger.debug("Redis→WS forward error [id=%s]: %s", client_id, exc)
                    break

        async def read_from_client():
            """Handles client-to-server messages (e.g. trigger simulation)."""
            while True:
                try:
                    data = await websocket.receive_text()
                    try:
                        payload = json.loads(data)
                        if payload.get("action") == "run_simulation":
                            from app.celery_app import run_gnn_simulation
                            task = run_gnn_simulation.delay({"mode": "manual"})
                            await websocket.send_text(
                                json.dumps({"type": "task_started", "task_id": task.id})
                            )
                            logger.info("Manual simulation task dispatched [id=%s]", client_id)
                        elif payload.get("action") == "ping":
                            await websocket.send_text(json.dumps({"type": "pong"}))
                    except json.JSONDecodeError:
                        pass
                except WebSocketDisconnect:
                    break
                except Exception as exc:
                    logger.debug("WS receive error [id=%s]: %s", client_id, exc)
                    break

        # Run both loops concurrently; whichever raises first causes cleanup
        await asyncio.gather(read_from_redis(), read_from_client())

    except WebSocketDisconnect:
        logger.info("WebSocket client cleanly disconnected [id=%s]", client_id)
    except Exception as exc:
        logger.warning("WebSocket session error [id=%s]: %s", client_id, exc)
    finally:
        _active_connections.discard(websocket)
        logger.info(
            "WebSocket cleanup complete [id=%s] remaining=%d", client_id, len(_active_connections)
        )
        try:
            await pubsub.unsubscribe(channel, "stream:agent_proposals", "telemetry:ais", "telemetry:iot", "telemetry:disruptions")
            await pubsub.aclose()
            await redis_client.aclose()
        except Exception as exc:
            logger.debug("WebSocket stream cleanup warning: %s", exc)


@router.get("/api/v1/stream/status", tags=["stream"], summary="Active WebSocket connection count")
async def stream_status():
    """Returns the number of active WebSocket connections — useful for Prometheus scraping."""
    return {"active_websocket_connections": len(_active_connections)}
