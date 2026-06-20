"""Simulation event sourcing service.

Every disruption injection, clearance, route simulation, and alert is written
to the Postgres `simulation_events` table as an immutable audit log.
This provides full operational history, compliance audit trails, and feeds
the AlertsTimeline frontend component.
"""
import logging
import datetime
from typing import Any, Dict, Optional
from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import Base

logger = logging.getLogger(__name__)


class SimulationEvent(Base):
    """Immutable audit log of all simulation and alert events."""
    __tablename__ = "simulation_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_type = Column(String(64), index=True, nullable=False)   # disruption_injected | disruption_cleared | route_simulated | alert_fired
    actor = Column(String(128), nullable=True)                     # username from JWT
    target = Column(String(256), nullable=True)                    # port/lane/route ID
    severity = Column(Float, nullable=True)
    details = Column(Text, nullable=True)                          # JSON blob of extra data
    global_resilience = Column(Float, nullable=True)               # snapshot resilience at time of event
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


async def log_event(
    db: AsyncSession,
    event_type: str,
    target: Optional[str] = None,
    actor: Optional[str] = "system",
    severity: Optional[float] = None,
    details: Optional[Dict[str, Any]] = None,
    global_resilience: Optional[float] = None,
) -> None:
    """Write an event to the simulation_events audit table.
    Failures are logged as warnings and never raise — events are best-effort.
    """
    import json
    try:
        event = SimulationEvent(
            event_type=event_type,
            actor=actor,
            target=target,
            severity=severity,
            details=json.dumps(details) if details else None,
            global_resilience=global_resilience,
            created_at=datetime.datetime.utcnow(),
        )
        db.add(event)
        await db.commit()
        logger.debug("Logged event: %s target=%s actor=%s", event_type, target, actor)
    except Exception as exc:
        logger.warning("Failed to log simulation event: %s", exc)
        await db.rollback()


async def get_recent_events(db: AsyncSession, limit: int = 50) -> list:
    """Fetch the most recent simulation events for the AlertsTimeline UI."""
    from sqlalchemy import select, desc
    try:
        result = await db.execute(
            select(SimulationEvent)
            .order_by(desc(SimulationEvent.created_at))
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "actor": r.actor,
                "target": r.target,
                "severity": r.severity,
                "details": r.details,
                "global_resilience": r.global_resilience,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("Failed to fetch simulation events: %s", exc)
        return []
