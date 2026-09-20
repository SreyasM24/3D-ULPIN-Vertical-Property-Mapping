from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    GEOJSON = "GEOJSON"
    SHAPEFILE = "SHAPEFILE"
    DEM_DSM = "DEM_DSM"
    LIDAR_POINT_CLOUD = "LIDAR_POINT_CLOUD"
    DRONE_IMAGERY = "DRONE_IMAGERY"
    FLOOR_PLAN_CAD = "FLOOR_PLAN_CAD"
    MANUAL = "MANUAL"


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    REPAIRED = "REPAIRED"
    REJECTED = "REJECTED"
    METADATA_EXTRACTED = "METADATA_EXTRACTED"


class ValidationStatus(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"


class DatasetProvenance(BaseModel):
    """
    Provenance audit trail for imported spatial datasets.
    Tracks lineage, original/normalized CRS, checksums, and normalization operations.
    """
    source_name: str
    source_type: SourceType
    original_crs: str = "EPSG:4326"
    normalized_crs: str = "EPSG:4326"
    ingestion_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_status: ProcessingStatus = ProcessingStatus.COMPLETED
    validation_status: ValidationStatus = ValidationStatus.VALID
    source_file_hash: Optional[str] = None
    feature_count: int = 0
    normalization_notes: List[str] = Field(default_factory=list)
    metadata_attributes: Dict[str, Any] = Field(default_factory=dict)


class IngestedFeature(BaseModel):
    """Standardized ingested cadastral feature with calculated metric properties."""
    source_id: Optional[str] = None
    geometry_geojson: Dict[str, Any]
    area_sqm: float
    perimeter_m: float
    centroid_lat: float
    centroid_lon: float
    bbox: List[float]
    projected_crs: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    was_repaired: bool = False
    repair_actions: List[str] = Field(default_factory=list)


class IngestionResult(BaseModel):
    """Result returned by dataset ingestion adapters."""
    success: bool
    provenance: DatasetProvenance
    features: List[IngestedFeature] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
