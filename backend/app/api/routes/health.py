from fastapi import APIRouter
from app.core.config import get_settings
from app.db.neo4j import db

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get(
    "/health",
    summary="Full system health check",
    description="Checks Neo4j, Redis, Postgres, and Kafka connectivity. Returns 200 OK when all critical services are healthy, or 207 Multi-Status when partially degraded.",
)
async def health():
    checks = {}

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    try:
        async with db.get_session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            checks["neo4j"] = record is not None and record["ok"] == 1
    except Exception:
        checks["neo4j"] = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.close()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    # ── Postgres ──────────────────────────────────────────────────────────────
    try:
        from sqlalchemy import text
        from app.db.postgres import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        checks["postgres"] = False

    # ── Kafka (optional — may not be running in dev) ───────────────────────────
    checks["kafka"] = "disabled"
    if settings.KAFKA_ENABLED:
        try:
            from aiokafka.admin import AIOKafkaAdminClient
            admin = AIOKafkaAdminClient(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                request_timeout_ms=2000,
            )
            await admin.start()
            await admin.close()
            checks["kafka"] = True
        except Exception:
            checks["kafka"] = False

    all_critical_ok = checks["neo4j"] and checks["redis"] and checks["postgres"]
    http_status = 200 if all_critical_ok else 207

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=http_status,
        content={
            "status": "healthy" if all_critical_ok else "degraded",
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
        }
    )


@router.get("/ready", summary="Readiness probe for Kubernetes/Docker")
async def ready():
    return await health()
