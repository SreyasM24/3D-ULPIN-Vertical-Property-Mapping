"""
Validation API Router for SIH 26011.
Provides endpoints for deterministic cadastral validation, rule discovery,
report retrieval, and audit history.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import APIResponse
from app.schemas.validation import (
    DigitalTwinValidationReport,
    EntityValidationReport,
    ValidationRuleDefinition,
    ValidationHistoryItem,
)
from app.core.validation_rules import ValidationRuleRegistry
from app.services.cadastral_validator import CadastralValidationService
from app.core.exceptions import EntityNotFoundException

router = APIRouter(prefix="/validation", tags=["Cadastral Validation & Topology Engine"])


@router.get("/rules", response_model=APIResponse[List[ValidationRuleDefinition]])
def list_validation_rules():
    """
    Returns the comprehensive catalog of all active deterministic cadastral validation rules.
    Each rule provides stable rule ID, category, severity, description, and affected entity types.
    """
    rules = ValidationRuleRegistry.list_rules()
    return APIResponse(data=rules)


@router.post("/parcel/{parcel_id}", response_model=APIResponse[DigitalTwinValidationReport])
def validate_parcel(
    parcel_id: str,
    persist: bool = Query(default=True, description="Whether to persist the validation run in audit history"),
    db: Session = Depends(get_db)
):
    """
    Executes comprehensive 2D & 3D cadastral validation for an entire parcel hierarchy:
    Parcel -> Buildings -> Floors -> Units -> 3D Overlap/Clashes -> Explainable Quality Score.
    """
    report = CadastralValidationService.validate_parcel_hierarchy(db, parcel_id, persist=persist)
    return APIResponse(data=report)


@router.post("/building/{building_id}", response_model=APIResponse[EntityValidationReport])
def validate_building(
    building_id: str,
    persist: bool = Query(default=True, description="Whether to persist the validation run in audit history"),
    db: Session = Depends(get_db)
):
    """
    Validates building geometry, footprint containment within parent parcel, and floor strata consistency.
    """
    report = CadastralValidationService.validate_building(db, building_id, persist=persist)
    return APIResponse(data=report)


@router.post("/unit/{unit_id}", response_model=APIResponse[EntityValidationReport])
def validate_unit(
    unit_id: str,
    persist: bool = Query(default=True, description="Whether to persist the validation run in audit history"),
    db: Session = Depends(get_db)
):
    """
    Validates unit geometry, containment in parent floor and building envelope, vertical elevation, and volume.
    """
    report = CadastralValidationService.validate_unit(db, unit_id, persist=persist)
    return APIResponse(data=report)


@router.get("/report/{validation_run_id}", response_model=APIResponse[Dict[str, Any]])
def get_validation_report(validation_run_id: str, db: Session = Depends(get_db)):
    """
    Retrieves a historical validation audit report by its unique validation_run_id.
    """
    report = CadastralValidationService.get_validation_report_by_run_id(db, validation_run_id)
    if not report:
        raise EntityNotFoundException("ValidationRunRecord", validation_run_id)
    return APIResponse(data=report)


@router.get("/history/{entity_id}", response_model=APIResponse[List[ValidationHistoryItem]])
def get_validation_history(
    entity_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Retrieves chronological validation history and quality score trends for an entity.
    """
    records = CadastralValidationService.get_validation_history(db, entity_id, limit=limit)
    items = [
        ValidationHistoryItem(
            id=str(r.id),
            validation_run_id=r.validation_run_id,
            target_entity_type=r.target_entity_type,
            target_entity_id=r.target_entity_id,
            engine_version=r.engine_version,
            is_valid=r.is_valid,
            quality_score=r.quality_score,
            quality_grade=r.quality_grade,
            critical_issues_count=r.critical_issues_count,
            warnings_count=r.warnings_count,
            created_at=r.created_at
        )
        for r in records
    ]
    return APIResponse(data=items)
