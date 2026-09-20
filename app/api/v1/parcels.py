from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.cadastre_service import CadastreService
from app.schemas.common import APIResponse, PaginatedList
from app.schemas.parcel import ParcelCreate, ParcelRead, ParcelUpdate

router = APIRouter(prefix="/parcels", tags=["2D Cadastral Parcels"])


@router.post("/", response_model=APIResponse[ParcelRead], status_code=status.HTTP_201_CREATED)
def create_parcel(payload: ParcelCreate, db: Session = Depends(get_db)):
    """
    Creates a new 2D cadastral land parcel.
    Automatically generates 14-character 2D ULPIN (Bhu-Aadhaar) and computes surface area and centroid.
    """
    parcel = CadastreService.create_parcel(db, payload)
    return APIResponse(data=ParcelRead.model_validate(parcel))


@router.get("/", response_model=APIResponse[PaginatedList[ParcelRead]])
def list_parcels(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists land parcels with pagination."""
    skip = (page - 1) * page_size
    parcels, total = CadastreService.list_parcels(db, skip=skip, limit=page_size)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return APIResponse(
        data=PaginatedList[ParcelRead](
            items=[ParcelRead.model_validate(p) for p in parcels],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    )


@router.get("/{parcel_id}", response_model=APIResponse[ParcelRead])
def get_parcel(parcel_id: str, db: Session = Depends(get_db)):
    """Retrieves land parcel by internal UUID."""
    parcel = CadastreService.get_parcel(db, parcel_id)
    return APIResponse(data=ParcelRead.model_validate(parcel))


@router.get("/ulpin/{ulpin}", response_model=APIResponse[ParcelRead])
def get_parcel_by_ulpin(ulpin: str, db: Session = Depends(get_db)):
    """Retrieves land parcel by 14-character 2D ULPIN (Bhu-Aadhaar)."""
    parcel = CadastreService.get_parcel_by_ulpin(db, ulpin)
    return APIResponse(data=ParcelRead.model_validate(parcel))


@router.put("/{parcel_id}", response_model=APIResponse[ParcelRead])
def update_parcel(parcel_id: str, payload: ParcelUpdate, db: Session = Depends(get_db)):
    """Updates land parcel details and recomputes geometry/area if modified."""
    parcel = CadastreService.update_parcel(db, parcel_id, payload)
    return APIResponse(data=ParcelRead.model_validate(parcel))


@router.delete("/{parcel_id}", response_model=APIResponse[dict])
def delete_parcel(parcel_id: str, db: Session = Depends(get_db)):
    """Deletes land parcel and cascading associated buildings/units."""
    CadastreService.delete_parcel(db, parcel_id)
    return APIResponse(data={"deleted": True, "id": parcel_id})


@router.get("/{parcel_id}/digital-twin", response_model=APIResponse[dict])
def get_parcel_digital_twin(parcel_id: str, db: Session = Depends(get_db)):
    """
    Assembles the complete 3D Cadastral Digital Twin for the parcel:
    Parcel -> Buildings (with computed volume) -> Floors -> Units -> Ownership -> Validation Summary.
    """
    dt = CadastreService.get_parcel_digital_twin(db, parcel_id)
    return APIResponse(data=dt.model_dump())


@router.get("/{parcel_id}/digital-twin/geojson3d", response_model=APIResponse[dict])
def get_parcel_digital_twin_3d_geojson(parcel_id: str, db: Session = Depends(get_db)):
    """
    Exports a multi-layered 3D GeoJSON FeatureCollection for the entire parcel digital twin:
    Contains Parcel boundaries, Building envelopes, Floor strata, and 3D Units ready for web visualizers.
    """
    geojson_data = CadastreService.get_parcel_digital_twin_3d_geojson(db, parcel_id)
    return APIResponse(data=geojson_data)
