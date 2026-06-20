"""LLM service — Mistral-powered AI mitigation strategies with intelligent fallback.

Model Priority Chain (best free quality → fastest):
  1. mistral:7b-instruct  — Best instruction-following, concise logistics reasoning (~4GB)
  2. mistral               — Base Mistral if instruct variant not pulled
  3. llama3                — Meta Llama 3 8B fallback
  4. Expert Rule Engine    — Domain-expert logistics templates (zero-dependency fallback)

The rule-based fallback produces professional-grade responses indistinguishable from
a brief LLM response in logistics context — maintaining full application quality.

To download Mistral on first run:
  docker-compose exec ollama ollama pull mistral:7b-instruct
"""
import logging
import httpx
from typing import Dict, Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Model Priority Chain ────────────────────────────────────────────────────
# mistral:7b-instruct is the best free model for concise instruction-following tasks.
# We auto-detect which model is available and use the best one found.
_MODEL_PRIORITY_CHAIN = [
    settings.OLLAMA_MODEL,  # Configured model (default: mistral:7b-instruct)
    "mistral:7b-instruct",
    "mistral",
    "llama3",
    "llama3.2",
    "gemma2",
]

# Cache the resolved working model so we don't probe on every request
_resolved_model: Optional[str] = None


async def _probe_best_model(base_url: str) -> Optional[str]:
    """
    Queries Ollama for available models and returns the best one from the priority chain.
    Called once on first invocation; result is cached for the session.
    """
    global _resolved_model
    if _resolved_model:
        return _resolved_model
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                available = {m["name"].split(":")[0] for m in resp.json().get("models", [])}
                available_full = {m["name"] for m in resp.json().get("models", [])}
                logger.info("Ollama available models: %s", available_full)
                for candidate in _MODEL_PRIORITY_CHAIN:
                    base = candidate.split(":")[0]
                    if candidate in available_full or base in available:
                        _resolved_model = candidate if candidate in available_full else base
                        logger.info("Selected Ollama model: %s", _resolved_model)
                        return _resolved_model
    except Exception as e:
        logger.debug("Ollama model probe failed: %s", type(e).__name__)
    return None


# ─── Expert Rule-Based Mitigation Engine ─────────────────────────────────────
# Domain-specific strategies keyed by type and severity tier.
# Produces concise, professional 2-sentence responses matching LLM output quality.

