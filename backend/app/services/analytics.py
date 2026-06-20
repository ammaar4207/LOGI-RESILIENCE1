import logging
import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import torch

from app.core.config import get_settings
from app.db.neo4j import db
from app.models.gnn import TemporalGraphNetwork
from app.services.scraper import LogisticsDataScraper
from app.services.xai import classify_lane_status, compute_xai_attribution, risk_to_resilience_index

logger = logging.getLogger(__name__)
settings = get_settings()

NGO_CAMPS = [
    {"id": "CAMP_LAX", "name": "FEMA Relief Hub - LA", "lat": 34.0522, "lon": -118.2437, "population": 85000, "base_days_supply": 14, "current_days_supply": 14, "port_id": "uslax"},
    {"id": "CAMP_NYC", "name": "UNICEF Transit Center - NY", "lat": 40.7128, "lon": -74.0060, "population": 120000, "base_days_supply": 12, "current_days_supply": 12, "port_id": "usnyc"},
    {"id": "CAMP_HKG", "name": "Red Cross Regional Depot - HK", "lat": 22.3193, "lon": 114.1694, "population": 250000, "base_days_supply": 7, "current_days_supply": 7, "port_id": "cnhkg"},
    {"id": "CAMP_MNI", "name": "Typhoon Shelter - Manila", "lat": 14.5995, "lon": 120.9842, "population": 150000, "base_days_supply": 4, "current_days_supply": 4, "port_id": "phmni"},
    {"id": "CAMP_VLC", "name": "WFP Mediterranean Hub - Valencia", "lat": 39.4699, "lon": -0.3763, "population": 60000, "base_days_supply": 20, "current_days_supply": 20, "port_id": "esvlc"}
]


def safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


