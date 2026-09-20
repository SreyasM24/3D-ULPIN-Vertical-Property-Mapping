from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.cadastre_service import CadastreService
from app.schemas.common import APIResponse, PaginatedList
from app.schemas.floor import FloorCreate, FloorRead, FloorUpdate

router = APIRouter(prefix="/floors", tags=["Floor Levels & Strata"])


@router.post("/", response_model=APIResponse[FloorRead], status_code=status.HTTP_201_CREATED)
def create_floor(payload: FloorCreate, db: Session = Depends(get_db)):
    """
    Creates a floor level within a building.
    Enforces vertical elevation consistency (z_min, z_max) and calculates floor height.
    """
    floor = CadastreService.create_floor(db, payload)
    return APIResponse(data=FloorRead.model_validate(floor))


@router.get("/", response_model=APIResponse[PaginatedList[FloorRead]])
def list_floors(
    building_id: Optional[str] = Query(default=None, description="Filter by parent Building ID"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists floor levels with optional building filter and pagination."""
    skip = (page - 1) * page_size
    floors, total = CadastreService.list_floors(db, building_id=building_id, skip=skip, limit=page_size)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return APIResponse(
        data=PaginatedList[FloorRead](
            items=[FloorRead.model_validate(f) for f in floors],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    )


@router.get("/{floor_id}", response_model=APIResponse[FloorRead])
def get_floor(floor_id: str, db: Session = Depends(get_db)):
    """Retrieves floor level by UUID."""
    floor = CadastreService.get_floor(db, floor_id)
    return APIResponse(data=FloorRead.model_validate(floor))


@router.put("/{floor_id}", response_model=APIResponse[FloorRead])
def update_floor(floor_id: str, payload: FloorUpdate, db: Session = Depends(get_db)):
    """Updates floor level attributes."""
    floor = CadastreService.update_floor(db, floor_id, payload)
    return APIResponse(data=FloorRead.model_validate(floor))


@router.delete("/{floor_id}", response_model=APIResponse[dict])
def delete_floor(floor_id: str, db: Session = Depends(get_db)):
    """Deletes floor level and child units."""
    CadastreService.delete_floor(db, floor_id)
    return APIResponse(data={"deleted": True, "id": floor_id})


@router.post("/validate-building-floors/{building_id}", response_model=APIResponse[dict])
def validate_building_floors(building_id: str, db: Session = Depends(get_db)):
    """
    Validates the vertical elevation consistency of all floor levels within a building:
    - Checks for invalid/overlapping vertical intervals between floor strata
    - Verifies basement levels are below ground reference
    - Verifies elevated levels are above ground reference
    - Ensures top floor does not exceed permissible building height
    """
    report = CadastreService.validate_building_floor_strata(db, building_id)
    return APIResponse(data=report)
