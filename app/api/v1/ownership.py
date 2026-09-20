from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.ownership_service import OwnershipService
from app.schemas.common import APIResponse, PaginatedList
from app.schemas.ownership import OwnershipCreate, OwnershipRead, OwnershipUpdate

router = APIRouter(prefix="/ownership", tags=["Record of Rights (RoR) & Ownership"])


@router.post("/", response_model=APIResponse[OwnershipRead], status_code=status.HTTP_201_CREATED)
def register_ownership(payload: OwnershipCreate, db: Session = Depends(get_db)):
    """
    Registers an ownership title record (Record of Rights) for a 3D Vertical Property Unit.
    - Anonymizes / hashes personal identification number for privacy protection.
    - Validates that total ownership share across unit owners does not exceed 100%.
    """
    record = OwnershipService.create_ownership(db, payload)
    return APIResponse(data=OwnershipRead.model_validate(record))


@router.get("/", response_model=APIResponse[PaginatedList[OwnershipRead]])
def list_ownership_records(
    unit_id: Optional[str] = Query(default=None, description="Filter by target 3D Vertical Unit ID"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists ownership records with optional unit filter and pagination."""
    skip = (page - 1) * page_size
    records, total = OwnershipService.list_ownerships(db, unit_id=unit_id, skip=skip, limit=page_size)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return APIResponse(
        data=PaginatedList[OwnershipRead](
            items=[OwnershipRead.model_validate(r) for r in records],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    )


@router.get("/{record_id}", response_model=APIResponse[OwnershipRead])
def get_ownership_record(record_id: str, db: Session = Depends(get_db)):
    """Retrieves an ownership record by UUID."""
    record = OwnershipService.get_ownership(db, record_id)
    return APIResponse(data=OwnershipRead.model_validate(record))


@router.put("/{record_id}", response_model=APIResponse[OwnershipRead])
def update_ownership_record(record_id: str, payload: OwnershipUpdate, db: Session = Depends(get_db)):
    """Updates ownership details or status (e.g. mortgage encumbrance release, transfer)."""
    record = OwnershipService.update_ownership(db, record_id, payload)
    return APIResponse(data=OwnershipRead.model_validate(record))


@router.delete("/{record_id}", response_model=APIResponse[dict])
def delete_ownership_record(record_id: str, db: Session = Depends(get_db)):
    """Deletes an ownership record."""
    OwnershipService.delete_ownership(db, record_id)
    return APIResponse(data={"deleted": True, "id": record_id})