class AnalyticsEngine:
    """Shared GNN inference + metric compilation for API and worker."""

    def __init__(self, redis_client=None):
        self.gnn = TemporalGraphNetwork(in_channels=3, hidden_channels=32, out_channels=1)
        self.scraper = LogisticsDataScraper(redis_client=redis_client)
        self.redis = redis_client
        self._load_checkpoint()

    def _load_checkpoint(self):
        path = settings.MODEL_CHECKPOINT_PATH
        if os.path.exists(path):
            try:
                try:
                    state = torch.load(path, map_location=torch.device("cpu"), weights_only=True)
                except TypeError:
                    state = torch.load(path, map_location=torch.device("cpu"))
                self.gnn.load_state_dict(state)
                logger.info("Loaded GNN checkpoint from %s", path)
            except Exception as exc:
                logger.warning("Checkpoint load failed: %s", exc)
        self.gnn.eval()

    async def run_inference_cycle(self, force: bool = False) -> Dict[str, Any]:
        # Cache check
        now = datetime.now(timezone.utc)
        if not force and hasattr(self, "_cached_inference") and self._cached_inference:
            cache_time, cached_val = self._cached_inference
            if (now - cache_time).total_seconds() < 3.0:
                return cached_val
        if force and hasattr(self, "_cached_inference"):
            self._cached_inference = None

        geo_nodes, sources, targets, edge_meta = await db.get_dynamic_topology()
        num_nodes = len(geo_nodes)

        if num_nodes == 0 or not sources:
            return {
                "status": "DEGRADED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": [],
                "history": [],
                "network_density": {"nodes": 0, "edges": 0},
                "message": "Graph empty — run seed script or check Neo4j.",
            }

        # Fetch active disruptions to overlay on edges
        disruptions = []
        active_detours = {}
        scfi_rates = {}
        if self.redis:
            try:
                disruptions_raw = await self.redis.get("simulation:disruptions")
                if disruptions_raw:
                    disruptions = json.loads(disruptions_raw)
                    
                detours_raw = await self.redis.get("simulation:active_detours")
                if detours_raw:
                    active_detours = json.loads(detours_raw)
                    
                scfi_raw = await self.redis.get("pricing:scfi_latest")
                if scfi_raw:
                    scfi_data = json.loads(scfi_raw)
                    scfi_rates = scfi_data.get("rates", {})
            except Exception as exc:
                logger.warning("Failed to fetch data from Redis for edge compile: %s", exc)

        adj_matrix = torch.eye(num_nodes, dtype=torch.float)
        for s, t in zip(sources, targets):
            if s < num_nodes and t < num_nodes:
                adj_matrix[s][t] = 1.0
                adj_matrix[t][s] = 1.0

        edge_index = torch.stack(
            [
                torch.tensor(sources, dtype=torch.long),
                torch.tensor(targets, dtype=torch.long),
            ],
            dim=0,
        )

        strains = await self.scraper.fetch_environmental_state(geo_nodes)
        
        # --- BUTTERFLY EFFECT: CASCADING SHOCKS ---
        # Inject the disruption shockwave into the base port congestion levels
        # BEFORE running GNN inference. This allows the 2-layer Graph Attention 
        # Network to natively ripple the risk shockwave to neighboring lanes.
        for d in disruptions:
            target_formatted = str(d.get("target", "")).strip().lower().replace("-", "_")
            severity = safe_float(d.get("severity", 0.8))
            if target_formatted.startswith("lane_"):
                parts = target_formatted.split("_")
                if len(parts) == 3:
                    src, tgt = parts[1], parts[2]
                    if src in strains:
                        strains[src]["congestion"] = min(1.0, strains[src]["congestion"] + severity)
                        strains[src]["weather"] = min(1.0, strains[src]["weather"] + (severity * 0.5))
                    if tgt in strains:
                        strains[tgt]["congestion"] = min(1.0, strains[tgt]["congestion"] + severity)
                        strains[tgt]["weather"] = min(1.0, strains[tgt]["weather"] + (severity * 0.5))
            else:
                # It is a port (node) disruption
                nid = target_formatted
                if nid in strains:
                    strains[nid]["congestion"] = min(1.0, strains[nid]["congestion"] + severity)
                    strains[nid]["weather"] = min(1.0, strains[nid]["weather"] + (severity * 0.5))

        features = []
        for node in geo_nodes:
            nid = str(node["id"]).strip().lower()
            s = strains.get(nid, {"weather": 0.2, "congestion": 0.2, "news": 0.2})
            features.append([s["weather"], s["congestion"], s["news"]])

        features_t = torch.tensor(features, dtype=torch.float)

        with torch.no_grad():
            # Initial temporal GRU state can be None for single step inference
            predictions, _ = self.gnn(features_t, edge_index, h_state=None)

        metrics = self._compile_lane_metrics(
            geo_nodes, sources, targets, edge_meta, predictions, strains, disruptions, active_detours, scfi_rates, forecast_days=0
        )

        active_lanes = [m for m in metrics if not m.get("is_detoured")]
        avg_risk = (
            sum(m["risk_score"] for m in active_lanes) / len(active_lanes) if active_lanes else 0.5
        )

        result = {
            "status": "OPERATIONAL",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
            "camps": NGO_CAMPS,  # Live state starts with base camps
            "network_density": {"nodes": num_nodes, "edges": len(metrics)},
            "global_risk": round(avg_risk, 3),
            "global_resilience_index": risk_to_resilience_index(avg_risk),
            "disruptions": disruptions,
        }
        self._cached_inference = (now, result)
        return result

    async def simulate_future_state(self, days: int) -> Dict[str, Any]:
        geo_nodes, sources, targets, edge_meta = await db.get_dynamic_topology()
        num_nodes = len(geo_nodes)
        if num_nodes == 0 or not sources:
            return {}

        disruptions = []
        active_detours = {}
        scfi_rates = {}
        if self.redis:
            try:
                disruptions_raw = await self.redis.get("simulation:disruptions")
                if disruptions_raw:
                    disruptions = json.loads(disruptions_raw)
                    
                detours_raw = await self.redis.get("simulation:active_detours")
                if detours_raw:
                    active_detours = json.loads(detours_raw)
                    
                scfi_raw = await self.redis.get("pricing:scfi_latest")
                if scfi_raw:
                    scfi_data = json.loads(scfi_raw)
                    scfi_rates = scfi_data.get("rates", {})
            except Exception:
                pass

        import copy
        strains = await self.scraper.fetch_environmental_state(geo_nodes)
        strains = copy.deepcopy(strains)
        disruptions = copy.deepcopy(disruptions)
        
        for d in disruptions:
            severity = safe_float(d.get("severity", 0.8))
            decayed = max(0.0, severity - (0.1 * days))
            d["severity"] = decayed
            if d.get("type") == "hurricane" and d.get("lon") is not None:
                d["lon"] -= (1.0 * days)

        for k, s in strains.items():
            s["weather"] = max(0.1, s["weather"] - (0.05 * days))
            s["congestion"] = max(0.1, s["congestion"] - (0.02 * days))

        for d in disruptions:
            target_raw = str(d.get("target", "")).strip().lower()
            target_formatted = target_raw.replace("-", "_")
            severity = safe_float(d.get("severity", 0.8))
            if target_formatted.startswith("lane_") or "-" in target_raw:
                parts = target_formatted.split("_")
                if len(parts) == 3 and parts[0] == "lane":
                    src, tgt = parts[1], parts[2]
                elif len(parts) == 2: # e.g. cnsha_uslax
                    src, tgt = parts[0], parts[1]
                else:
                    src, tgt = None, None
                
                if src and tgt:
                    if src in strains: strains[src]["congestion"] = min(1.0, strains[src]["congestion"] + severity)
                    if tgt in strains: strains[tgt]["congestion"] = min(1.0, strains[tgt]["congestion"] + severity)
            else:
                nid = target_formatted
                if nid in strains: strains[nid]["congestion"] = min(1.0, strains[nid]["congestion"] + severity)

        features = []
        for node in geo_nodes:
            nid = str(node["id"]).strip().lower()
            s = strains.get(nid, {"weather": 0.2, "congestion": 0.2, "news": 0.2})
            features.append([s["weather"], s["congestion"], s["news"]])

        features_t = torch.tensor(features, dtype=torch.float)
        edge_index = torch.stack(
            [torch.tensor(sources, dtype=torch.long), torch.tensor(targets, dtype=torch.long)],
            dim=0,
        )

        with torch.no_grad():
            predictions, _ = self.gnn(features_t, edge_index, h_state=None)

        metrics = self._compile_lane_metrics(
            geo_nodes, sources, targets, edge_meta, predictions, strains, disruptions, active_detours, scfi_rates, forecast_days=days
        )

        active_lanes = [m for m in metrics if not m.get("is_detoured")]
        avg_risk = sum(m["risk_score"] for m in active_lanes) / len(active_lanes) if active_lanes else 0.5

        camps = copy.deepcopy(NGO_CAMPS)
        for camp in camps:
            port_id = camp["port_id"]
            delay_penalty = 0.0
            
            for m in metrics:
                if m.get("target_id", "").lower() == port_id or m.get("source_id", "").lower() == port_id:
                    if m.get("status") == "CRITICAL":
                        delay_penalty = max(delay_penalty, m.get("risk_score", 0.0) * days * 1.5)
                    elif m.get("status") == "WARNING":
                        delay_penalty = max(delay_penalty, m.get("risk_score", 0.0) * days * 0.5)

            total_drain = days + delay_penalty
            camp["current_days_supply"] = max(0.0, round(camp["base_days_supply"] - total_drain, 1))

        return {
            "status": "FORECAST",
            "days_ahead": days,
            "metrics": metrics,
            "camps": camps,
            "global_risk": round(avg_risk, 3),
            "global_resilience_index": risk_to_resilience_index(avg_risk),
            "disruptions": disruptions,
        }

    async def run_and_publish_telemetry(self, force: bool = False) -> Dict[str, Any]:
        payload = await self.run_inference_cycle(force=force)

        # Maintain history in Redis
        history = []
        if self.redis:
            try:
                history_raw = await self.redis.get("simulation:history")
                history = json.loads(history_raw) if history_raw else []
            except Exception as exc:
                logger.warning("Failed to fetch history from Redis: %s", exc)

        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        avg_risk = payload.get("global_risk", 0.5)
        history.append({"t": ts, "avg_risk": avg_risk})
        if len(history) > 60:
            history.pop(0)

        if self.redis:
            try:
                await self.redis.set("simulation:history", json.dumps(history))
            except Exception as exc:
                logger.warning("Failed to save history to Redis: %s", exc)

        payload["history"] = history

        # Broadcast/Publish update to the WebSocket stream
        if self.redis:
            try:
                await self.redis.publish(settings.REDIS_STREAM_CHANNEL, json.dumps(payload))
            except Exception as exc:
                logger.warning("Failed to publish telemetry to Redis stream: %s", exc)

        # Trigger Slack Alerts if resilience is low or if any route is critical
        try:
            from app.services.alerts import check_and_send_alerts
            await check_and_send_alerts(payload, self.redis)
        except Exception as exc:
            logger.warning("Failed to process resilience alerts: %s", exc)

        # Trigger Autonomous LLM Agent
        try:
            from app.services.agent import run_autonomous_agent
            import asyncio
            if not hasattr(self, '_agent_tasks'):
                self._agent_tasks = set()
            print(f"DEBUG_ANALYTICS: Triggering agent with resilience {payload.get('global_resilience_index')}", flush=True)
            task = asyncio.create_task(run_autonomous_agent(payload, self.redis))
            self._agent_tasks.add(task)
            task.add_done_callback(self._agent_tasks.discard)
        except Exception as exc:
            logger.warning("Failed to trigger autonomous agent: %s", exc)

        return payload

    def _compile_lane_metrics(
        self,
        geo_nodes: List[Dict],
        sources: List[int],
        targets: List[int],
        edge_meta: List[Dict],
        predictions: torch.Tensor,
        strains: Dict[str, Dict[str, float]],
        disruptions: List[Dict] = None,
        active_detours: Dict[str, List[str]] = None,
        scfi_rates: Dict[str, int] = None,
        forecast_days: int = 0
    ) -> List[Dict[str, Any]]:
        metrics: List[Dict[str, Any]] = []
        n_preds = predictions.shape[0] if predictions.dim() > 0 else 0
        disruptions = disruptions or []
        active_detours = active_detours or {}
        scfi_rates = scfi_rates or {}

        for idx, meta in enumerate(edge_meta):
            if idx >= len(sources) or idx >= len(targets):
                break
            s_idx, t_idx = sources[idx], targets[idx]
            if s_idx >= len(geo_nodes) or t_idx >= len(geo_nodes):
                continue

            src, tgt = geo_nodes[s_idx], geo_nodes[t_idx]
            try:
                pred_val = float(predictions[idx].item() if idx < n_preds else 0.5)
            except Exception:
                pred_val = safe_float(meta.get("base_risk"), 0.5)

            base = safe_float(meta.get("base_risk"), 0.5)
            
            # --- BUTTERFLY EFFECT: PHYSICS CONSTRAINT ---
            # Retrieve the dynamic strains for the source and target nodes of THIS lane
            src_id = str(geo_nodes[sources[idx]]["id"]).strip().lower()
            tgt_id = str(geo_nodes[targets[idx]]["id"]).strip().lower()
            
            src_congestion = strains.get(src_id, {}).get("congestion", 0.0)
            tgt_congestion = strains.get(tgt_id, {}).get("congestion", 0.0)
            
            # The maximum congestion of either port acts as a shockwave modifier
            c_strain = max(src_congestion, tgt_congestion)
            
            # Integrate the AI prediction, base risk, and the local port congestion shockwave
            risk_val = round(min(1.0, max(0.0, 0.4 * pred_val + 0.4 * base + 0.35 * c_strain)), 3)

            src_id = str(src["id"])
            tgt_id = str(tgt["id"])
            src_strain = strains.get(src_id.strip().lower(), {})
            tgt_strain = strains.get(str(tgt["id"]).strip().lower(), {})
            blend = {
                "weather": (src_strain.get("weather", 0.2) + tgt_strain.get("weather", 0.2)) / 2,
                "congestion": max(
                    src_strain.get("congestion", 0.2),
                    tgt_strain.get("congestion", 0.2),
                ),
                "news": (src_strain.get("news", 0.2) + tgt_strain.get("news", 0.2)) / 2,
            }

            lane_id = meta.get("id") or f"lane_{src_id}_{tgt_id}".lower()
            status = classify_lane_status(risk_val)

            # Apply active lane blockages
            src_lat = safe_float(src.get("lat"))
            src_lon = safe_float(src.get("lon"))
            tgt_lat = safe_float(tgt.get("lat"))
            tgt_lon = safe_float(tgt.get("lon"))
            
            # Approximate midpoint for spatial intersection
            mid_lat = (src_lat + tgt_lat) / 2.0
            diff_lon = abs(src_lon - tgt_lon)
            mid_lon = (src_lon + tgt_lon) / 2.0
            if diff_lon > 180:
                mid_lon = (src_lon + tgt_lon + 360) / 2.0
                if mid_lon > 180:
                    mid_lon -= 360
                    
            import math
            def hav(lon1, lat1, lon2, lat2):
                lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
                a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
                return 6371 * 2 * math.asin(math.sqrt(a))

            storm_severity = 0.0
            for d in disruptions:
                target_raw = str(d.get("target", "")).strip().lower()
                target_formatted = target_raw.replace("-", "_")
                severity = safe_float(d.get("severity", 0.99))
                
                hit = False
                # Direct match
                if (target_formatted == lane_id.strip().lower() or 
                    f"lane_{target_formatted}" == lane_id.strip().lower() or 
                    target_raw == f"{src_id}-{tgt_id}".lower() or 
                    target_formatted == f"{src_id}_{tgt_id}".lower() or 
                    target_raw == src_id.lower() or 
                    target_raw == tgt_id.lower()):
                    hit = True
                else:
                    # Spatial overlap check: Does lane pass through the storm radius?
                    d_lat = d.get("lat")
                    d_lon = d.get("lon")
                    d_rad = safe_float(d.get("radius_km"), 1000.0)
                    
                    if d_lat is not None and d_lon is not None:
                        if hav(src_lon, src_lat, d_lon, d_lat) <= d_rad or hav(tgt_lon, tgt_lat, d_lon, d_lat) <= d_rad or hav(mid_lon, mid_lat, d_lon, d_lat) <= d_rad:
                            hit = True
                
                if hit and severity > 0.01:
                    risk_val = min(1.0, risk_val + severity)
                    storm_severity = max(storm_severity, severity)
                    if risk_val >= 0.7:
                        status = "CRITICAL"
                    elif risk_val >= 0.45:
                        status = "WARNING"

            # --- CONGESTION IDLE PENALTY ---
            # If a lane is experiencing high risk/congestion, ships are forced to idle or detour,
            # massively burning more fuel.
            
            is_detoured = lane_id.strip().lower() in active_detours
            
            base_co2 = safe_float(meta.get("co2_per_teu"), 150)
            if status == "CRITICAL" and not is_detoured:
                # Up to 150% more emissions (2.5x multiplier) in critical states
                adjusted_co2 = base_co2 * (1.0 + (risk_val * 1.5))
            elif status == "WARNING" and not is_detoured:
                # Up to 60% more emissions
                adjusted_co2 = base_co2 * (1.0 + (risk_val * 0.6))
            else:
                adjusted_co2 = base_co2

            distance_km_val = safe_float(meta.get("distance_km"), 10000.0)

            # --- FINANCIAL SPOT RATE ESCALATION ---
            spot_rate = safe_float(scfi_rates.get(lane_id), safe_float(meta.get("base_spot_rate", 1500.0)))
            
            # 1. Congestion Surcharge
            if blend["congestion"] > 0.4:
                spot_rate *= (1.0 + (blend["congestion"] * 0.4))
                
            # 2. Risk Premium Surcharge
            if risk_val > 0.5:
                spot_rate *= (1.0 + (risk_val * 0.8))
                
            # 3. Carbon Tax Liability (EU ETS / IMO 2023 proxy)
            # Factoring in extra emissions from idle/congestion
            carbon_tax = adjusted_co2 * 0.08
            spot_rate += carbon_tax

            # 4. Detour / Blockade Surcharge
            if is_detoured:
                # Flat surcharge for severely impacted lanes forcing detours
                spot_rate += 1500.0
                
            spot_rate = int(spot_rate)
            
            # --- PREDICTIVE PRIORITY ADJUSTMENT ---
            # Even essential routes (priority 0.7) should not display as active crises (Yellow >= 0.7) 
            # when the weather is clear. We clamp the base visual priority to 0.5 (Silver), and only 
            # allow it to spike to Yellow/Red based on ACTIVE storm severity, not residual congestion or base risk.
            base_priority = min(0.5, safe_float(meta.get("essential_priority", 0.5)))
            risk_escalation = storm_severity * 1.5
            priority = min(1.0, base_priority + risk_escalation)
            
            metrics.append(
                {
                    "id": lane_id,
                    "name": f"{src.get('name', src_id)} ➔ {tgt.get('name', tgt_id)}",
                    "source_id": src_id,
                    "target_id": tgt_id,
                    "source_coords": [safe_float(src.get("lon")), safe_float(src.get("lat"))],
                    "target_coords": [safe_float(tgt.get("lon")), safe_float(tgt.get("lat"))],
                    "risk_score": risk_val,
                    "resilience_index": risk_to_resilience_index(risk_val),
                    "status": status,
                    "xai_attribution": compute_xai_attribution(
                        risk_val,
                        blend["weather"],
                        blend["congestion"],
                        blend["news"],
                    ),
                    "carbon_metrics": {
                        "distance_km": distance_km_val,
                        "co2_per_teu": adjusted_co2,
                    },
                    "essential_priority": priority,
                    "congestion": int(round(blend["congestion"] * 100)),
                    "is_detoured": is_detoured,
                    "current_spot_rate": spot_rate,
                }
            )

        return metrics
