from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from app.schemas.parcel import GeoJSONPolygon


class FloorBase(BaseModel):
    level_number: int = Field(..., example=3, description="Floor index: 0=Ground, positive=above ground, negative=basement")
    level_code: str = Field(..., max_length=10, example="L03", description="Code such as B01, G00, L01, RF0")
    level_type: str = Field(default="TYPICAL_FLOOR", example="TYPICAL_FLOOR")
    z_min: float = Field(..., description="Bottom elevation in meters above MSL")
    z_max: float = Field(..., description="Top elevation in meters above MSL")
    spatial_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    status: str = Field(default="ACTIVE")

    @model_validator(mode="after")
    def validate_vertical_bounds(self) -> "FloorBase":
        if self.z_max <= self.z_min:
            raise ValueError(f"z_max ({self.z_max}) must be greater than z_min ({self.z_min})")
        return self


class FloorCreate(FloorBase):
    building_id: str = Field(..., description="ID of the parent Building")
    footprint_geojson: Optional[GeoJSONPolygon] = Field(None, description="Optional floor boundary override")


class FloorUpdate(BaseModel):
    level_code: Optional[str] = None
    level_type: Optional[str] = None
    z_min: Optional[float] = None
    z_max: Optional[float] = None
    footprint_geojson: Optional[GeoJSONPolygon] = None
    spatial_metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class FloorRead(FloorBase):
    id: str
    building_id: str
    floor_height_m: float
    footprint_geojson: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
