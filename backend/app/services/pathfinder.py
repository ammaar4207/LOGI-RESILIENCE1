"""Pathfinder service — A* and Yen's k-shortest paths with haversine heuristics and caching."""
import heapq
import math
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services.analytics import NGO_CAMPS

logger = logging.getLogger(__name__)

# Result cache for pathfinding results (TTL: 3.0 seconds)
_PATH_CACHE = {}
_CACHE_TTL = 3.0

def safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def haversine_distance(coord1: List[float], coord2: List[float]) -> float:
    """Computes the haversine distance in km between two nodes [lon, lat]."""
    lon1, lat1 = coord1
    lon2, lat2 = coord2
    R = 6371.0  # Earth radius in km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def _get_heuristic(curr: str, target: str, node_coords: Dict[str, List[float]], mode: str) -> float:
    if curr not in node_coords or target not in node_coords:
        return 0.0
    dist_km = haversine_distance(node_coords[curr], node_coords[target])
    if mode == "sustainability":
        # Weight is co2_per_teu. Average co2 per km is ~0.02.
        # Use an admissible heuristic (e.g. 0.01 * dist_km) to avoid overestimating.
        return dist_km * 0.010
    elif mode == "financial":
        # Weight is spot_rate per TEU. Average rate per km is ~0.15.
        return dist_km * 0.10
    else:
        # Weight is now dist_km * risk. Base risk is usually >= 0.12.
        # So dist_km * 0.05 is safely admissible.
        return dist_km * 0.05

def _find_astar_path(
    graph: Dict[str, list],
    node_coords: Dict[str, List[float]],
    start: str,
    target: str,
    mode: str,
    avoided_edges: set,
    blocked_nodes: set = None,
) -> Optional[Tuple[float, List[str], List[str]]]:
    if blocked_nodes is None:
        blocked_nodes = set()
    if start in blocked_nodes:
        return None

    h_start = _get_heuristic(start, target, node_coords, mode)
    # Queue stores: (f_score, g_score, curr_node, path_nodes, path_lanes)
    queue = [(h_start, 0.0, start, [start], [])]
    g_scores = {start: 0.0}

    while queue:
        _, g, curr, path, lanes = heapq.heappop(queue)

        if curr == target:
            return g, path, lanes

        if g > g_scores.get(curr, float('inf')):
            continue

        for neighbor, weight, lane_id in graph.get(curr, []):
            if lane_id in avoided_edges or neighbor in blocked_nodes:
                continue
            new_g = g + weight
            if new_g < g_scores.get(neighbor, float('inf')):
                g_scores[neighbor] = new_g
                h = _get_heuristic(neighbor, target, node_coords, mode)
                heapq.heappush(queue, (new_g + h, new_g, neighbor, path + [neighbor], lanes + [lane_id]))

    return None

