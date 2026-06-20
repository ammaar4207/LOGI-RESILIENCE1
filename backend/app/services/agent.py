import logging
import json
from app.services.llm import LocalLLMService

from app.db.neo4j import db
from app.services.analytics import NGO_CAMPS

logger = logging.getLogger(__name__)

async def run_autonomous_agent(telemetry_payload: dict, redis_client=None):
    if not redis_client:
        return
        
    resilience = telemetry_payload.get("global_resilience_index")
    print(f"DEBUG: Agent triggered with resilience {resilience}", flush=True)
    if resilience is None or resilience >= 75:
        return
        
    metrics = telemetry_payload.get("metrics", [])
    critical_lanes = [m for m in metrics if m.get("status") == "CRITICAL" and not m.get("is_detoured")]
    
    # Sort by risk score descending so highest risk lanes get prioritized
    critical_lanes = sorted(critical_lanes, key=lambda x: float(x.get("risk_score", 0.0)), reverse=True)
    
    print(f"DEBUG: Agent found {len(critical_lanes)} critical un-detoured lanes", flush=True)
    if not critical_lanes:
        await redis_client.delete("simulation:agent:last_proposal")
        return
        
    # Clear stale proposals for lanes that are no longer critical
    last_proposal_raw = await redis_client.get("simulation:agent:last_proposal")
    if last_proposal_raw:
        try:
            last_proposal = json.loads(last_proposal_raw)
            lane_id = last_proposal.get("agent_proposal", {}).get("lane_id")
            if lane_id not in [l.get("id") for l in critical_lanes]:
                await redis_client.delete("simulation:agent:last_proposal")
        except:
            pass
            
    # We only trigger the agent if it hasn't triggered recently
    agent_key = "simulation:agent:cooldown"
    on_cooldown = await redis_client.get(agent_key)
    if on_cooldown:
        print(f"DEBUG: Agent is on cooldown.", flush=True)
        return
        
    await redis_client.setex(agent_key, 60, "active") # 60 sec cooldown
    
    # Run pathfinder to find alternative
    try:
        from app.services.pathfinder import calculate_dijkstra_path
        from app.core.config import get_settings
        geo_nodes, _, _, _ = await db.get_dynamic_topology()
        settings = get_settings()
        
        for target_lane in critical_lanes:
            lane_id = target_lane.get("id")
            
            # Check if we recently proposed a detour for this specific lane
            lane_cooldown_key = f"simulation:agent:proposed:{lane_id}"
            if await redis_client.get(lane_cooldown_key):
                print(f"DEBUG: Lane {lane_id} was recently proposed. Skipping.", flush=True)
                continue
                
            src = target_lane.get("source_id")
            tgt = target_lane.get("target_id")
            
            target_camp = next((c for c in NGO_CAMPS if c["port_id"] == tgt.lower()), None)
            mode = "essential" if target_camp else "resilience"
            
            alt_path, error = calculate_dijkstra_path(
                nodes=geo_nodes,
                metrics=metrics,
                source_id=src,
                target_id=tgt,
                avoid_edge_id=lane_id,
                mode=mode
            )
            if error or not alt_path:
                logger.warning(f"Agent failed to find detour for {lane_id}: error={error}")
                continue # Try the next critical lane
                
            logger.info(f"Agent found detour for {lane_id}!")
                
            alt_route = alt_path.get("nodes", [])
            alt_lanes = alt_path.get("lanes", [])
            alt_distance = alt_path.get("summary", {}).get("total_distance_km", 0)
            alt_cost = alt_path.get("summary", {}).get("total_co2_teu", 0) * 1000
            orig_cost = target_lane.get("carbon_metrics", {}).get("co2_per_teu", 0) * 1000 # scale up
            
            cost_diff = (alt_cost - orig_cost) * 2.5 # $2.5 per kg CO2 tax
            
            human_cost_str = ""
            if target_camp:
                alt_days_transit = alt_distance / 960.0 # ~40km/h
                days_supply = target_camp.get("current_days_supply", 14)
                deficit = max(0, alt_days_transit - days_supply)
                population = target_camp.get("population", 50000)
                
                if deficit > 0:
                    human_cost_str = f"Cargo arrives in {alt_days_transit:.1f} days, but supply runs out in {days_supply} days, creating a {deficit:.1f}-day deficit for {population} people."
                else:
                    surplus = days_supply - alt_days_transit
                    human_cost_str = f"Cargo arrives in {alt_days_transit:.1f} days, averting a supply deficit with {surplus:.1f} days of buffer remaining for {population} people."

            
            llm = LocalLLMService()
            alt_route_str = " -> ".join(alt_route)
            
            summary_resilience = await llm.generate_mitigation_strategy("blockade", lane_id, 1.0, alt_route_str=alt_route_str, optimization_mode="resilience")
            summary_essential = await llm.generate_mitigation_strategy("blockade", lane_id, 1.0, alt_route_str=alt_route_str, optimization_mode="essential", human_cost_str=human_cost_str)
            
            proposal = {
                "type": "AGENT_PROPOSAL",
                "lane_id": lane_id,
                "alternative_route": alt_route,
                "alternative_lanes": alt_lanes,
                "alternative_distance": alt_distance,
                "cost_impact": round(cost_diff, 2),
                "summary": summary_resilience,
                "summary_essential": summary_essential
            }
            
            # Mark this lane as proposed for 5 minutes so we don't get stuck on it if user ignores it
            await redis_client.setex(lane_cooldown_key, 300, "proposed")
            
            # Publish proposal directly to the stream channel
            message = json.dumps({"agent_proposal": proposal})
            await redis_client.set("simulation:agent:last_proposal", message)
            await redis_client.publish(settings.REDIS_STREAM_CHANNEL, message)
            break # Stop after finding the first viable detour
            
    except Exception as e:
        logger.error(f"Agent failed: {e}")
