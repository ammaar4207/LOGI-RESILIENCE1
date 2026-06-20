"""Carbon emissions analytics service.

Computes fleet-wide CO2 metrics, per-lane carbon budgets, and green route recommendations
for the CarbonDashboard frontend component.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# IPCC Scope 3 shipping baseline: 161g CO2 per tonne-km (HFO vessels)
# IMO 2030 target: 40% reduction from 2008 baseline → ~97g CO2/tonne-km
BASELINE_CO2_PER_TEU_KM = 0.060  # kg CO2 / TEU / km
IMO_2030_TARGET_CO2_PER_TEU_KM = 0.025
EU_ETS_PRICE_PER_TONNE = 65.0  # EUR, approximate 2024 price


def compute_carbon_analytics(metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes comprehensive carbon footprint analytics for the entire shipping network.

    Returns:
        - total_co2_teu: Total kg CO2 per TEU across all active lanes
        - avg_co2_per_km: Average carbon intensity per TEU-km
        - eco_score: 0–100 score (100 = fully IMO 2030 compliant)
        - worst_lanes: Top 5 highest-carbon corridors
        - best_lanes: Top 5 lowest-carbon corridors
        - ets_cost_estimate: Estimated EU ETS carbon cost per TEU (EUR)
        - emissions_vs_baseline: % difference from IPCC baseline
        - scope3_breakdown: Proportional breakdown by trade corridor type
    """
    if not metrics:
        return _empty_carbon_response()

    lane_carbon: List[Dict[str, Any]] = []
    total_co2 = 0.0
    total_distance = 0.0
    total_lanes = len(metrics)

    for lane in metrics:
        carbon = lane.get("carbon_metrics") or {}
        dist_km = float(carbon.get("distance_km") or 5000)
        co2_teu = float(carbon.get("co2_per_teu") or 150)
        co2_per_km = co2_teu / max(dist_km, 1)

        total_co2 += co2_teu
        total_distance += dist_km

        lane_carbon.append({
            "id": lane.get("id"),
            "name": lane.get("name"),
            "co2_per_teu": round(co2_teu, 1),
            "distance_km": int(dist_km),
            "co2_per_km": round(co2_per_km * 1000, 2),  # g CO2/TEU/km
            "risk_score": lane.get("risk_score", 0.5),
            "is_eco": co2_teu < 120,  # Below IMO eco-threshold
        })

    avg_co2 = total_co2 / max(total_lanes, 1)
    avg_co2_per_km = total_co2 / max(total_distance, 1) * 1000  # g/TEU/km

    # Eco score: 100 = meeting IMO 2030, 0 = baseline or worse
    imo_target_total = IMO_2030_TARGET_CO2_PER_TEU_KM * (total_distance / max(total_lanes, 1)) if total_lanes > 0 else 100
    baseline_total = BASELINE_CO2_PER_TEU_KM * (total_distance / max(total_lanes, 1)) if total_lanes > 0 else 175
    eco_score = max(0, min(100, int(
        100 * (1 - (avg_co2 - imo_target_total) / max(baseline_total - imo_target_total, 1))
    )))

    # EU ETS cost: convert kg → tonnes
    ets_cost = round((avg_co2 / 1000) * EU_ETS_PRICE_PER_TONNE, 2)

    # Vs baseline
    baseline_avg = BASELINE_CO2_PER_TEU_KM * (total_distance / max(total_lanes, 1))
    vs_baseline_pct = round((avg_co2 - baseline_avg) / max(baseline_avg, 1) * 100, 1)

    sorted_by_co2 = sorted(lane_carbon, key=lambda x: x["co2_per_teu"])
    best_lanes = sorted_by_co2[:5]
    worst_lanes = sorted_by_co2[-5:][::-1]

    # Scope 3 corridor type breakdown (proportional estimate)
    short_haul = [l for l in lane_carbon if l["distance_km"] < 3000]
    medium_haul = [l for l in lane_carbon if 3000 <= l["distance_km"] < 8000]
    long_haul = [l for l in lane_carbon if l["distance_km"] >= 8000]

    scope3 = {
        "short_haul_pct": _pct(len(short_haul), total_lanes),
        "medium_haul_pct": _pct(len(medium_haul), total_lanes),
        "long_haul_pct": _pct(len(long_haul), total_lanes),
    }

    return {
        "total_co2_teu": round(total_co2, 1),
        "avg_co2_per_lane": round(avg_co2, 1),
        "avg_co2_per_km_g": round(avg_co2_per_km, 2),
        "eco_score": eco_score,
        "ets_cost_eur_per_teu": ets_cost,
        "emissions_vs_baseline_pct": vs_baseline_pct,
        "imo_2030_target_co2": round(imo_target_total, 1),
        "eco_lanes_count": len([l for l in lane_carbon if l["is_eco"]]),
        "total_lanes": total_lanes,
        "worst_lanes": worst_lanes,
        "best_lanes": best_lanes,
        "scope3_breakdown": scope3,
        "lane_details": lane_carbon,
    }


def _pct(n: int, total: int) -> int:
    return int(round(n / max(total, 1) * 100))


def _empty_carbon_response() -> Dict[str, Any]:
    return {
        "total_co2_teu": 0,
        "avg_co2_per_lane": 0,
        "avg_co2_per_km_g": 0,
        "eco_score": 0,
        "ets_cost_eur_per_teu": 0,
        "emissions_vs_baseline_pct": 0,
        "imo_2030_target_co2": 0,
        "eco_lanes_count": 0,
        "total_lanes": 0,
        "worst_lanes": [],
        "best_lanes": [],
        "scope3_breakdown": {"short_haul_pct": 0, "medium_haul_pct": 0, "long_haul_pct": 0},
        "lane_details": [],
    }
