import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from prometheus_client import make_asgi_app

from app.api.routes import graph, health, pathfinder, stream, simulations, analytics, dcsa
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.core.middleware import PrometheusMiddleware, SecurityHeadersMiddleware
from app.core.telemetry import setup_telemetry
from app.db.graph_seed import seed_graph_if_empty
from app.db.neo4j import db
from app.db.postgres import init_postgres_db
from app.services.analytics import AnalyticsEngine

# Initialize structured logging
setup_logging()
logger = logging.getLogger("logi-resilience")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Database connections ──────────────────────────────────────────────────
    await db.connect()
    await seed_graph_if_empty()
    try:
        await init_postgres_db()
        logger.info("PostgreSQL tables checked/initialized.")
    except Exception as e:
        logger.warning("PostgreSQL initialization skipped: %s", e)

    # ── Singleton AnalyticsEngine (eliminates per-request GNN load) ───────────
    redis_pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    app.state.redis_pool = redis_pool
    redis_client = aioredis.Redis(connection_pool=redis_pool)
    app.state.engine = AnalyticsEngine(redis_client=redis_client)
    logger.info("Singleton AnalyticsEngine initialized.")

    # ── MinIO model-registry bucket provisioning ──────────────────────────────
    try:
        from minio import Minio
        endpoint = settings.MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
        minio_client = Minio(
            endpoint,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        bucket = settings.MINIO_BUCKET
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
            logger.info("MinIO bucket '%s' successfully provisioned.", bucket)
        else:
            logger.info("MinIO bucket '%s' is present.", bucket)
    except Exception as e:
        logger.warning("MinIO auto-provisioning skipped: %s", e)

    logger.info("%s v%s started [%s]", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)
    yield

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    await db.close()
    await redis_pool.disconnect()
    logger.info("Logi-Resilience shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "🌐 **Logi-Resilience** — AI-powered maritime logistics resilience platform.\n\n"
        "Real-time GNN risk inference, multi-modal route optimization, disruption simulation, "
        "and carbon footprint analytics for global supply chains.\n\n"
        "**Stack:** FastAPI · Neo4j · PyTorch Geometric · Kafka · Redis · OpenTelemetry · Keycloak"
    ),
    lifespan=lifespan,
    contact={"name": "Logi-Resilience Operations", "email": "ops@logiresilience.io"},
    license_info={"name": "Enterprise", "url": "https://logiresilience.io/license"},
)

# ── Observability ─────────────────────────────────────────────────────────────
setup_telemetry(app)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middlewares (order matters: outermost runs first) ─────────────────────────
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(PrometheusMiddleware)

origins = settings.CORS_ORIGINS if settings.CORS_ORIGINS != ["*"] else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.graphql import graphql_app

app.include_router(health.router)
app.include_router(graph.router)
app.include_router(pathfinder.router)
app.include_router(stream.router)
app.include_router(simulations.router)
app.include_router(analytics.router)
app.include_router(dcsa.router)
app.include_router(graphql_app, prefix="/graphql")


@app.get("/", tags=["root"], summary="API root — service info and documentation links")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "redoc": "/redoc",
        "graphql": "/graphql",
        "stream": "/api/v1/stream",
        "metrics": "/metrics",
        "health": "/health",
    }
