from typing import Dict, Any
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.cadastre_service import CadastreService
from app.services.ulpin_engine import parse_and_validate_3d_ulpin
from app.services.geometry_normalization import GeometryNormalizationService
from app.services.spatial_engine import (
    compute_projected_spatial_metrics,
    evaluate_building_containment,
)
from app.schemas.common import APIResponse
from app.schemas.spatial import ClashCheckResponse, GeoJSON3DFeatureCollection

router = APIRouter(prefix="/spatial", tags=["3D Spatial Analysis & GeoJSON 3D"])


class ULPIN3DValidationRequest(BaseModel):
    ulpin_3d: str = Field(..., example="14CH78901234AB-L04-U402-K9")


class GeometryNormalizationRequest(BaseModel):
    geometry: Dict[str, Any] = Field(..., description="GeoJSON Polygon or MultiPolygon")
    snap_decimals: int = Field(default=7, ge=3, le=12)


class BuildingContainmentRequest(BaseModel):
    building_geometry: Dict[str, Any] = Field(..., description="Building footprint GeoJSON Polygon")
    parcel_geometry: Dict[str, Any] = Field(..., description="Parent Parcel boundary GeoJSON Polygon")
    tolerance_sqm: float = Field(default=0.05, ge=0.0, description="Tolerance in m²")


@router.get("/clashes/building/{building_id}", response_model=APIResponse[ClashCheckResponse])
def check_building_clashes(building_id: str, db: Session = Depends(get_db)):
    """
    Performs full 3D spatial collision and clash detection between all vertical units in a building.
    Detects volumetric overlap based on projected 2D footprint intersection and vertical elevation overlap.
    """
    report = CadastreService.check_building_clashes(db, building_id)
    return APIResponse(data=ClashCheckResponse(**report))


@router.get("/geojson3d/building/{building_id}", response_model=APIResponse[GeoJSON3DFeatureCollection])
def get_building_3d_geojson(building_id: str, db: Session = Depends(get_db)):
    """
    Exports a 3D GeoJSON FeatureCollection ready for web visualizers (Three.js, Cesium, Mapbox 3D).
    Features include extruded heights, z_min, z_max, volume, and 3D ULPIN attributes.
    """
    geojson_data = CadastreService.get_building_3d_geojson(db, building_id)
    return APIResponse(data=GeoJSON3DFeatureCollection(**geojson_data))


@router.post("/validate-ulpin-3d", response_model=APIResponse[dict])
def validate_3d_ulpin(payload: ULPIN3DValidationRequest):
    """
    Validates the structure and Luhn mod-36 checksum of a 3D ULPIN string.
    Returns parsed components (base_ulpin, level_code, unit_code, checksum).
    """
    parsed = parse_and_validate_3d_ulpin(payload.ulpin_3d)
    return APIResponse(data=parsed)


@router.post("/normalize-geometry", response_model=APIResponse[dict])
def normalize_geometry(payload: GeometryNormalizationRequest):
    """
    Normalizes a 2D cadastral boundary:
    - Enforces linear ring closure
    - Deduplicates redundant vertices
    - Snaps coordinate precision
    - Orients exterior CCW / interiors CW
    - Computes metric spatial properties (area m², perimeter m, bbox) in local projected UTM CRS
    """
    norm_res = GeometryNormalizationService.normalize_geojson(
        payload.geometry,
        snap_decimals=payload.snap_decimals
    )
    metrics = compute_projected_spatial_metrics(norm_res.geojson)

    data = {
        "is_valid": norm_res.is_valid,
        "was_repaired": norm_res.was_repaired,
        "repair_actions": norm_res.repair_actions,
        "area_change_pct": norm_res.area_change_pct,
        "geometry": norm_res.geojson,
        "metrics": {
            "area_sqm": metrics["area_sqm"],
            "perimeter_m": metrics["perimeter_m"],
            "centroid": [metrics["centroid_lat"], metrics["centroid_lon"]],
            "bbox": metrics["bbox"],
            "projected_crs": metrics["projected_crs"],
            "source_crs": metrics["source_crs"]
        }
    }
    return APIResponse(data=data)


@router.post("/validate-building-containment", response_model=APIResponse[dict])
def validate_building_containment(payload: BuildingContainmentRequest):
    """
    Evaluates building footprint containment within parent cadastral parcel.
    Returns structured status: CONTAINED, PARTIALLY_OUTSIDE, COMPLETELY_OUTSIDE, INVALID_GEOMETRY.
    Calculates exact projected excess area in m² and percentage outside.
    """
    res = evaluate_building_containment(
        payload.building_geometry,
        payload.parcel_geometry,
        tolerance_sqm=payload.tolerance_sqm
    )
    return APIResponse(data=res)
