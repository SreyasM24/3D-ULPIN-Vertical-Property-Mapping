"""
Pydantic Schemas for 3D Temporal Property Change Detection.
SIH 26011 - 3D ULPIN & Vertical Property Mapping System.

Advisory change detection model comparing registered baseline digital twins
against subsequent survey captures or proposed AI feature extractions.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class ChangeType(str, Enum):
    BUILDING_ADDED = "BUILDING_ADDED"
    BUILDING_REMOVED = "BUILDING_REMOVED"
    FOOTPRINT_CHANGED = "FOOTPRINT_CHANGED"
    HEIGHT_CHANGED = "HEIGHT_CHANGED"
    FLOOR_STRUCTURE_CHANGED = "FLOOR_STRUCTURE_CHANGED"
    VERTICAL_UNIT_CHANGED = "VERTICAL_UNIT_CHANGED"
    BASEMENT_CHANGED = "BASEMENT_CHANGED"
    ELEVATED_STRUCTURE_CHANGED = "ELEVATED_STRUCTURE_CHANGED"
    GEOMETRY_UNCERTAIN = "GEOMETRY_UNCERTAIN"


class ChangeClassification(str, Enum):
    OBSERVED_CHANGE = "OBSERVED_CHANGE"
    AI_ESTIMATED_CHANGE = "AI_ESTIMATED_CHANGE"
    DETERMINISTIC_CHANGE = "DETERMINISTIC_CHANGE"
    TEST_FIXTURE_CHANGE = "TEST_FIXTURE_CHANGE"


class FootprintChangeClass(str, Enum):
    NO_SIGNIFICANT_CHANGE = "NO_SIGNIFICANT_CHANGE"
    MINOR_GEOMETRY_CHANGE = "MINOR_GEOMETRY_CHANGE"
    MAJOR_GEOMETRY_CHANGE = "MAJOR_GEOMETRY_CHANGE"
    NEW_BUILDING = "NEW_BUILDING"
    REMOVED_BUILDING = "REMOVED_BUILDING"
    UNRESOLVED = "UNRESOLVED"


class ChangeSeverity(str, Enum):
    NONE = "NONE"
    MINOR = "MINOR"
    MODERATE = "MODERATE"
    SIGNIFICANT = "SIGNIFICANT"
    CRITICAL = "CRITICAL"


class ChangeEvent(BaseModel):
    """Structured temporal change event representing a measurable difference."""
    change_type: ChangeType
    change_classification: ChangeClassification
    entity_type: str  # PARCEL, BUILDING, FLOOR, UNIT
    entity_id: str
    entity_identifier: Optional[str] = None
    previous_value: Optional[Any] = None
    new_value: Optional[Any] = None
    magnitude: float = Field(default=0.0, description="Measurable magnitude (m, m², m³, or count)")
    unit: str = Field(default="", description="Measurement unit (m, m2, m3, count)")
    confidence: float = Field(ge=0.0, le=1.0, description="Technical confidence score")
    source: str = Field(default="UNKNOWN", description="Sensor or algorithm source provenance")
    requires_review: bool = True
    explanation: str


class FootprintComparisonResult(BaseModel):
    """Deterministic geometric comparison metrics between two building footprints."""
    baseline_area_sqm: float
    new_area_sqm: float
    area_delta_sqm: float
    area_pct_change: float
    baseline_perimeter_m: float
    new_perimeter_m: float
    perimeter_delta_m: float
    intersection_area_sqm: float
    union_area_sqm: float
    iou: float = Field(ge=0.0, le=1.0)
    centroid_displacement_m: float
    classification: FootprintChangeClass
    is_significant: bool


class HeightComparisonResult(BaseModel):
    """Vertical height comparison metrics between baseline and new observation."""
    baseline_height_m: Optional[float] = None
    new_height_m: Optional[float] = None
    height_delta_m: Optional[float] = None
    height_pct_change: Optional[float] = None
    baseline_source: str = "UNKNOWN"
    new_source: str = "UNKNOWN"
    uncertainty_adjusted_delta_m: Optional[float] = None
    is_significant: bool = False
    classification: str = "NO_CHANGE"  # OBSERVED_HEIGHT_CHANGE, AI_ESTIMATED_HEIGHT_CHANGE, NO_CHANGE
    requires_review: bool = False


class FloorComparisonResult(BaseModel):
    """Comparison of vertical floor strata slices between snapshots."""
    baseline_floor_count: int
    new_floor_count: int
    floor_count_delta: int
    added_floors: List[str] = Field(default_factory=list)
    removed_floors: List[str] = Field(default_factory=list)
    altered_floors: List[Dict[str, Any]] = Field(default_factory=list)
    basement_delta: int = 0
    elevated_delta: int = 0
    requires_review: bool = False


class UnitComparisonResult(BaseModel):
    """Comparison of vertical property unit spaces between snapshots."""
    baseline_unit_count: int
    new_unit_count: int
    unit_count_delta: int
    added_units: List[str] = Field(default_factory=list)
    removed_units: List[str] = Field(default_factory=list)
    altered_units: List[Dict[str, Any]] = Field(default_factory=list)
    requires_review: bool = False


class DigitalTwinSnapshot(BaseModel):
    """Versioned representation of a Digital Twin observation."""
    model_config = ConfigDict(extra="ignore")

    snapshot_id: str
    entity_id: str
    version: str = "1.0.0"
    observation_timestamp: Optional[str] = None  # Explicit ISO string or None if unavailable
    source: str = "REGISTERED_CADASTRAL_TRUTH"  # SENSOR, AI_EXTRACTION, SURVEY, TEST_FIXTURE
    footprint_geojson: Optional[Dict[str, Any]] = None
    ground_elevation_m: float = 0.0
    total_height_m: Optional[float] = None
    height_uncertainty_m: Optional[float] = None
    height_source: Optional[str] = None
    floors: List[Dict[str, Any]] = Field(default_factory=list)
    units: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TemporalComparisonConfig(BaseModel):
    """Configurable tolerance thresholds for deterministic temporal change detection."""
    iou_significance_threshold: float = Field(default=0.92, description="IoU below which footprint is considered altered")
    area_delta_threshold_sqm: float = Field(default=2.0, description="Minimum square meters delta to trigger change event")
    centroid_displacement_threshold_m: float = Field(default=0.30, description="Minimum centroid shift in meters")
    height_delta_threshold_m: float = Field(default=0.50, description="Minimum height difference in meters")
    is_test_fixture: bool = Field(default=False, description="Flag indicating input is a controlled test fixture")


class TemporalChangeReport(BaseModel):
    """Complete temporal change evaluation report between two digital twin states."""
    comparison_id: str
    compared_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    baseline_snapshot_id: str
    observation_snapshot_id: str
    entity_id: str
    is_test_fixture: bool = False
    technical_change_score: float = Field(ge=0.0, le=1.0, description="TECHNICAL_CHANGE_SCORE from 0.0 to 1.0")
    change_severity: ChangeSeverity
    requires_cadastral_review: bool
    total_change_events: int
    change_events: List[ChangeEvent] = Field(default_factory=list)
    footprint_comparison: Optional[FootprintComparisonResult] = None
    height_comparison: Optional[HeightComparisonResult] = None
    floor_comparison: Optional[FloorComparisonResult] = None
    unit_comparison: Optional[UnitComparisonResult] = None
    cross_referenced_anomalies: List[Dict[str, Any]] = Field(default_factory=list)
    legal_disclaimer: str = (
        "ADVISORY NOTICE: This report is a deterministic geometric change audit. "
        "It does not constitute legal ownership transfer, nor does it predict structural failure. "
        "Official cadastral records remain unaltered until authorized surveyor review."
    )


class TemporalCompareRequest(BaseModel):
    """Input payload to trigger temporal comparison."""
    model_config = ConfigDict(extra="ignore")

    parcel_id: Optional[str] = Field(default=None, description="Registered parcel ID to use as baseline")
    baseline_snapshot: Optional[DigitalTwinSnapshot] = Field(default=None, description="Explicit baseline snapshot")
    new_observation: DigitalTwinSnapshot = Field(..., description="New observation snapshot or AI proposal")
    config: Optional[TemporalComparisonConfig] = Field(default_factory=TemporalComparisonConfig)
