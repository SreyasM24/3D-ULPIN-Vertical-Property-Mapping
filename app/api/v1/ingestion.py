from typing import Dict, Any, Optional
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.services.ingestion.geojson_adapter import GeoJSONIngestionAdapter
from app.services.ingestion.metadata_adapters import (
    LiDARMetadataAdapter,
    DEMDSMMetadataAdapter,
    DroneImageryMetadataAdapter,
    FloorPlanMetadataAdapter,
    LiDARMetadataModel,
    DEMDSMMetadataModel,
    DroneImageryMetadataModel,
    FloorPlanMetadataModel,
)
from app.schemas.common import APIResponse
from app.schemas.provenance import IngestionResult

router = APIRouter(prefix="/ingestion", tags=["Geospatial Dataset Ingestion & Provenance"])


class GeoJSONIngestRequest(BaseModel):
    source_name: str = Field(default="GeoJSON Upload", example="Village_Survey_411001.geojson")
    source_crs: str = Field(default="EPSG:4326", example="EPSG:4326")
    geojson: Dict[str, Any] = Field(..., description="GeoJSON FeatureCollection or Polygon dict")


@router.post("/geojson", response_model=APIResponse[IngestionResult], status_code=status.HTTP_200_OK)
def ingest_geojson_dataset(payload: GeoJSONIngestRequest):
    """
    Ingests, normalizes, and validates a 2D GeoJSON cadastral dataset.
    Extracts features, computes projected UTM metrics (area m², perimeter m, bbox),
    heals minor topological defects safely, and generates a complete DatasetProvenance audit.
    """
    adapter = GeoJSONIngestionAdapter(source_name=payload.source_name)
    result = adapter.ingest(payload.geojson, options={"source_crs": payload.source_crs})
    return APIResponse(data=result)


@router.post("/lidar-metadata", response_model=APIResponse[IngestionResult], status_code=status.HTTP_201_CREATED)
def register_lidar_metadata(payload: LiDARMetadataModel):
    """
    Registers provenance metadata for 3D Airborne or Mobile LiDAR (LAS/LAZ) survey point clouds.
    Validates bounding extent, point counts, and vertical datum.
    """
    adapter = LiDARMetadataAdapter(source_name=payload.file_name)
    result = adapter.ingest(payload.model_dump())
    return APIResponse(data=result)


@router.post("/dem-metadata", response_model=APIResponse[IngestionResult], status_code=status.HTTP_201_CREATED)
def register_dem_metadata(payload: DEMDSMMetadataModel):
    """
    Registers provenance metadata for Digital Elevation / Surface Models (GeoTIFF rasters).
    Tracks pixel resolution, elevation min/max, and vertical datum.
    """
    adapter = DEMDSMMetadataAdapter(source_name=payload.raster_name)
    result = adapter.ingest(payload.model_dump())
    return APIResponse(data=result)


@router.post("/drone-metadata", response_model=APIResponse[IngestionResult], status_code=status.HTTP_201_CREATED)
def register_drone_survey_metadata(payload: DroneImageryMetadataModel):
    """
    Registers provenance metadata for Drone/UAV photogrammetric mapping flights.
    Records Ground Sampling Distance (GSD), flight altitude, and RTK/CORS configuration.
    """
    adapter = DroneImageryMetadataAdapter(source_name=payload.mission_name)
    result = adapter.ingest(payload.model_dump())
    return APIResponse(data=result)


@router.post("/floorplan-metadata", response_model=APIResponse[IngestionResult], status_code=status.HTTP_201_CREATED)
def register_floorplan_metadata(payload: FloorPlanMetadataModel):
    """
    Registers provenance metadata for architectural CAD/BIM floor plan drawings.
    Tracks scale, floor level, and datum elevation.
    """
    adapter = FloorPlanMetadataAdapter(source_name=f"{payload.building_code}_{payload.level_code}")
    result = adapter.ingest(payload.model_dump())
    return APIResponse(data=result)
