from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.schemas.ownership import OwnershipRead
from app.core.spatial_volume import VerticalClassification


class DigitalTwinUnit(BaseModel):
    id: str
    floor_id: str
    unit_number: str
    unit_code: str
    unit_type: str
    ulpin_3d: str
    ulpin_status: str
    vertical_classification: str
    z_min: float
    z_max: float
    height_m: float
    carpet_area_sqm: float
    volume_cu_m: float
    is_clash_free: bool
    status: str
    footprint_geojson: Dict[str, Any]
    stage: str = "VALIDATED"  # OBSERVED, ESTIMATED, DERIVED, VALIDATED
    confidence: Optional[float] = None
    ml_provenance: Optional[Dict[str, Any]] = None
    ownership_records: List[OwnershipRead] = Field(default_factory=list)


class DigitalTwinFloor(BaseModel):
    id: str
    building_id: str
    level_number: int
    level_code: str
    level_type: str
    z_min: float
    z_max: float
    floor_height_m: float
    stage: str = "VALIDATED"
    unit_count: int
    units: List[DigitalTwinUnit] = Field(default_factory=list)


class DigitalTwinBuilding(BaseModel):
    id: str
    parcel_id: str
    building_name: str
    building_code: str
    structure_type: str
    ground_elevation_m: float
    total_height_m: float
    top_elevation_m: float
    footprint_area_sqm: float
    volume_cu_m: float
    footprint_geojson: Dict[str, Any]
    stage: str = "VALIDATED"  # OBSERVED, ESTIMATED, DERIVED, VALIDATED
    confidence: Optional[float] = None
    ml_provenance: Optional[Dict[str, Any]] = None
    estimated_features: Optional[Dict[str, Any]] = None
    floors: List[DigitalTwinFloor] = Field(default_factory=list)


class DigitalTwinParcel(BaseModel):
    id: str
    ulpin: str
    state_code: str
    district_code: str
    village_code: str
    survey_number: str
    area_sqm: float
    centroid: List[float]
    base_elevation_m: float
    geometry_geojson: Dict[str, Any]
    stage: str = "VALIDATED"
    buildings: List[DigitalTwinBuilding] = Field(default_factory=list)


class DigitalTwinSummary(BaseModel):
    total_buildings: int
    total_floors: int
    total_units: int
    total_volume_cu_m: float
    total_carpet_area_sqm: float
    vertical_breakdown: Dict[str, int]
    clashes_detected: int
    overall_status: str
    data_stages: Dict[str, int] = Field(default_factory=lambda: {"VALIDATED": 1})
    anomalies_detected: List[Dict[str, Any]] = Field(default_factory=list)


class CadastralDigitalTwin(BaseModel):
    """
    Unified 3D Cadastral Digital Twin payload.
    Assembles Parcel -> Buildings -> Floors -> Units -> Ownership -> Validation Status.
    """
    parcel: DigitalTwinParcel
    summary: DigitalTwinSummary
    assembled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
