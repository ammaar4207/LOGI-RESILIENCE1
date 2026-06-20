from fastapi import APIRouter, Depends

from app.db.neo4j import db
from app.core.dependencies import get_analytics_engine

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


@router.get("/ports")
async def list_ports():
    return {"ports": await db.list_ports()}


@router.get("/snapshot")
async def graph_snapshot(engine=Depends(get_analytics_engine)):
    return await engine.run_inference_cycle()
