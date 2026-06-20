import json
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.dependencies import get_analytics_engine, get_redis_client
from app.core.auth import require_roles
from app.services.llm import LocalLLMService
from app.db.postgres import get_db
from app.services.event_log import log_event
from app.services.weather import fetch_live_weather
import uuid

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])
settings = get_settings()
logger = logging.getLogger(__name__)


class DisruptionModel(BaseModel):
    id: str = Field(..., description="Unique disruption identifier")
    type: str = Field(..., description="strike | hurricane | blockade | custom")
    target: str = Field(..., description="Port ID, Lane ID, or coordinate label")
    severity: float = Field(0.8, ge=0.0, le=1.0)
    weather: Optional[float] = 0.0
    congestion: Optional[float] = 0.0
    news: Optional[float] = 0.0
    radius_km: Optional[float] = 1000.0
    lat: Optional[float] = None
    lon: Optional[float] = None
    label: Optional[str] = ""
    mitigation: Optional[str] = ""


class DetourApprovalModel(BaseModel):
    lane_id: str = Field(..., description="The ID of the lane to detour")
    alternative_lanes: List[str] = Field(..., description="List of alternative lane IDs")
    is_essential: bool = Field(False, description="Whether this is a humanitarian/essential detour")



@router.get("/disruptions", response_model=List[DisruptionModel])
async def list_disruptions(redis_client=Depends(get_redis_client)):
    try:
        data = await redis_client.get("simulation:disruptions")
        if not data:
            return []
        return json.loads(data)
    except Exception as exc:
        logger.error("Failed to read disruptions: %s", exc)
        raise HTTPException(status_code=500, detail="Database failure reading disruptions.")


@router.post("/disruptions")
async def save_disruptions(
    disruptions: List[DisruptionModel], 
    redis_client=Depends(get_redis_client),
    engine=Depends(get_analytics_engine),
    db=Depends(get_db),
    _user=Depends(require_roles(["admin", "dispatcher"]))
):
    try:
        llm = LocalLLMService()
        for d in disruptions:
            if not d.mitigation:
                d.mitigation = await llm.generate_mitigation_strategy(
                    disruption_type=d.type,
                    target_node=d.target,
                    severity=d.severity
                )
            
            # Autocomplete lat/lon if missing so map scatterplots render correctly
            if d.lat is None or d.lon is None:
                try:
                    from app.db.neo4j import db as neo_db
                    geo_nodes, _, _, _ = await neo_db.get_dynamic_topology()
                    
                    target_parts = str(d.target).replace("lane_", "").split("-")
                    if len(target_parts) == 2:
                        src_id = target_parts[0].strip().lower()
                        tgt_id = target_parts[1].strip().lower()
                        src_node, tgt_node = None, None
                        for n in geo_nodes:
                            n_id = str(n.get("id")).strip().lower()
                            if n_id == src_id:
                                src_node = n
                            elif n_id == tgt_id:
                                tgt_node = n
                        if src_node and tgt_node:
                            lon1 = float(src_node.get("lon"))
                            lon2 = float(tgt_node.get("lon"))
                            diff = abs(lon1 - lon2)
                            if diff > 180:
                                if lon1 < 0:
                                    lon1 += 360
                                else:
                                    lon2 += 360
                            mid_lon = (lon1 + lon2) / 2.0
                            if mid_lon > 180:
                                mid_lon -= 360
                                
                            d.lat = (float(src_node.get("lat")) + float(tgt_node.get("lat"))) / 2.0
                            d.lon = mid_lon
                    elif len(target_parts) == 1:
                        src_id = target_parts[0].strip().lower()
                        for n in geo_nodes:
                            if str(n.get("id")).strip().lower() == src_id:
                                d.lat = float(n.get("lat"))
                                d.lon = float(n.get("lon"))
                                break
                except Exception as e:
                    logger.warning(f"Failed to lookup lat/lon for disruption: {e}")

            # Fetch live weather if coordinates are available
            if d.lat is not None and d.lon is not None:
                weather_data = await fetch_live_weather(d.lat, d.lon)
                wind_speed = weather_data.get("wind_speed_kmh", 0.0)
                # If wind speed is high (e.g. > 50km/h), increase severity dynamically
                if wind_speed > 50.0:
                    d.severity = min(1.0, d.severity + (wind_speed / 200.0))
                    logger.info(f"Dynamically increased severity to {d.severity} due to wind speed {wind_speed}km/h")
                # Store weather code for reference
                d.weather = weather_data.get("weather_code", 0.0)

        # Fetch existing
        existing_data = await redis_client.get("simulation:disruptions")
        existing_list = json.loads(existing_data) if existing_data else []
        
        existing_dict = {d["target"]: d for d in existing_list}
        
        # Merge new disruptions
        for d in disruptions:
            existing_dict[d.target] = d.dict()
            
        final_list = list(existing_dict.values())
        
        # Save to Redis
        await redis_client.set("simulation:disruptions", json.dumps(final_list))
        
        # Clear scraping cache so new values are pulled immediately
        await redis_client.delete("ingestion:environmental_v1")
        
        # Trigger immediate inference and update broadcast
        payload = await engine.run_and_publish_telemetry(force=True)
        
        for d in disruptions:
            await log_event(
                db=db,
                event_type="disruption_injected",
                target=d.target,
                severity=d.severity,
                details={"type": d.type, "mitigation": d.mitigation},
                global_resilience=payload.get("global_resilience_index")
            )
        
        return {
            "status": "SUCCESS",
            "message": f"Applied {len(disruptions)} active disruptions and generated mitigations.",
            "global_resilience": payload.get("global_resilience_index"),
            "disruptions": final_list
        }
    except Exception as exc:
        logger.error("Failed to save disruptions: %s", exc)
        raise HTTPException(status_code=500, detail=f"Simulation engine failure: {str(exc)}")


