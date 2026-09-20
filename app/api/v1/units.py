from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.cadastre_service import CadastreService
from app.schemas.common import APIResponse, PaginatedList
from app.schemas.unit import UnitCreate, UnitRead, UnitUpdate

router = APIRouter(prefix="/units", tags=["3D Vertical Units & Volumetric Cadastre"])


@router.post("/", response_model=APIResponse[UnitRead], status_code=status.HTTP_201_CREATED)
def create_unit(
    payload: UnitCreate,
    enforce_clash_free: bool = Query(default=True, description="Reject creation if 3D collision detected"),
    db: Session = Depends(get_db)
):
    """
    Creates a 3D Vertical Property Unit (Apartment, Commercial, Utility, Parking).
    - Automatically derives Prototype 3D ULPIN: <base_ulpin>-<level_code>-<unit_code>-<checksum>
    - Computes 3D Volume (m3) and Carpet Area (m2) via projected UTM coordinates
    - Validates 2D containment within building footprint
    - Performs 3D clash/overlap validation against existing units
    """
    unit = CadastreService.create_unit(db, payload, enforce_clash_free=enforce_clash_free)
    return APIResponse(data=UnitRead.model_validate(unit))


@router.get("/", response_model=APIResponse[PaginatedList[UnitRead]])
def list_units(
    parcel_id: Optional[str] = Query(default=None, description="Filter by LandParcel ID"),
    building_id: Optional[str] = Query(default=None, description="Filter by Building ID"),
    floor_id: Optional[str] = Query(default=None, description="Filter by Floor Level ID"),
    unit_type: Optional[str] = Query(default=None, description="Filter by unit type (e.g. APARTMENT, PARKING, UTILITY)"),
    elevation_z: Optional[float] = Query(default=None, description="Filter units intersecting a specific elevation Z (m MSL)"),
    vertical_classification: Optional[str] = Query(default=None, description="Filter by strata: UNDERGROUND, GROUND_LEVEL, ELEVATED"),
    has_clashes: Optional[bool] = Query(default=None, description="Filter units with/without spatial collisions"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Lists 3D vertical units with advanced spatial and cadastral filters:
    - Hierarchical filtering (parcel, building, floor)
    - Volumetric elevation filtering (elevation_z)
    - Vertical strata classification (UNDERGROUND, GROUND_LEVEL, ELEVATED)
    - Validation clash filtering
    """
    skip = (page - 1) * page_size
    units, total = CadastreService.query_units_spatial(
        db,
        parcel_id=parcel_id,
        building_id=building_id,
        floor_id=floor_id,
        unit_type=unit_type,
        elevation_z=elevation_z,
        vertical_classification=vertical_classification,
        has_clashes=has_clashes,
        skip=skip,
        limit=page_size
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return APIResponse(
        data=PaginatedList[UnitRead](
            items=[UnitRead.model_validate(u) for u in units],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    )


@router.get("/spatial-query", response_model=APIResponse[PaginatedList[UnitRead]])
def spatial_query_units(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    min_z: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    max_z: float = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Executes a 3D bounding box volumetric spatial query across all vertical units."""
    skip = (page - 1) * page_size
    bbox_3d = [min_lon, min_lat, min_z, max_lon, max_lat, max_z]
    units, total = CadastreService.query_units_spatial(
        db,
        bbox_3d=bbox_3d,
        skip=skip,
        limit=page_size
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return APIResponse(
        data=PaginatedList[UnitRead](
            items=[UnitRead.model_validate(u) for u in units],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    )


@router.get("/{unit_id}", response_model=APIResponse[UnitRead])
def get_unit(unit_id: str, db: Session = Depends(get_db)):
    """Retrieves 3D unit by internal UUID."""
    unit = CadastreService.get_unit(db, unit_id)
    return APIResponse(data=UnitRead.model_validate(unit))


@router.get("/ulpin/{ulpin_3d}", response_model=APIResponse[UnitRead])
def get_unit_by_ulpin(ulpin_3d: str, db: Session = Depends(get_db)):
    """Retrieves 3D unit by its unique 3D ULPIN string."""
    unit = CadastreService.get_unit_by_ulpin_3d(db, ulpin_3d)
    return APIResponse(data=UnitRead.model_validate(unit))


@router.put("/{unit_id}", response_model=APIResponse[UnitRead])
def update_unit(unit_id: str, payload: UnitUpdate, db: Session = Depends(get_db)):
    """Updates 3D unit properties and recalculates volume/area if bounds/footprint change."""
    unit = CadastreService.update_unit(db, unit_id, payload)
    return APIResponse(data=UnitRead.model_validate(unit))


@router.delete("/{unit_id}", response_model=APIResponse[dict])
def delete_unit(unit_id: str, db: Session = Depends(get_db)):
    """Deletes 3D unit and associated ownership records."""
    CadastreService.delete_unit(db, unit_id)
    return APIResponse(data={"deleted": True, "id": unit_id})


@router.post("/{unit_id}/validate-relationships", response_model=APIResponse[dict])
def validate_unit_relationships(
    unit_id: str,
    allow_multi_floor: bool = Query(default=True, description="Support legitimate multi-floor units (e.g. duplexes, ramps)"),
    db: Session = Depends(get_db)
):
    """
    Rigorously verifies the hierarchical spatial containment of a vertical property unit:
    - Floor contains Unit (with multi-floor span detection)
    - Building contains Unit (horizontal & vertical envelope)
    - Parcel contains Unit (cadastral land boundary)
    """
    result = CadastreService.validate_unit_relationships(
        db, unit_id=unit_id, allow_multi_floor=allow_multi_floor
    )
    return APIResponse(data=result)
