from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.parcel import GeoJSONPolygon


class BuildingBase(BaseModel):
    building_name: str = Field(..., max_length=100, example="Tower A")
    building_code: str = Field(..., max_length=30, example="TWR-A")
    rera_number: Optional[str] = Field(None, max_length=50, example="P52100012345")
    structure_type: str = Field(default="RESIDENTIAL", example="RESIDENTIAL")
    floors_above_ground: int = Field(default=1, ge=1, example=12)
    basement_floors: int = Field(default=0, ge=0, example=2)
    total_height_m: float = Field(..., gt=0, example=45.0)
    ground_elevation_m: float = Field(default=560.0, example=560.0)
    spatial_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    status: str = Field(default="ACTIVE")


class BuildingCreate(BuildingBase):
    parcel_id: str = Field(..., description="ID of the parent LandParcel")
    footprint_geojson: GeoJSONPolygon = Field(..., description="2D Building Footprint Polygon")


class BuildingUpdate(BaseModel):
    building_name: Optional[str] = None
    rera_number: Optional[str] = None
    structure_type: Optional[str] = None
    floors_above_ground: Optional[int] = None
    basement_floors: Optional[int] = None
    total_height_m: Optional[float] = None
    ground_elevation_m: Optional[float] = None
    footprint_geojson: Optional[GeoJSONPolygon] = None
    spatial_metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class BuildingRead(BuildingBase):
    id: str
    parcel_id: str
    footprint_geojson: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
