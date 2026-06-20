"""Analytics API routes — carbon footprint, port details, simulation events timeline."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.dependencies import get_analytics_engine, get_redis_client
from app.db.postgres import get_db
from app.services.carbon_tracker import compute_carbon_analytics
from app.services.event_log import get_recent_events

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


@router.get(
    "/carbon",
    summary="Fleet-wide carbon footprint analytics",
    description=(
        "Computes CO2 emissions, IMO 2030 eco-score, EU ETS cost estimates, "
        "Scope 3 corridor breakdown, and best/worst lane rankings."
    ),
)
async def get_carbon_analytics(engine=Depends(get_analytics_engine)):
    """Compute real-time carbon analytics from the live GNN inference cycle."""
    try:
        cycle = await engine.run_inference_cycle()
        metrics = cycle.get("metrics", [])
        return compute_carbon_analytics(metrics)
    except Exception as exc:
        logger.error("Carbon analytics computation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to compute carbon analytics.")

from fastapi import Query
@router.get(
    "/forecast",
    summary="Predictive time-series forecasting",
    description="Predicts the network state X days into the future."
)
async def forecast_network(
    days: int = Query(7, ge=1, le=14),
    engine = Depends(get_analytics_engine)
):
    try:
        payload = await engine.simulate_future_state(days)
        return payload
    except Exception as exc:
        logger.error("Forecast computation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to compute forecast.")


@router.get(
    "/events",
    summary="Simulation event timeline",
    description="Returns the most recent simulation and alert events for the AlertsTimeline UI.",
)
async def get_event_timeline(limit: int = 50, db=Depends(get_db)):
    """Fetch recent disruption, alert, and simulation events from the audit log."""
    try:
        events = await get_recent_events(db, limit=min(limit, 200))
        return {"events": events, "total": len(events)}
    except Exception as exc:
        logger.error("Failed to fetch event timeline: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch event timeline.")


@router.get(
    "/ports/{port_id}",
    summary="Port detail analytics",
    description="Returns detailed metrics for a specific port including risk history and active lanes.",
)
async def get_port_details(port_id: str, engine=Depends(get_analytics_engine)):
    """Fetch detailed risk and operational data for a specific port."""
    try:
        cycle = await engine.run_inference_cycle()
        metrics = cycle.get("metrics", [])

        port_lanes = [
            m for m in metrics
            if m.get("source_id", "").upper() == port_id.upper()
            or m.get("target_id", "").upper() == port_id.upper()
        ]
        if not port_lanes:
            raise HTTPException(status_code=404, detail=f"Port '{port_id}' not found or has no active lanes.")

        risk_scores = [m["risk_score"] for m in port_lanes]
        avg_risk = round(sum(risk_scores) / len(risk_scores), 3)
        max_risk = round(max(risk_scores), 3)

        # Collect unique connected ports
        connections = set()
        for m in port_lanes:
            if m.get("source_id", "").upper() == port_id.upper():
                connections.add(m["target_id"])
            else:
                connections.add(m["source_id"])

        return {
            "port_id": port_id.upper(),
            "active_lanes": len(port_lanes),
            "avg_risk": avg_risk,
            "max_risk": max_risk,
            "resilience_index": int(round((1.0 - avg_risk) * 100)),
            "connected_ports": list(connections),
            "lane_details": port_lanes,
            "global_context": {
                "global_risk": cycle.get("global_risk"),
                "global_resilience": cycle.get("global_resilience_index"),
                "total_lanes": cycle.get("network_density", {}).get("edges"),
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Port detail analytics failed for %s: %s", port_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch port details.")


@router.get(
    "/network/summary",
    summary="Full network health summary",
    description="Returns health grid data for all ports — risk, status, congestion, and lane count.",
)
async def get_network_summary(engine=Depends(get_analytics_engine)):
    """Aggregate per-port health metrics for the NetworkHealthGrid UI component."""
    try:
        cycle = await engine.run_inference_cycle()
        metrics = cycle.get("metrics", [])

        port_map = {}
        for m in metrics:
            for pid_key, coords_key in [("source_id", "source_coords"), ("target_id", "target_coords")]:
                pid = m.get(pid_key, "").upper()
                if not pid:
                    continue
                if pid not in port_map:
                    port_map[pid] = {
                        "port_id": pid,
                        "name": m.get("name", "").split("➔")[0 if pid_key == "source_id" else 1].strip() if "➔" in m.get("name", "") else pid,
                        "coords": m.get(coords_key, [0, 0]),
                        "risk_scores": [],
                        "lane_count": 0,
                        "congestion": m.get("congestion", 0),
                    }
                port_map[pid]["risk_scores"].append(m["risk_score"])
                port_map[pid]["lane_count"] += 1
                port_map[pid]["congestion"] = max(port_map[pid]["congestion"], m.get("congestion", 0))

        ports_summary = []
        for port_id, data in port_map.items():
            risk_scores = data["risk_scores"]
            avg_risk = round(sum(risk_scores) / len(risk_scores), 3) if risk_scores else 0.3
            status = "CRITICAL" if avg_risk >= 0.70 else ("WARNING" if avg_risk >= 0.45 else "STABLE")
            ports_summary.append({
                "port_id": port_id,
                "name": data["name"],
                "coords": data["coords"],
                "avg_risk": avg_risk,
                "status": status,
                "resilience_index": int(round((1.0 - avg_risk) * 100)),
                "lane_count": data["lane_count"],
                "congestion": data["congestion"],
            })

        ports_summary.sort(key=lambda x: x["avg_risk"], reverse=True)
        return {
            "ports": ports_summary,
            "global_risk": cycle.get("global_risk"),
            "global_resilience": cycle.get("global_resilience_index"),
            "timestamp": cycle.get("timestamp"),
        }
    except Exception as exc:
        logger.error("Network summary computation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to compute network summary.")
