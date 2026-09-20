from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.cadastre_service import CadastreService
from app.schemas.common import APIResponse, PaginatedList
from app.schemas.building import BuildingCreate, BuildingRead, BuildingUpdate

router = APIRouter(prefix="/buildings", tags=["Buildings & Structures"])


@router.post("/", response_model=APIResponse[BuildingRead], status_code=status.HTTP_201_CREATED)
def create_building(payload: BuildingCreate, db: Session = Depends(get_db)):
    """
    Registers a building structure on a land parcel.
    Validates that the building footprint is topologically contained within the parcel boundary.
    """
    building = CadastreService.create_building(db, payload)
    return APIResponse(data=BuildingRead.model_validate(building))


@router.get("/", response_model=APIResponse[PaginatedList[BuildingRead]])
def list_buildings(
    parcel_id: Optional[str] = Query(default=None, description="Filter by parent Parcel ID"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists buildings with optional parcel filter and pagination."""
    skip = (page - 1) * page_size
    buildings, total = CadastreService.list_buildings(db, parcel_id=parcel_id, skip=skip, limit=page_size)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return APIResponse(
        data=PaginatedList[BuildingRead](
            items=[BuildingRead.model_validate(b) for b in buildings],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    )


@router.get("/{building_id}", response_model=APIResponse[BuildingRead])
def get_building(building_id: str, db: Session = Depends(get_db)):
    """Retrieves building by UUID."""
    building = CadastreService.get_building(db, building_id)
    return APIResponse(data=BuildingRead.model_validate(building))


@router.put("/{building_id}", response_model=APIResponse[BuildingRead])
def update_building(building_id: str, payload: BuildingUpdate, db: Session = Depends(get_db)):
    """Updates building attributes and re-verifies spatial containment if footprint is altered."""
    building = CadastreService.update_building(db, building_id, payload)
    return APIResponse(data=BuildingRead.model_validate(building))


@router.delete("/{building_id}", response_model=APIResponse[dict])
def delete_building(building_id: str, db: Session = Depends(get_db)):
    """Deletes building and cascading floors/units."""
    CadastreService.delete_building(db, building_id)
    return APIResponse(data={"deleted": True, "id": building_id})
