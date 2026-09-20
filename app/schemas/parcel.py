from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class GeoJSONPolygon(BaseModel):
    """GeoJSON Polygon Geometry definition."""
    type: str = Field(default="Polygon", pattern="^Polygon$")
    coordinates: List[List[List[float]]] = Field(
        ...,
        description="Linear rings: list of coordinates [lon, lat] where first and last match"
    )

    @field_validator("coordinates")
    @classmethod
    def validate_polygon_coords(cls, v: List[List[List[float]]]) -> List[List[List[float]]]:
        if not v or len(v) == 0:
            raise ValueError("Polygon must contain at least an outer linear ring.")
        outer_ring = v[0]
        if len(outer_ring) < 4:
            raise ValueError("Linear ring must have at least 4 coordinate pairs (closed polygon).")
        if outer_ring[0][:2] != outer_ring[-1][:2]:
            raise ValueError("Linear ring must be closed (first and last coordinates must match).")
        return v


class ParcelBase(BaseModel):
    state_code: str = Field(..., max_length=10, example="MH")
    district_code: str = Field(..., max_length=10, example="PUN")
    village_code: str = Field(..., max_length=20, example="54321")
    survey_number: str = Field(..., max_length=50, example="145/2A")
    subdivision_number: Optional[str] = Field(None, max_length=50, example="1")
    base_elevation_m: float = Field(default=560.0, description="Elevation above MSL in meters")
    spatial_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    status: str = Field(default="ACTIVE")


class ParcelCreate(ParcelBase):
    geometry_geojson: GeoJSONPolygon = Field(..., description="2D Boundary Polygon GeoJSON")


class ParcelUpdate(BaseModel):
    survey_number: Optional[str] = None
    subdivision_number: Optional[str] = None
    base_elevation_m: Optional[float] = None
    geometry_geojson: Optional[GeoJSONPolygon] = None
    spatial_metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class ParcelRead(ParcelBase):
    id: str
    ulpin: str
    area_sqm: float
    centroid_lat: float
    centroid_lon: float
    geometry_geojson: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
