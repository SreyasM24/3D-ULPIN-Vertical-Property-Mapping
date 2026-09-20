"""
Metadata-Only Adapters for Advanced Geospatial Ingestion.

Supports metadata registration and provenance tracking for:
- LiDAR (LAS/LAZ point clouds)
- Digital Elevation Models (DEM/DSM rasters)
- Drone Imagery surveys
- Floor Plans (CAD/BIM/PDF)

NOTE:
These adapters model and validate metadata structures and provenance.
They do not execute heavy point cloud extraction or photogrammetry meshing,
which are reserved for future asynchronous processing pipelines.
"""

from typing import Any, Dict, Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.services.ingestion.base import BaseIngestionAdapter, compute_sha256_str
from app.schemas.provenance import (
    IngestionResult,
    DatasetProvenance,
    SourceType,
    ProcessingStatus,
    ValidationStatus,
)


class LiDARMetadataModel(BaseModel):
    """Metadata specification for 3D Airborne or Mobile LiDAR (LAS/LAZ) survey."""
    file_name: str
    las_version: str = Field(default="1.4", example="1.4")
    point_count: int = Field(..., gt=0, example=15000000)
    horizontal_crs: str = Field(default="EPSG:4326", example="EPSG:4326")
    vertical_datum: str = Field(default="EGM96", example="EGM96")
    bounds_bbox: List[float] = Field(
        ...,
        description="[min_x, min_y, min_z, max_x, max_y, max_z]",
        example=[73.85, 18.51, 550.0, 73.87, 18.53, 620.0]
    )
    sensor_model: Optional[str] = Field(None, example="Riegl VUX-1LR")
    flight_date: Optional[str] = Field(None, example="2026-02-10")
    pulse_rate_khz: Optional[int] = Field(None, example=820)


class DEMDSMMetadataModel(BaseModel):
    """Metadata specification for Digital Elevation / Surface Models (GeoTIFF)."""
    raster_name: str
    model_type: str = Field(default="DSM", example="DSM")  # DSM or DTM/DEM
    spatial_resolution_m: float = Field(..., gt=0, example=0.25)
    horizontal_crs: str = Field(default="EPSG:4326", example="EPSG:4326")
    vertical_datum: str = Field(default="WGS84_ELLIPSOID", example="WGS84_ELLIPSOID")
    elevation_min_m: float = Field(..., example=545.2)
    elevation_max_m: float = Field(..., example=632.8)
    bounds_bbox: List[float] = Field(..., example=[73.85, 18.51, 73.87, 18.53])
    sensor_platform: Optional[str] = Field(None, example="UAV_PHOTOGRAMMETRY")


class DroneImageryMetadataModel(BaseModel):
    """Metadata specification for Drone / UAV Photogrammetry Survey."""
    mission_name: str
    operator_organization: str = Field(..., example="Survey of India / Empanelled Agency")
    drone_model: str = Field(..., example="DJI Matrice 300 RTK")
    camera_sensor: str = Field(..., example="Zenmuse P1")
    flight_altitude_agl_m: float = Field(..., gt=0, example=120.0)
    ground_sampling_distance_cm: float = Field(..., gt=0, example=2.5)
    total_images: int = Field(..., gt=0, example=450)
    rtk_cors_used: bool = Field(default=True)
    survey_date: str = Field(..., example="2026-03-05")
    coverage_area_sqm: Optional[float] = Field(None, example=250000.0)


class FloorPlanMetadataModel(BaseModel):
    """Metadata specification for Building Floor Plan / Architectural CAD drawing."""
    building_code: str = Field(..., example="TWR-A")
    level_code: str = Field(..., example="L04")
    drawing_number: str = Field(..., example="ARCH-FL-04-REV2")
    source_format: str = Field(default="DXF", example="DXF")  # DXF, DWG, IFC, PDF
    scale: str = Field(default="1:100", example="1:100")
    georeferenced: bool = Field(default=True)
    datum_elevation_m: float = Field(..., example=572.0)
    floor_height_m: float = Field(..., gt=0, example=3.0)
    architect_approval_ref: Optional[str] = Field(None, example="MCGM/BP/2026/0912")


