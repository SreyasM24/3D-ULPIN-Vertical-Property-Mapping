"""
API Router for Temporal 3D Change & Cadastral Property Intelligence.
SIH 26011 - 3D ULPIN & Vertical Property Mapping System.

Provides endpoints to compare baseline digital twin snapshots against
new surveys, LiDAR/DSM observations, or AI proposals.
"""

from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import APIResponse
from app.schemas.temporal_change import (
    DigitalTwinSnapshot,
    TemporalComparisonConfig,
    TemporalChangeReport,
    TemporalCompareRequest,
)
from app.services.temporal_change_service import TemporalChangeService
from app.core.exceptions import CadastreException

router = APIRouter(prefix="/digital-twin", tags=["3D Digital Twin Temporal Change"])


@router.get("/parcels/{parcel_id}/snapshot", response_model=APIResponse[DigitalTwinSnapshot])
def get_parcel_snapshot(parcel_id: str, db: Session = Depends(get_db)):
    """
    Generates an authoritative baseline snapshot of the registered parcel's 3D Digital Twin.
    Contains stable entity IDs, 3D footprints, elevations, floors, and vertical units.
    """
    snapshot = TemporalChangeService.create_snapshot_from_parcel(db, parcel_id)
    return APIResponse(data=snapshot)


@router.post("/compare", response_model=APIResponse[TemporalChangeReport])
def compare_digital_twins(payload: TemporalCompareRequest, db: Session = Depends(get_db)):
    """
    Executes an end-to-end temporal change comparison between a registered baseline
    (or explicit baseline snapshot) and a newly observed 3D survey / AI extraction.

    Outputs classified ChangeEvents (OBSERVED, AI-ESTIMATED, DETERMINISTIC, TEST_FIXTURE),
    IoU displacement, height delta, vertical floor/unit delta, and a calibrated TECHNICAL_CHANGE_SCORE.
    """
    if payload.baseline_snapshot is not None:
        baseline = payload.baseline_snapshot
    elif payload.parcel_id:
        baseline = TemporalChangeService.create_snapshot_from_parcel(db, payload.parcel_id)
    else:
        raise CadastreException(
            message="Either 'parcel_id' or 'baseline_snapshot' must be provided to establish a baseline.",
            code="MISSING_BASELINE"
        )

    if payload.new_observation is None:
        raise CadastreException(
            message="'new_observation' snapshot must be provided for comparison.",
            code="MISSING_OBSERVATION"
        )

    report = TemporalChangeService.compare_digital_twins(
        baseline=baseline,
        observation=payload.new_observation,
        config=payload.config
    )
    return APIResponse(data=report)


@router.post("/parcels/{parcel_id}/compare", response_model=APIResponse[TemporalChangeReport])
def compare_parcel_with_observation(
    parcel_id: str,
    observation: DigitalTwinSnapshot,
    config: Optional[TemporalComparisonConfig] = None,
    db: Session = Depends(get_db)
):
    """
    Convenience endpoint: Compares a registered parcel's Digital Twin baseline
    directly against an incoming observation snapshot.
    """
    baseline = TemporalChangeService.create_snapshot_from_parcel(db, parcel_id)
    report = TemporalChangeService.compare_digital_twins(
        baseline=baseline,
        observation=observation,
        config=config
    )
    return APIResponse(data=report)
