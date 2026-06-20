from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.db.postgres import get_db, Shipment, EquipmentEvent, TransportCall

router = APIRouter(prefix="/api/v1/dcsa", tags=["dcsa"])

@router.get("/events", summary="Get equipment events (DCSA standard)")
async def get_events(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Retrieve Track & Trace equipment events."""
    stmt = (
        select(EquipmentEvent)
        .options(selectinload(EquipmentEvent.shipment), selectinload(EquipmentEvent.transport_call))
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()
    
    return [
        {
            "eventClassifierCode": e.event_classifier_code,
            "eventTypeCode": e.event_type_code,
            "equipmentReference": e.equipment_reference,
            "eventDateTime": e.event_date_time.isoformat(),
            "shipment": {
                "carrierBookingReference": e.shipment.carrier_booking_reference,
                "receiptTypeAtOrigin": e.shipment.receipt_type_at_origin,
                "deliveryTypeAtDestination": e.shipment.delivery_type_at_destination,
            },
            "transportCall": {
                "transportCallReference": e.transport_call.transport_call_reference,
                "locationId": e.transport_call.location_id,
            }
        }
        for e in events
    ]

@router.get("/shipments/{carrier_booking_reference}", summary="Get a specific shipment")
async def get_shipment(carrier_booking_reference: str, db: AsyncSession = Depends(get_db)):
    """Retrieve a DCSA shipment by its carrier booking reference."""
    stmt = (
        select(Shipment)
        .where(Shipment.carrier_booking_reference == carrier_booking_reference)
    )
    result = await db.execute(stmt)
    shipment = result.scalar_one_or_none()
    
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
        
    return {
        "carrierBookingReference": shipment.carrier_booking_reference,
        "termsAndConditions": shipment.terms_and_conditions,
        "receiptTypeAtOrigin": shipment.receipt_type_at_origin,
        "deliveryTypeAtDestination": shipment.delivery_type_at_destination,
        "cargoGrossWeight": shipment.cargo_gross_weight
    }
