from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.neo4j import db
from app.core.dependencies import get_analytics_engine, get_redis_client
from app.services.pathfinder import calculate_dijkstra_path
from app.db.postgres import get_db
from app.services.event_log import log_event
from app.services.llm import LocalLLMService
import json

router = APIRouter(prefix="/api/v1/pathfinder", tags=["pathfinder"])
settings = get_settings()


class SimulationRequest(BaseModel):
    source_id: str
    target_id: str
    avoid_edge_id: Optional[str] = None
    optimization_mode: str = Field(
        default="resilience",
        description="resilience | sustainability | financial | essential",
    )
    forecast_days: int = Field(
        default=0,
        description="Number of days to forecast into the future for pathfinding (0 = live)"
    )

@router.post("/simulate")
@limiter.limit(settings.RATE_LIMIT_SIMULATE)
async def simulate_route(payload: SimulationRequest, request: Request, engine=Depends(get_analytics_engine), pg_db=Depends(get_db), redis_client=Depends(get_redis_client)):
    if payload.forecast_days > 0:
        cycle = await engine.simulate_future_state(payload.forecast_days)
    else:
        cycle = await engine.run_inference_cycle()
        
    geo_nodes, _, _, _ = await db.get_dynamic_topology()
    metrics = cycle.get("metrics", [])

    if not geo_nodes or not metrics:
        raise HTTPException(
            status_code=400,
            detail="Graph topology empty. Ensure Neo4j is seeded.",
        )

    mode = payload.optimization_mode.lower()
    if mode not in ("resilience", "sustainability", "financial", "essential"):
        mode = "resilience"

    result, error = calculate_dijkstra_path(
        geo_nodes,
        metrics,
        payload.source_id,
        payload.target_id,
        payload.avoid_edge_id,
        mode,
        essential_boost=(mode == "essential"),
    )

    if error:
        raise HTTPException(status_code=400, detail=error)
        
    await log_event(
        db=pg_db,
        event_type="route_simulated",
        target=f"{payload.source_id}->{payload.target_id}",
        details={
            "mode": mode,
            "distance_km": result.get("summary", {}).get("total_distance_km"),
            "hops": len(result.get("nodes", []))
        },
        global_resilience=cycle.get("global_resilience_index")
    )
    # Generate Mitigation Strategy if disruptions exist
    mitigation_strategy = None
    if redis_client:
        try:
            d_raw = await redis_client.get("simulation:disruptions")
            disruptions = json.loads(d_raw) if d_raw else []
            if disruptions:
                # Filter disruptions relevant to this path request
                relevant_disruptions = []
                for d in disruptions:
                    target = str(d.get("target", "")).lower()
                    if payload.avoid_edge_id and target == payload.avoid_edge_id.lower():
                        relevant_disruptions.append(d)
                    else:
                        # If the disruption target is an edge (e.g., cnsha-uslax), check if our source or dest is part of it
                        target_parts = target.split("-")
                        if payload.source_id.lower() in target_parts or payload.target_id.lower() in target_parts or target == payload.source_id.lower() or target == payload.target_id.lower():
                            relevant_disruptions.append(d)
                
                if not relevant_disruptions:
                    # check if any disruption targets the calculated path
                    path_nodes_lower = [n.lower() for n in result.get("nodes", [])]
                    path_lanes_lower = [l.lower() for l in result.get("lanes", [])]
                    for d in disruptions:
                        target = str(d.get("target", "")).lower()
                        if target in path_nodes_lower or target in path_lanes_lower:
                            relevant_disruptions.append(d)

                if relevant_disruptions:
                    highest_d = max(relevant_disruptions, key=lambda x: float(x.get("severity", 0)))
                    llm = LocalLLMService()
                    mitigation_strategy = await llm.generate_mitigation_strategy(
                        disruption_type=highest_d.get("type", "custom"),
                        target_node=highest_d.get("target", "Unknown"),
                        severity=float(highest_d.get("severity", 0.8)),
                        radius_km=float(highest_d.get("radius_km", 1000.0)),
                        optimization_mode=mode
                    )
        except Exception as exc:
            pass
            
    if mitigation_strategy:
        result["mitigation_strategy"] = mitigation_strategy
    
    return result