# ---------------------------------------------------------------------------
# Ingestion Adapters
# ---------------------------------------------------------------------------

class LiDARMetadataAdapter(BaseIngestionAdapter):
    def __init__(self, source_name: str = "LiDAR Metadata Ingestion"):
        super().__init__(source_name=source_name, source_type=SourceType.LIDAR_POINT_CLOUD)

    def ingest(self, content: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> IngestionResult:
        model = LiDARMetadataModel(**content)
        file_hash = compute_sha256_str(str(model.model_dump()))

        provenance = DatasetProvenance(
            source_name=self.source_name,
            source_type=self.source_type,
            original_crs=model.horizontal_crs,
            normalized_crs="EPSG:4326",
            processing_status=ProcessingStatus.METADATA_EXTRACTED,
            validation_status=ValidationStatus.VALID,
            source_file_hash=file_hash,
            feature_count=0,
            normalization_notes=["Point cloud metadata registered; raw point extraction pending"],
            metadata_attributes=model.model_dump()
        )
        return IngestionResult(success=True, provenance=provenance, features=[], errors=[])


class DEMDSMMetadataAdapter(BaseIngestionAdapter):
    def __init__(self, source_name: str = "DEM/DSM Metadata Ingestion"):
        super().__init__(source_name=source_name, source_type=SourceType.DEM_DSM)

    def ingest(self, content: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> IngestionResult:
        model = DEMDSMMetadataModel(**content)
        file_hash = compute_sha256_str(str(model.model_dump()))

        provenance = DatasetProvenance(
            source_name=self.source_name,
            source_type=self.source_type,
            original_crs=model.horizontal_crs,
            normalized_crs="EPSG:4326",
            processing_status=ProcessingStatus.METADATA_EXTRACTED,
            validation_status=ValidationStatus.VALID,
            source_file_hash=file_hash,
            feature_count=0,
            normalization_notes=["Elevation raster metadata registered; surface query pipeline pending"],
            metadata_attributes=model.model_dump()
        )
        return IngestionResult(success=True, provenance=provenance, features=[], errors=[])


class DroneImageryMetadataAdapter(BaseIngestionAdapter):
    def __init__(self, source_name: str = "Drone Survey Metadata Ingestion"):
        super().__init__(source_name=source_name, source_type=SourceType.DRONE_IMAGERY)

    def ingest(self, content: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> IngestionResult:
        model = DroneImageryMetadataModel(**content)
        file_hash = compute_sha256_str(str(model.model_dump()))

        provenance = DatasetProvenance(
            source_name=self.source_name,
            source_type=self.source_type,
            original_crs="EPSG:4326",
            normalized_crs="EPSG:4326",
            processing_status=ProcessingStatus.METADATA_EXTRACTED,
            validation_status=ValidationStatus.VALID,
            source_file_hash=file_hash,
            feature_count=0,
            normalization_notes=["Drone survey mission metadata registered"],
            metadata_attributes=model.model_dump()
        )
        return IngestionResult(success=True, provenance=provenance, features=[], errors=[])


class FloorPlanMetadataAdapter(BaseIngestionAdapter):
    def __init__(self, source_name: str = "Floor Plan Metadata Ingestion"):
        super().__init__(source_name=source_name, source_type=SourceType.FLOOR_PLAN_CAD)

    def ingest(self, content: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> IngestionResult:
        model = FloorPlanMetadataModel(**content)
        file_hash = compute_sha256_str(str(model.model_dump()))

        provenance = DatasetProvenance(
            source_name=self.source_name,
            source_type=self.source_type,
            original_crs="EPSG:4326",
            normalized_crs="EPSG:4326",
            processing_status=ProcessingStatus.METADATA_EXTRACTED,
            validation_status=ValidationStatus.VALID,
            source_file_hash=file_hash,
            feature_count=0,
            normalization_notes=["Architectural floor plan drawing metadata registered"],
            metadata_attributes=model.model_dump()
        )
        return IngestionResult(success=True, provenance=provenance, features=[], errors=[])