_MITIGATION_TEMPLATES: Dict[str, list] = {
    "strike": [
        (0.9, "Immediately reroute all containers scheduled through {target} to the nearest viable alternative "
              "terminal — prioritizing {alt_port} based on current capacity availability and berth window. "
              "Activate pre-negotiated port-omission contracts and issue priority berthing requests to inland "
              "rail hubs to maintain supply chain continuity and minimize consignee impact."),
        (0.6, "Divert {target}-bound vessels to pre-identified contingency ports and engage freight forwarders "
              "to pre-clear customs at alternate inland depots within the next 12 hours. "
              "Notify downstream consignees of an estimated 3–5 day delay and activate buffer stock release "
              "procedures for time-critical commodities."),
        (0.0, "Monitor {target} industrial action closely and implement selective cargo diversion for "
              "high-priority TEUs while maintaining nominal scheduling for standard freight. "
              "Engage port authority liaisons to negotiate priority handling corridors for essential goods."),
    ],
    "hurricane": [
        (0.9, "Issue immediate fleet-wide weather routing advisories to divert all vessels within {radius_km}km "
              "of {target} to the next safe waypoint — recommend {alt_port} or the Cape of Good Hope bypass "
              "for trans-oceanic corridors. "
              "Suspend berthing operations at all affected terminals until sustained winds fall below 35 knots "
              "and activate emergency port-omission clauses with all affected shippers and P&I clubs."),
        (0.6, "Re-route vessels currently within the {radius_km}km storm radius via alternative headings "
              "and delay planned sailings by 48–72 hours pending updated meteorological assessment. "
              "Pre-position emergency response assets at designated shelter ports and notify cargo owners "
              "of potential cargo damage liability exposure and estimated delay window."),
        (0.0, "Monitor the developing weather system near {target} and issue precautionary routing advisories "
              "to vessels within 300km. "
              "Prepare contingency berthing arrangements at alternate ports and advise cargo owners of a "
              "possible 24–48 hour delay window pending storm track confirmation."),
    ],
    "blockade": [
        (0.9, "Execute immediate operational pivot: suspend all transits through {target} and activate the "
              "Cape of Good Hope bypass routing via {alt_port} — accepting the 8–12 day transit extension "
              "as the operationally and commercially secure option. "
              "File force majeure notices with all affected shippers within 4 hours, engage war-risk underwriters, "
              "and pre-book additional tonnage on alternate corridors to absorb demand surge."),
        (0.6, "Divert {target} corridor traffic via the alternative routing matrix and coordinate with freight "
              "charterers on demurrage compensation and force majeure clause activation within 24 hours. "
              "Assess bonded warehousing capacity at origin ports to absorb 5–8 day sailing delays and "
              "brief consignees on revised ETA schedules."),
        (0.0, "Heightened monitoring of {target} corridor; pre-position vessels at approved anchorages pending "
              "diplomatic resolution of the access restriction. "
              "Evaluate risk-adjusted routing alternatives and brief charterers on contingency timelines "
              "and any applicable demurrage exposure."),
    ],
    "custom": [
        (0.9, "Activate emergency logistics response protocol: reroute all critical cargo from {target} via "
              "the most resilient corridor identified by real-time GNN risk scoring — engage {alt_port} as "
              "the primary diversion hub. "
              "Notify all stakeholders within 2 hours, engage insurance underwriters for cargo endorsement "
              "review, and escalate to senior supply chain management for strategic oversight."),
        (0.0, "Initiate enhanced monitoring of {target} and apply dynamic rerouting logic to any shipments "
              "with departure dates within the next 72 hours. "
              "Coordinate with port agencies for updated capacity and berth availability assessments "
              "and prepare contingency plans for escalating disruption scenarios."),
    ],
}

_ALT_PORTS: Dict[str, str] = {
    "SGSIN": "MYPKG / Port Klang",
    "SGSTR": "SGSIN / Singapore",
    "CNSHA": "CNNBO / Ningbo-Zhoushan",
    "CNNBO": "CNSHA / Shanghai",
    "KRPUS": "JPTYO / Yokohama",
    "EGSUZ": "Cape bypass via ZADUR / Durban",
    "NLRTM": "BEANT / Antwerp",
    "DEHAM": "BEANT / Antwerp",
    "BEANT": "NLRTM / Rotterdam",
    "USLAX": "USNYC / New York",
    "USNYC": "USLAX / Los Angeles",
    "AEJEA": "OMSLL / Salalah",
    "OMSLL": "AEJEA / Jebel Ali",
    "INMUN": "LKCMB / Colombo",
    "LKCMB": "INMUN / Mumbai",
    "ZADUR": "NGLOS / Lagos",
    "NGLOS": "ZADUR / Durban",
    "MYPKG": "SGSIN / Singapore",
    "CNHKG": "TWKHH / Kaohsiung",
    "BRSSZ": "USHOH / Houston",
}


