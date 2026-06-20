import datetime
from typing import AsyncGenerator
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, relationship

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.postgres_url, echo=False, pool_pre_ping=True, pool_size=20, max_overflow=10)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="operator")  # admin, operator, viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    api_keys = relationship("ApiKey", back_populates="owner", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="api_keys")


# ── DCSA Track & Trace Models ────────────────────────────────────────────────
class Shipment(Base):
    """Represents a carrier booking / shipment (DCSA standard)."""
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    carrier_booking_reference = Column(String(50), unique=True, index=True, nullable=False)
    terms_and_conditions = Column(String(255), nullable=True)
    receipt_type_at_origin = Column(String(10), nullable=True) # CY, SD, CFS
    delivery_type_at_destination = Column(String(10), nullable=True) # CY, SD, CFS
    cargo_gross_weight = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    equipment_events = relationship("EquipmentEvent", back_populates="shipment", cascade="all, delete-orphan")


class TransportCall(Base):
    """Represents a vessel calling at a specific port (DCSA standard)."""
    __tablename__ = "transport_calls"

    id = Column(Integer, primary_key=True, index=True)
    transport_call_reference = Column(String(50), unique=True, index=True, nullable=False)
    carrier_service_code = Column(String(10), nullable=True)
    vessel_imo_number = Column(String(10), nullable=True)
    location_id = Column(String(50), index=True) # UN/LOCODE (e.g., SGSIN)
    facility_code = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    equipment_events = relationship("EquipmentEvent", back_populates="transport_call", cascade="all, delete-orphan")


class EquipmentEvent(Base):
    """Represents a container event (e.g., loaded, discharged, gate-in)."""
    __tablename__ = "equipment_events"

    id = Column(Integer, primary_key=True, index=True)
    event_classifier_code = Column(String(3), nullable=False) # PLT, ACT, EST (Planned, Actual, Estimated)
    event_type_code = Column(String(4), nullable=False) # RECE, LOAD, DEPA, ARRI, DISC, GTOT
    equipment_reference = Column(String(20), index=True, nullable=False) # Container number
    event_date_time = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    transport_call_id = Column(Integer, ForeignKey("transport_calls.id"), nullable=False)

    shipment = relationship("Shipment", back_populates="equipment_events")
    transport_call = relationship("TransportCall", back_populates="equipment_events")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_postgres_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
