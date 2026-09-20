from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from app.schemas.parcel import GeoJSONPolygon


class UnitBase(BaseModel):
    unit_number: str = Field(..., max_length=50, example="Flat 302")
    unit_code: str = Field(..., max_length=30, example="U302")
    unit_type: str = Field(default="APARTMENT", example="APARTMENT")
    z_min: float = Field(..., description="Bottom elevation in meters MSL")
    z_max: float = Field(..., description="Top elevation in meters MSL")
    is_multi_floor: bool = Field(default=False, description="Flag indicating if unit spans multiple vertical floors")
    floor_span: Optional[list[str]] = Field(default=None, description="List of floor IDs spanned by this unit")
    builtup_area_sqm: Optional[float] = Field(None, gt=0)
    spatial_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    status: str = Field(default="ACTIVE")

    @model_validator(mode="after")
    def validate_unit_bounds(self) -> "UnitBase":
        if self.z_max <= self.z_min:
            raise ValueError(f"z_max ({self.z_max}) must be greater than z_min ({self.z_min})")
        return self


class UnitCreate(UnitBase):
    floor_id: str = Field(..., description="ID of the parent FloorLevel")
    footprint_geojson: GeoJSONPolygon = Field(..., description="2D Footprint Polygon of the Unit")


class UnitUpdate(BaseModel):
    unit_number: Optional[str] = None
    unit_code: Optional[str] = None
    unit_type: Optional[str] = None
    z_min: Optional[float] = None
    z_max: Optional[float] = None
    is_multi_floor: Optional[bool] = None
    floor_span: Optional[list[str]] = None
    footprint_geojson: Optional[GeoJSONPolygon] = None
    builtup_area_sqm: Optional[float] = None
    spatial_metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class UnitRead(UnitBase):
    id: str
    floor_id: str
    ulpin_3d: str
    ulpin_status: str
    footprint_geojson: Dict[str, Any]
    carpet_area_sqm: float
    volume_cu_m: float
    is_clash_free: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Unit3DFeature(BaseModel):
    """3D GeoJSON Feature representation ready for 3D viewers."""
    type: str = "Feature"
    id: str
    geometry: Dict[str, Any]
    properties: Dict[str, Any]