def _rule_based_strategy(disruption_type: str, target_node: str, severity: float, radius_km: float = 1000, alt_route_str: str = "", optimization_mode: str = "resilience", human_cost_str: str = "") -> str:
    """
    Generates a professional, domain-accurate mitigation strategy.
    Used as a zero-dependency fallback when Ollama is unavailable.
    """
    dt = disruption_type.lower().strip()
    templates = _MITIGATION_TEMPLATES.get(dt, _MITIGATION_TEMPLATES["custom"])

    selected = templates[-1][1]
    for threshold, template in templates:
        if severity >= threshold:
            selected = template
            break

    alt_port = _ALT_PORTS.get(target_node.upper(), "the nearest viable alternative terminal")
    if alt_route_str:
        selected = selected.replace("Cape of Good Hope bypass routing via {alt_port}", "alternative routing via {alt_route}")
        selected = selected.replace("{alt_port}", "{alt_route}")

    result = selected.format(
        target=target_node,
        alt_port=alt_port,
        alt_route=alt_route_str,
        radius_km=int(radius_km),
        severity_pct=int(severity * 100),
    )
    
    if optimization_mode == "essential":
        # Create a seamlessly integrated response rather than awkwardly appending text
        hc_text = f" ({human_cost_str})" if human_cost_str else ""
        result = (
            f"⚠️ NGO HUMANITARIAN PROTOCOL: Initiate urgent diversion of {target_node} traffic via {alt_port} "
            f"to ensure uninterrupted delivery of critical medical supplies{hc_text}. While this reroute incurs an expedited "
            f"humanitarian freight premium and estimated carbon tax impact, it is the only viable option to bypass "
            f"the disruption, override standard commercial constraints, and meet life-saving delivery timelines."
        )

    return result


# ─── Mistral-Optimized Prompt ─────────────────────────────────────────────────
def _build_mistral_prompt(disruption_type: str, target_node: str, severity: float, alt_route_str: str = "", optimization_mode: str = "resilience", human_cost_str: str = "") -> str:
    """
    Mistral:7b-instruct uses [INST] tags for best instruction-following performance.
    The prompt is tuned for concise, logistics-domain expert responses.
    """
    humanitarian_directive = ""
    if optimization_mode == "essential":
        human_cost_directive = f" Here is the calculated human impact of the delay: '{human_cost_str}' Incorporate this specific deficit into your reasoning." if human_cost_str else ""
        humanitarian_directive = f"This route carries a mix of standard commercial and essential humanitarian cargo. Your strategy must seamlessly integrate commercial advice (e.g. carbon tax impact, underwriters) with NGO Humanitarian aid (e.g. expedited humanitarian freight premium) into a cohesive response that perfectly makes sense. Do not awkwardly stack them.{human_cost_directive} Prefix your response with '⚠️ NGO HUMANITARIAN PROTOCOL: '."


    return (
        f"[INST] You are a senior maritime logistics risk analyst at a global shipping firm.\n"
        f"A disruption has occurred on the global shipping network. Respond with exactly 2 sentences.\n\n"
        f"Disruption Type: {disruption_type}\n"
        f"Affected Port/Corridor: {target_node}\n"
        f"Severity: {int(severity * 100)}%\n"
        f"{f'Proposed Alternative Route: {alt_route_str}' if alt_route_str else ''}\n"
        f"{humanitarian_directive}\n\n"
        f"Provide 2 concise, professional, actionable sentences describing the optimal mitigation strategy. "
        f"Include specific alternative corridors and concrete stakeholder actions. "
        f"Do not include any preamble, explanation, or formatting — just the 2 sentences. [/INST]"
    )


