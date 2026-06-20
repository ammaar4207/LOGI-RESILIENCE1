import os
from celery import Celery
from app.core.config import get_settings
import logging
import app.core.telemetry # Registers OpenTelemetry signals
from celery.schedules import crontab

settings = get_settings()

logger = logging.getLogger(__name__)

celery_app = Celery(
    "logi_resilience",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
    include=['app.worker']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        'run-periodic-inference': {
            'task': 'run_gnn_simulation',
            'schedule': crontab(minute=0, hour='*/1'),
            'args': ({},),
        },
    },
)

@celery_app.task(bind=True, name="run_gnn_simulation")
def run_gnn_simulation(self, params: dict):
    """
    Background task to run a heavy pathfinding or GNN simulation without blocking the API.
    """
    logger.info(f"Starting GNN simulation task with params: {params}")
    # In a real scenario, this imports the analytics engine and runs inference
    import asyncio
    from app.services.analytics import AnalyticsEngine
    
    engine = AnalyticsEngine()
    
    # Run the async engine in a new event loop for this Celery worker thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(engine.run_inference_cycle())
    loop.close()
    
    return result
