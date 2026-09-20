"""
Pydantic Schemas for Asynchronous Ingestion & Processing Jobs.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobStage(str, Enum):
    QUEUED = "QUEUED"
    INSPECTION = "INSPECTION"
    PREPROCESSING = "PREPROCESSING"
    FEATURE_EXTRACTION = "FEATURE_EXTRACTION"
    CADASTRAL_CONSTRUCTION = "CADASTRAL_CONSTRUCTION"
    ULPIN_GENERATION = "ULPIN_GENERATION"
    VALIDATION = "VALIDATION"
    DIGITAL_TWIN_UPDATE = "DIGITAL_TWIN_UPDATE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobType(str, Enum):
    SURVEY_INGESTION = "SURVEY_INGESTION"
    END_TO_END_PARCEL_PROCESS = "END_TO_END_PARCEL_PROCESS"
    POINT_CLOUD_PROCESS = "POINT_CLOUD_PROCESS"
    RASTER_PROCESS = "RASTER_PROCESS"
    DRONE_PROCESS = "DRONE_PROCESS"
    CAD_PROCESS = "CAD_PROCESS"


class SurveyIngestJobRequest(BaseModel):
    """Payload to register an asynchronous survey dataset ingestion job."""
    model_config = ConfigDict(extra="ignore")

    source_type: str = Field(..., description="Type of survey: GEOJSON, LIDAR, DEM_DSM, DRONE, CAD_FLOOR_PLAN", example="GEOJSON")
    source_filename: str = Field(..., description="Original filename or dataset identifier", example="Survey_Sector_14.geojson")
    source_crs: str = Field(default="EPSG:4326", description="Source Coordinate Reference System", example="EPSG:4326")
    dataset_payload: Optional[Dict[str, Any]] = Field(default=None, description="Raw survey GeoJSON or metadata dictionary")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional ingestion options or survey metadata")


class ParcelProcessJobRequest(BaseModel):
    """Payload to trigger asynchronous end-to-end processing for a land parcel and its 3D structures."""
    model_config = ConfigDict(extra="ignore")

    parcel_id: Optional[str] = Field(default=None, description="Existing LandParcel UUID to process, or null if creating anew")
    state_code: Optional[int] = Field(default=27, description="State code (e.g. 27 for Maharashtra)", example=27)
    district_code: Optional[str] = Field(default="PUN", description="District code", example="PUN")
    survey_number: Optional[str] = Field(default="SN-411001-AUTO", description="Cadastral survey number", example="SN-411001-AUTO")
    parcel_geojson: Optional[Dict[str, Any]] = Field(default=None, description="GeoJSON polygon of the parcel if creating or updating")
    building_footprint_geojson: Optional[Dict[str, Any]] = Field(default=None, description="Building footprint polygon, or auto-derived if omitted")
    total_height_m: Optional[float] = Field(default=None, description="Measured or estimated building height in meters", example=18.5)
    ground_elevation_m: Optional[float] = Field(default=0.0, description="Base ground elevation AMSL in meters", example=560.0)
    floor_count: Optional[int] = Field(default=None, description="Total above-ground floors", example=5)
    basement_count: Optional[int] = Field(default=0, description="Basement floor levels", example=1)
    units_per_floor: int = Field(default=2, ge=1, le=10, description="Number of vertical units to derive per floor", example=2)
    source_evidence: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Sensor metadata (point cloud, DEM, raster) to feed ML feature extraction")
    auto_generate_strata: bool = Field(default=True, description="Whether to automatically construct candidate 3D strata and units")


class JobRead(BaseModel):
    """Public read schema representing job status and execution progress."""
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    job_type: str
    request_id: Optional[str] = None
    status: JobStatus
    current_stage: JobStage
    progress_percent: float = Field(ge=0.0, le=100.0)
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    source_filename: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    stage_details: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    tracking_url: Optional[str] = None


class JobResultResponse(BaseModel):
    """Detailed response schema returned upon job completion."""
    job_id: str
    status: JobStatus
    job_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    quality_score: Optional[float] = None
    quality_grade: Optional[str] = None
    is_valid: Optional[bool] = None
    created_entities: Dict[str, Any] = Field(default_factory=dict)
    validation_summary: Optional[Dict[str, Any]] = None
    digital_twin_url: Optional[str] = None
    anomalies: List[Dict[str, Any]] = Field(default_factory=list, description="Advisory cadastral anomaly findings")
    artifacts: Dict[str, Any] = Field(default_factory=dict)


class JobListResponse(BaseModel):
    """List response for job querying and filtering."""
    jobs: List[JobRead]
    total: int
    limit: int
    offset: int