@router.delete("/disruptions")
async def clear_disruptions(
    redis_client=Depends(get_redis_client),
    engine=Depends(get_analytics_engine),
    db=Depends(get_db),
    _user=Depends(require_roles(["admin", "dispatcher"]))
):
    try:
        # Clear from Redis
        await redis_client.delete("simulation:disruptions")
        await redis_client.delete("simulation:active_detours")
        await redis_client.delete("simulation:agent:cooldown")
        
        # Clear all proposed lane cooldowns
        proposed_keys = await redis_client.keys("simulation:agent:proposed:*")
        if proposed_keys:
            await redis_client.delete(*proposed_keys)
        
        # Clear scraping cache
        await redis_client.delete("ingestion:environmental_v1")
        
        # Trigger immediate inference and update broadcast
        payload = await engine.run_and_publish_telemetry(force=True)
        
        await log_event(
            db=db,
            event_type="disruption_cleared",
            target="ALL",
            details={"message": "All active disruptions cleared"},
            global_resilience=payload.get("global_resilience_index")
        )
        
        return {
            "status": "SUCCESS",
            "message": "Cleared all disruptions and reset logistics network.",
            "global_resilience": payload.get("global_resilience_index")
        }
    except Exception as exc:
        logger.error("Failed to clear disruptions: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to reset simulation state.")