def _run_yen_k_shortest_paths(
    graph: Dict[str, list],
    node_coords: Dict[str, List[float]],
    start: str,
    target: str,
    mode: str,
    k: int = 3,
    avoided_edges_global: set = None,
    blocked_nodes_global: set = None,
) -> List[Tuple[float, List[str], List[str]]]:
    """Finds up to K shortest paths using Yen's algorithm on top of A* search."""
    if avoided_edges_global is None:
        avoided_edges_global = set()
    if blocked_nodes_global is None:
        blocked_nodes_global = set()
        
    first_path = _find_astar_path(graph, node_coords, start, target, mode, avoided_edges_global, blocked_nodes_global)
    if not first_path:
        return []

    A = [first_path]
    B = []

    for i in range(1, k):
        prev_path_nodes = A[-1][1]
        prev_path_lanes = A[-1][2]
        for j in range(len(prev_path_nodes) - 1):
            spur_node = prev_path_nodes[j]
            root_path_nodes = prev_path_nodes[:j + 1]
            root_path_lanes = prev_path_lanes[:j]

            avoided_edges = set(avoided_edges_global)
            for path_data in A:
                p_nodes = path_data[1]
                p_lanes = path_data[2]
                if len(p_nodes) > j and p_nodes[:j+1] == root_path_nodes:
                    avoided_edges.add(p_lanes[j])

            blocked = set(root_path_nodes[:-1]).union(blocked_nodes_global)
            spur_path_data = _find_astar_path(graph, node_coords, spur_node, target, mode, avoided_edges, blocked)

            if spur_path_data:
                spur_g, spur_nodes, spur_lanes = spur_path_data
                total_nodes = root_path_nodes + spur_nodes[1:]
                total_lanes = root_path_lanes + spur_lanes

                # Calculate total weight (g value)
                total_g = 0.0
                for idx in range(len(total_nodes) - 1):
                    u, v = total_nodes[idx], total_nodes[idx+1]
                    for neighbor, w, l_id in graph.get(u, []):
                        if neighbor == v and l_id == total_lanes[idx]:
                            total_g += w
                            break

                candidate = (total_g, total_nodes, total_lanes)
                if candidate not in B and not any(p[1] == total_nodes for p in A):
                    heapq.heappush(B, candidate)

        if not B:
            break

        shortest_candidate = heapq.heappop(B)
        A.append(shortest_candidate)

    return A

