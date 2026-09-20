"""
Pydantic V2 Data Contracts for ML/AI-Assisted 3D Feature Extraction Engine.
Strictly distinguishes OBSERVED, ESTIMATED, DERIVED, and VALIDATED stages.
"""

from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict


class EvidenceSourceType(str, Enum):
    POINT_CLOUD = "POINT_CLOUD"
    DSM_DTM = "DSM_DTM"
    DRONE_PHOTOGRAMMETRY = "DRONE_PHOTOGRAMMETRY"
    CAD_FLOOR_PLAN = "CAD_FLOOR_PLAN"
    BUILDING_METADATA = "BUILDING_METADATA"
    ASSUMPTION_FALLBACK = "ASSUMPTION_FALLBACK"
    EXPLICIT_FLOOR_COUNT = "EXPLICIT_FLOOR_COUNT"
    OBSERVED_HEIGHT_DECOMPOSITION = "OBSERVED_HEIGHT_DECOMPOSITION"
    AI_HEIGHT_DECOMPOSITION = "AI_HEIGHT_DECOMPOSITION"
    DETERMINISTIC_BASELINE = "DETERMINISTIC_BASELINE"
    UNRESOLVED = "UNRESOLVED"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"          # Verified survey or high-density LiDAR with low uncertainty
    MEDIUM = "MEDIUM"      # Architectural CAD/BIM or solid photogrammetric DSM
    LOW = "LOW"            # Inferred estimates or statistical height assumptions
    UNKNOWN = "UNKNOWN"    # Unverified defaults or insufficient data


class DataStage(str, Enum):
    OBSERVED = "OBSERVED"    # Raw sensor data directly measured
    ESTIMATED = "ESTIMATED"  # ML/heuristic output with uncertainty
    DERIVED = "DERIVED"      # Geometrically calculated from estimates
    VALIDATED = "VALIDATED"  # Passed deterministic cadastral validation rules


class ModelStatus(str, Enum):
    ACTIVE = "ACTIVE"                  # Model weights loaded and ready
    NOT_CONFIGURED = "NOT_CONFIGURED"  # Interface present, no trained weights configured
    DEGRADED = "DEGRADED"              # Running on heuristic fallback path
    ERROR = "ERROR"                    # Failure in model execution


class MLCapability(BaseModel):
    """Runtime inspection of optional native C-libraries and ML accelerators."""
    has_pdal: bool = False
    has_open3d: bool = False
    has_rasterio: bool = False
    has_laspy: bool = False
    has_torch: bool = False
    has_onnx: bool = False
    hardware_acceleration: str = "CPU"
    notes: List[str] = Field(default_factory=list)


class SourceProvenance(BaseModel):
    """Auditable provenance record for an ML/AI-extracted feature."""
    source_type: EvidenceSourceType
    source_id: str
    method: str
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty_m: Optional[float] = Field(default=None, ge=0.0)


class BuildingDetectionResult(BaseModel):
    """Detection result proposing building footprint and coarse 3D envelope."""
    building_id: Optional[str] = None
    footprint_geojson: Dict[str, Any]
    estimated_height_m: Optional[float] = None
    estimated_ground_elevation_m: Optional[float] = None
    estimated_top_elevation_m: Optional[float] = None
    estimated_floor_count: Optional[int] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    uncertainty_m: Optional[float] = None
    source: EvidenceSourceType
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    stage: DataStage = DataStage.ESTIMATED
    processing_metadata: Dict[str, Any] = Field(default_factory=dict)


class BuildingFeatureResult(BaseModel):
    """Extracted building spatial and volumetric metric features."""
    footprint_geojson: Dict[str, Any]
    area_m2: float
    perimeter_m: float
    height_m: Optional[float] = None
    volume_m3: Optional[float] = None
    floor_count: Optional[int] = None
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    uncertainty_m: Optional[float] = None
    feature_sources: List[EvidenceSourceType] = Field(default_factory=list)
    stage: DataStage = DataStage.DERIVED
    provenance: Optional[SourceProvenance] = None


class VerticalFeatureResult(BaseModel):
    """Proposed vertical strata slice or unit envelope."""
    level_code: str
    z_min: float
    z_max: float
    estimated_height_m: float
    classification: str  # UNDERGROUND, GROUND_LEVEL, ELEVATED, MULTI_LEVEL_INFRASTRUCTURE, ROOFTOP, UNKNOWN
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    uncertainty_m: Optional[float] = None
    source: EvidenceSourceType
    stage: DataStage = DataStage.ESTIMATED


class AnomalyResult(BaseModel):
    """Advisory spatial, structural, or statistical anomaly signal."""
    anomaly_type: str
    severity: str  # ADVISORY, WARNING, CRITICAL
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    geometry_reference: Optional[Dict[str, Any]] = None
    requires_review: bool = True


class PipelineResult(BaseModel):
    """End-to-end feature extraction pipeline execution outcome."""
    status: str  # SUCCESS, PARTIAL, DEGRADED, FAILED
    features: Optional[BuildingFeatureResult] = None
    vertical_proposals: List[VerticalFeatureResult] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    uncertainty_m: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    provenance: List[SourceProvenance] = Field(default_factory=list)
    anomalies: List[AnomalyResult] = Field(default_factory=list)
    validation_ready: bool = False