@router.delete("/disruptions/{target}")
async def remove_disruption(
    target: str,
    redis_client=Depends(get_redis_client),
    engine=Depends(get_analytics_engine),
    db=Depends(get_db),
    _user=Depends(require_roles(["admin", "dispatcher"]))
):
    try:
        # Fetch existing
        existing_data = await redis_client.get("simulation:disruptions")
        existing_list = json.loads(existing_data) if existing_data else []
        
        # Filter out the one to remove
        final_list = [d for d in existing_list if str(d.get("target")).strip().lower() != target.strip().lower()]
        
        # Save to Redis
        await redis_client.set("simulation:disruptions", json.dumps(final_list))
        
        target_lane = "lane_" + target.strip().lower().replace("-", "_")
        
        # Remove from active_detours if it matches
        detours_raw = await redis_client.get("simulation:active_detours")
        if detours_raw:
            detours_dict = json.loads(detours_raw)
            if target_lane in detours_dict:
                del detours_dict[target_lane]
                await redis_client.set("simulation:active_detours", json.dumps(detours_dict))
                
        # Clear agent cooldowns for this specific target
        target_lane = "lane_" + target.strip().lower().replace("-", "_")
        await redis_client.delete(f"simulation:agent:proposed:{target_lane}")
        await redis_client.delete("simulation:agent:cooldown")
        
        # Clear scraping cache
        await redis_client.delete("ingestion:environmental_v1")
        
        # Trigger immediate inference and update broadcast
        payload = await engine.run_and_publish_telemetry(force=True)
        
        await log_event(
            db=db,
            event_type="disruption_cleared",
            target=target,
            details={"message": f"Disruption on {target} cleared"},
            global_resilience=payload.get("global_resilience_index")
        )
        
        return {
            "status": "SUCCESS",
            "message": f"Cleared disruption for {target}.",
            "global_resilience": payload.get("global_resilience_index"),
            "disruptions": final_list
        }
    except Exception as exc:
        logger.error("Failed to remove disruption: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to remove disruption.")


@router.post("/approve_detour")
async def approve_detour(
    detour: DetourApprovalModel,
    redis_client=Depends(get_redis_client),
    engine=Depends(get_analytics_engine),
    db=Depends(get_db),
    _user=Depends(require_roles(["admin", "dispatcher"]))
):
    try:
        active_raw = await redis_client.get("simulation:active_detours")
        active_detours = json.loads(active_raw) if active_raw else {}
        active_detours[detour.lane_id.strip().lower()] = detour.alternative_lanes
        await redis_client.set("simulation:active_detours", json.dumps(active_detours))
        
        # Trigger immediate inference and update broadcast
        payload = await engine.run_and_publish_telemetry(force=True)
        
        await log_event(
            db=db,
            event_type="detour_approved",
            target=detour.lane_id,
            details={"alternative_lanes": detour.alternative_lanes},
            global_resilience=payload.get("global_resilience_index")
        )
        
        # Generate Carrier Booking Reference
        booking_ref = f"BKG-{uuid.uuid4().hex[:6].upper()}-MSK"
        
        # Generate Shipper Email via LLM
        llm = LocalLLMService()
        email_content = await llm.generate_shipper_email(detour.lane_id, detour.alternative_lanes, detour.is_essential)
        
        # Store booking in Redis
        bookings_raw = await redis_client.get("simulation:active_bookings")
        bookings_list = json.loads(bookings_raw) if bookings_raw else []
        bookings_list.append({
            "booking_ref": booking_ref,
            "lane_id": detour.lane_id,
            "alternative_lanes": detour.alternative_lanes,
            "email_content": email_content,
            "is_essential": detour.is_essential
        })
        await redis_client.set("simulation:active_bookings", json.dumps(bookings_list))
        
        return {
            "status": "SUCCESS",
            "message": f"Detour implemented for {detour.lane_id}.",
            "global_resilience": payload.get("global_resilience_index"),
            "booking_reference": booking_ref,
            "shipper_email": email_content
        }
    except Exception as exc:
        logger.error("Failed to approve detour: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to approve detour.")


@router.get("/bookings")
async def list_active_bookings(
    redis_client=Depends(get_redis_client),
    _user=Depends(require_roles(["admin", "dispatcher"]))
):
    try:
        data = await redis_client.get("simulation:active_bookings")
        if not data:
            return []
        return json.loads(data)
    except Exception as exc:
        logger.error("Failed to read active bookings: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to read bookings.")


