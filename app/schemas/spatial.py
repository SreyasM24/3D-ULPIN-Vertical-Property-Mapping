from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.unit import Unit3DFeature


class ClashReportItem(BaseModel):
    unit_a_id: str
    unit_a_ulpin: str
    unit_a_number: str
    unit_b_id: str
    unit_b_ulpin: str
    unit_b_number: str
    overlap_area_sqm: float
    vertical_overlap_m: float
    overlap_volume_cu_m: float
    severity: str = "ERROR"  # "ERROR" for volume overlap, "WARNING" for boundary touch


class ClashCheckResponse(BaseModel):
    building_id: Optional[str] = None
    floor_id: Optional[str] = None
    total_units_checked: int
    has_clashes: bool
    clash_count: int
    clashes: List[ClashReportItem]


class ContainmentValidationItem(BaseModel):
    unit_id: str
    unit_ulpin: str
    is_contained_in_building: bool
    is_contained_in_parcel: bool
    exceeding_area_sqm: float
    message: str


class ContainmentValidationResponse(BaseModel):
    total_checked: int
    all_valid: bool
    violations: List[ContainmentValidationItem]


class GeoJSON3DFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection container carrying 3D spatial properties."""
    type: str = "FeatureCollection"
    features: List[Unit3DFeature]
    metadata: Dict[str, Any] = Field(default_factory=dict)