# ─── LLM Service ─────────────────────────────────────────────────────────────
class LocalLLMService:
    """
    AI-powered mitigation strategy generator using Mistral via Ollama.

    Model selection: auto-detects the best available Ollama model using
    the priority chain: mistral:7b-instruct → mistral → llama3 → rule engine.
    Falls back to domain-expert rule engine when no Ollama model is available.
    """

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.timeout = 25.0

    async def generate_mitigation_strategy(
        self,
        disruption_type: str,
        target_node: str,
        severity: float,
        radius_km: float = 1000,
        alt_route_str: str = "",
        optimization_mode: str = "resilience",
        human_cost_str: str = "",
    ) -> str:
        """
        Generates a concise, actionable 2-sentence mitigation strategy using
        Mistral:7b-instruct (best free quality). Falls back gracefully to the
        expert rule engine if Ollama is not running.
        """
        model = await _probe_best_model(self.base_url)

        if model:
            prompt = _build_mistral_prompt(disruption_type, target_node, severity, alt_route_str, optimization_mode, human_cost_str)
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/api/generate",
                        json={"model": model, "prompt": prompt, "stream": False},
                    )
                    response.raise_for_status()
                    result = response.json().get("response", "").strip()
                    if result:
                        logger.info(
                            "Mistral strategy generated via model=%s for %s/%s",
                            model, disruption_type, target_node,
                        )
                        return result
            except Exception as e:
                logger.info(
                    "Ollama call failed (%s: %s) — activating expert rule engine.",
                    type(e).__name__, e,
                )
        else:
            logger.info(
                "No Ollama model available — using expert rule engine for %s/%s.",
                disruption_type, target_node,
            )

        # Expert domain-knowledge fallback — full professional quality maintained
        return _rule_based_strategy(
            disruption_type, target_node, severity, radius_km, alt_route_str, optimization_mode, human_cost_str
        )

    async def generate_shipper_email(self, lane_id: str, alternative_route: list, is_essential: bool = False) -> str:
        """
        Drafts a formal, legally sound "Force Majeure" email to the affected shippers,
        notifying them of the automated pivot. If is_essential is True, crafts a humanitarian notice.
        """
        route_str = " ➔ ".join(alternative_route) if alternative_route else "Unknown"
        model = await _probe_best_model(self.base_url)
        
        if is_essential:
            fallback_email = (
                f"DUAL-MANDATE NOTICE: Commercial & Humanitarian Cargo Re-Routed\n\n"
                f"Dear Shipper,\n\n"
                f"Please be advised that due to a critical disruption affecting {lane_id}, "
                f"we have initiated a dual-mandate mitigation protocol. To ensure supply chain continuity "
                f"and the immediate delivery of life-saving supplies, your cargo has been re-booked onto the following route:\n\n"
                f"{route_str}\n\n"
                f"Our autonomous logistics system has secured this capacity to minimize commercial delays, "
                f"while simultaneously securing premium capacity to bypass constraints for essential humanitarian cargo. "
                f"Force Majeure notices and updated ETAs will be provided shortly.\n\n"
                f"Sincerely,\nLogi-Resilience Operations & Humanitarian Desk"
            )
        else:
            fallback_email = (
                f"Dear Shipper,\n\n"
                f"Please be advised that due to a critical disruption affecting {lane_id}, "
                f"we have declared a Force Majeure event. To ensure supply chain continuity, "
                f"your cargo has been automatically re-booked onto the following alternative route:\n\n"
                f"{route_str}\n\n"
                f"Our autonomous logistics system has secured this capacity to minimize delays. "
                f"Further details and updated ETAs will be provided shortly.\n\n"
                f"Sincerely,\nLogi-Resilience Operations Team"
            )
        
        if model:
            if is_essential:
                prompt = (
                    f"[INST] You are an automated logistics communications system managing a dual-mandate network (commercial + NGO humanitarian).\n"
                    f"Write a formal notice informing shippers that their cargo on {lane_id} was automatically rerouted "
                    f"due to a crisis. The new route is: {route_str}.\n"
                    f"Keep it under 100 words. Seamlessly blend standard commercial force majeure language with the urgency of expediting essential life-saving humanitarian aid. Do not include placeholder text like [Name].\n"
                    f"Just output the email body directly. [/INST]"
                )
            else:
                prompt = (
                    f"[INST] You are an automated logistics communications system.\n"
                    f"Write a formal, professional maritime logistics notice (Force Majeure declaration) "
                    f"informing affected shippers that their cargo on {lane_id} was automatically rerouted "
                    f"due to critical disruptions. The new route is: {route_str}.\n"
                    f"Keep it under 100 words, be polite but firm, and do not include any placeholder text like [Name].\n"
                    f"Just output the email body directly. [/INST]"
                )
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/api/generate",
                        json={"model": model, "prompt": prompt, "stream": False},
                    )
                    response.raise_for_status()
                    result = response.json().get("response", "").strip()
                    if result:
                        return result
            except Exception as e:
                logger.warning(f"Failed to generate shipper email via LLM: {e}")
        
        return fallback_email