def calculate_dijkstra_path(
    nodes: List[Dict],
    metrics: List[Dict],
    source_id: str,
    target_id: str,
    avoid_edge_id: Optional[str],
    mode: str,
    essential_boost: bool = False,
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Finds the optimal route using A* search (and alternative routes using Yen's algorithm).
    Results are cached using a TTL cache.
    """
    cache_key = (
        tuple(sorted([(n.get("id"), n.get("congestion")) for n in nodes if n.get("id")])),
        tuple(sorted([(m.get("id"), m.get("risk_score")) for m in metrics if m.get("id")])),
        source_id,
        target_id,
        avoid_edge_id,
        mode,
        essential_boost,
    )
    
    # Check cache
    now = time.time()
    if cache_key in _PATH_CACHE:
        val, expiry = _PATH_CACHE[cache_key]
        if now < expiry:
            logger.debug("Pathfinder cache HIT for %s -> %s", source_id, target_id)
            return val
        else:
            del _PATH_CACHE[cache_key]

    src_clean = str(source_id).strip().lower()
    tgt_clean = str(target_id).strip().lower()
    avoid_clean = str(avoid_edge_id).strip().lower() if avoid_edge_id else None

    alias_to_id: Dict[str, str] = {}
    graph: Dict[str, list] = {}
    node_coords: Dict[str, List[float]] = {}
    node_display_names: Dict[str, str] = {}

    for node in nodes:
        if not node.get("id"):
            continue
        node_actual_id = str(node["id"]).strip().lower()
        graph[node_actual_id] = []
        alias_to_id[node_actual_id] = node_actual_id
        display_name = str(node.get("name") or node["id"]).strip()
        node_display_names[node_actual_id] = display_name
        alias_to_id[display_name.lower()] = node_actual_id
        node_coords[node_actual_id] = [
            safe_float(node.get("lon") or node.get("longitude")),
            safe_float(node.get("lat") or node.get("latitude")),
        ]

    resolved_src = alias_to_id.get(src_clean)
    resolved_tgt = alias_to_id.get(tgt_clean)

    if not resolved_src:
        err = f"Origin '{source_id}' not found in graph."
        return None, err
    if not resolved_tgt:
        err = f"Destination '{target_id}' not found in graph."
        return None, err

    if resolved_src == resolved_tgt:
        res = {
            "nodes": [node_display_names.get(resolved_src, resolved_src)],
            "lanes": [],
            "coordinates": [node_coords[resolved_src]],
            "summary": {
                "cost": 0.0,
                "total_distance_km": 0,
                "total_co2_teu": 0,
                "total_cost_usd": 0,
                "avg_risk_score": 0.0,
                "resilience_index": 100,
            },
            "alternatives": []
        }
        _PATH_CACHE[cache_key] = ((res, None), now + _CACHE_TTL)
        return res, None

    edge_metrics_lookup: Dict[str, Dict] = {}
    avoided_edges = set()
    blocked_nodes = set()
    if avoid_clean:
        for item in avoid_clean.split(","):
            item = item.strip()
            if item.startswith("lane_"):
                avoided_edges.add(item)
            else:
                # If it's not a lane, assume it's a node ID to block (e.g. egsuz)
                actual_id = alias_to_id.get(item)
                if actual_id:
                    blocked_nodes.add(actual_id)
                else:
                    blocked_nodes.add(item)

    for lane in metrics:
        if not lane.get("id"):
            continue
        l_id = str(lane["id"]).strip().lower()
        
        # Build index/lookup of edge properties
        lane_src = str(lane.get("source_id", "")).strip().lower()
        lane_dst = str(lane.get("target_id", "")).strip().lower()
        actual_lane_src = alias_to_id.get(lane_src)
        actual_lane_dst = alias_to_id.get(lane_dst)
        if not actual_lane_src or not actual_lane_dst:
            continue

        carbon = lane.get("carbon_metrics") or {"co2_per_teu": 150, "distance_km": 5000}
        dist_km = safe_float(carbon.get("distance_km"), 5000)
        risk = safe_float(lane.get("risk_score"), 0.5)
        essential = safe_float(lane.get("essential_priority"), 0.5)
        spot_rate = safe_float(lane.get("current_spot_rate"), dist_km * 0.15)

        if mode == "sustainability":
            weight = safe_float(carbon.get("co2_per_teu"), 150.0)
        elif mode == "financial":
            weight = spot_rate
        elif mode == "essential":
            # Essential cargo tolerates some risk, but still avoids critical zones
            effective_risk = max(0.05, risk - (essential * 0.3))
            
            # Check if target is an NGO camp and fetch its supply level
            target_camp = next((c for c in NGO_CAMPS if c["port_id"] == target_id.lower()), None)
            days_supply = target_camp.get("current_days_supply", 14) if target_camp else 14
            
            # Base weight is distance * risk
            weight = dist_km * effective_risk
            
            # If days supply is critically low, distance (time) becomes the absolute priority,
            # so we exponentially penalize longer paths to force the algorithm to pick the fastest route.
            if days_supply <= 5:
                urgency_multiplier = (6 - days_supply) ** 2  # e.g. 5 days -> 1x, 3 days -> 9x, 1 day -> 25x penalty
                weight = (dist_km * urgency_multiplier) + (effective_risk * 1000)
            
            if effective_risk >= 0.7:
                weight += 20000.0  # Flat penalty to avoid bias against long safe edges
        else:
            # Standard resilience mode: add massive flat penalty for critical disruptions
            weight = dist_km * risk
            if risk >= 0.7:
                weight += 50000.0  # Massive flat penalty ensures fewest possible disruptions are crossed
            elif risk >= 0.45:
                weight += 10000.0  # Moderate penalty for degraded

        if essential_boost and essential >= 0.85:
            weight *= 0.85  # Boost for essential lanes

        graph[actual_lane_src].append((actual_lane_dst, weight, lane["id"]))
        graph[actual_lane_dst].append((actual_lane_src, weight, lane["id"]))
        edge_metrics_lookup[f"{actual_lane_src}->{actual_lane_dst}"] = lane
        edge_metrics_lookup[f"{actual_lane_dst}->{actual_lane_src}"] = lane

    # 1. Run A* for the primary path
    primary_astar = _find_astar_path(graph, node_coords, resolved_src, resolved_tgt, mode, avoided_edges, blocked_nodes)
    if not primary_astar:
        err = f"No route from '{source_id}' to '{target_id}' with current constraints (mode={mode})."
        return None, err

    cum_weight, new_path_nodes, path_lanes = primary_astar
    
    # Trace details for primary path
    total_co2 = 0.0
    total_distance = 0.0
    total_cost = 0.0
    avg_risk = 0.0
    coordinates = [node_coords[n] for n in new_path_nodes if n in node_coords]
    steps = len(new_path_nodes) - 1

    for i in range(steps):
        u, v = new_path_nodes[i], new_path_nodes[i + 1]
        lane_data = edge_metrics_lookup.get(f"{u}->{v}")
        if lane_data:
            carbon_metrics = lane_data.get("carbon_metrics") or {}
            total_co2 += safe_float(carbon_metrics.get("co2_per_teu"), 150)
            dist_val = safe_float(carbon_metrics.get("distance_km"), 5000)
            total_distance += dist_val
            total_cost += safe_float(lane_data.get("current_spot_rate"), dist_val * 0.15)
            avg_risk += safe_float(lane_data.get("risk_score"), 0.5)

    if steps > 0:
        avg_risk = round(avg_risk / steps, 3)

    resilience_index = int(round((1.0 - min(1.0, avg_risk)) * 100))

    # 2. Run Yen's algorithm for alternative paths (e.g. k=3 alternatives)
    # We pass avoided_edges and blocked_nodes to Yen's to respect them
    yen_paths = _run_yen_k_shortest_paths(graph, node_coords, resolved_src, resolved_tgt, mode, k=3, avoided_edges_global=avoided_edges, blocked_nodes_global=blocked_nodes)
    alternatives = []
    
    for alt_weight, alt_nodes, alt_lanes in yen_paths:
        if alt_nodes == new_path_nodes:
            continue  # Skip primary path
            
        alt_co2 = 0.0
        alt_distance = 0.0
        alt_cost = 0.0
        alt_risk = 0.0
        alt_steps = len(alt_nodes) - 1
        for i in range(alt_steps):
            u, v = alt_nodes[i], alt_nodes[i + 1]
            lane_data = edge_metrics_lookup.get(f"{u}->{v}")
            if lane_data:
                carbon_metrics = lane_data.get("carbon_metrics") or {}
                alt_co2 += safe_float(carbon_metrics.get("co2_per_teu"), 150)
                dist_val = safe_float(carbon_metrics.get("distance_km"), 5000)
                alt_distance += dist_val
                alt_cost += safe_float(lane_data.get("current_spot_rate"), dist_val * 0.15)
                alt_risk += safe_float(lane_data.get("risk_score"), 0.5)
                
        if alt_steps > 0:
            alt_risk = round(alt_risk / alt_steps, 3)
            
        alternatives.append({
            "nodes": [node_display_names.get(n, n) for n in alt_nodes],
            "lanes": alt_lanes,
            "coordinates": [node_coords[n] for n in alt_nodes if n in node_coords],
            "summary": {
                "cost": round(alt_weight, 3),
                "total_distance_km": int(alt_distance),
                "total_co2_teu": int(alt_co2),
                "total_cost_usd": int(alt_cost),
                "avg_risk_score": alt_risk,
                "resilience_index": int(round((1.0 - min(1.0, alt_risk)) * 100)),
            }
        })

    result = {
        "nodes": [node_display_names.get(n, n) for n in new_path_nodes],
        "lanes": path_lanes,
        "coordinates": coordinates,
        "summary": {
            "cost": round(cum_weight, 3),
            "total_distance_km": int(total_distance),
            "total_co2_teu": int(total_co2),
            "total_cost_usd": int(total_cost),
            "avg_risk_score": avg_risk,
            "resilience_index": resilience_index,
        },
        "alternatives": alternatives
    }
    
    result_tuple = (result, None)
    _PATH_CACHE[cache_key] = (result_tuple, now + _CACHE_TTL)
    return result, None
