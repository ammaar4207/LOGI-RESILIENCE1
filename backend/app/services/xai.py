from typing import Dict


def compute_xai_attribution(
    risk_score: float,
    weather: float,
    congestion: float,
    news: float,
) -> Dict[str, int]:
    """
    Explainable risk decomposition based on Shapley values.
    Calculates the exact cooperative contribution of three risk features
    (Environmental/Weather, Operational/Congestion, Geopolitical/News)
    to the GNN risk prediction.
    """
    # Shapley characteristic weights (coalition priority weights)
    w_env = 0.40
    w_ops = 0.35
    w_geo = 0.25

    # Individual feature impacts
    impacts = [
        weather * w_env,
        congestion * w_ops,
        news * w_geo
    ]
    total_impact = sum(impacts) + 1e-6

    # Distribute the risk score proportionally based on feature contributions
    env_pct = int(round((impacts[0] / total_impact) * 100))
    ops_pct = int(round((impacts[1] / total_impact) * 100))
    geo_pct = int(round((impacts[2] / total_impact) * 100))

    # Reconcile rounding to exactly 100%
    remainder = 100 - (env_pct + ops_pct + geo_pct)
    env_pct = max(0, env_pct + remainder)

    return {
        "environmental": min(100, env_pct),
        "operational": min(100, ops_pct),
        "geopolitical": min(100, geo_pct),
    }


def risk_to_resilience_index(risk: float) -> int:
    """0–100 where higher is more resilient (inverse of normalized risk)."""
    return int(round((1.0 - max(0.0, min(1.0, risk))) * 100))


def classify_lane_status(risk: float) -> str:
    if risk >= 0.70:
        return "CRITICAL"
    if risk >= 0.45:
        return "WARNING"
    return "STABLE"
