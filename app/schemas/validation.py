"""
Pydantic V2 Schemas for Advanced Cadastral Topology and Validation.
Supports auditable validation reporting, rule discovery, quality scoring,
and historical compliance tracking.
"""

from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RuleSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class RuleCategory(str, Enum):
    GEOMETRY = "GEOMETRY"
    HIERARCHY = "HIERARCHY"
    FLOOR_STRATA = "FLOOR_STRATA"
    TOPOLOGY_3D = "TOPOLOGY_3D"
    UNIT_INTEGRITY = "UNIT_INTEGRITY"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class QualityGrade(str, Enum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"          # 90 - 100
    GOOD_QUALITY = "GOOD_QUALITY"                # 75 - 89
    REQUIRES_REVIEW = "REQUIRES_REVIEW"          # 50 - 74
    INVALID_OR_INCOMPLETE = "INVALID_OR_INCOMPLETE"  # 0 - 49


class ClashClassification(str, Enum):
    CRITICAL = "CRITICAL"                      # Actual private property volumetric intersection
    WARNING = "WARNING"                        # Near-boundary / tolerance condition
    INFO = "INFO"                              # Shared / common space or infrastructure coexistence
    UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"  # Insufficient semantic information to determine legal/cadastral status


class ValidationRuleDefinition(BaseModel):
    """Catalog metadata for an independently testable validation rule."""
    rule_id: str
    category: RuleCategory
    severity: RuleSeverity
    title: str
    description: str
    affected_entity_types: List[str]


class ValidationIssue(BaseModel):
    """Auditable finding produced by a validation rule."""
    rule_id: str
    category: RuleCategory
    severity: RuleSeverity
    entity_type: str
    entity_id: str
    entity_identifier: Optional[str] = None  # ULPIN, code, or unit number
    measured_values: Dict[str, Any] = Field(default_factory=dict)
    expected_condition: str
    actual_condition: str
    explanation: str
    suggested_remediation: str


class QualityScoreBreakdown(BaseModel):
    """
    Transparent, explainable 100-point data quality score breakdown.
    NOTE: Project-level data-quality indicator with NO legal authority or government certification.
    """
    geometry_validity: float = Field(ge=0.0, le=25.0, description="Max 25 pts: OGC validity, ring closure, no distortion")
    crs_projection: float = Field(ge=0.0, le=15.0, description="Max 15 pts: Valid coordinate ranges & optimal UTM projection")
    hierarchy_containment: float = Field(ge=0.0, le=20.0, description="Max 20 pts: Parcel->Building->Floor->Unit containment")
    vertical_strata_consistency: float = Field(ge=0.0, le=15.0, description="Max 15 pts: Floor ordering, z bounds, no strata clashes")
    topology_3d_clash_freedom: float = Field(ge=0.0, le=15.0, description="Max 15 pts: Volumetric separation & coexistence")
    provenance_completeness: float = Field(ge=0.0, le=10.0, description="Max 10 pts: Metadata, survey numbers, timestamps, ULPINs")
    total_score: float = Field(ge=0.0, le=100.0)
    grade: QualityGrade
    deductions: List[Dict[str, Any]] = Field(default_factory=list)
    disclaimer: str = (
        "SIH 26011 Prototype Notice: This quality score is a technical data-quality indicator "
        "and conveys no legal authority, official title confirmation, or government certification."
    )


class DetailedClashFinding(BaseModel):
    """Detailed volumetric intersection audit between two spatial entities."""
    entity_a_id: str
    entity_a_identifier: str
    entity_a_type: str
    entity_b_id: str
    entity_b_identifier: str
    entity_b_type: str
    classification: ClashClassification
    horizontal_overlap_sqm: float
    vertical_overlap_m: float
    overlap_elevation_range: List[float]  # [z_min_overlap, z_max_overlap]
    estimated_overlap_volume_cu_m: float
    explanation: str
    suggested_action: str


class EntityValidationReport(BaseModel):
    """Validation report for an individual entity (Building or Unit)."""
    entity_id: str
    entity_type: str
    entity_code: Optional[str] = None
    is_valid: bool
    issues: List[ValidationIssue] = Field(default_factory=list)
    quality_score: float
    quality_grade: QualityGrade


class DigitalTwinValidationReport(BaseModel):
    """
    Unified validation report for an entire parcel and its vertical digital twin.
    Directly consumable by frontends and external cadastral systems.
    """
    validation_run_id: str
    timestamp: datetime
    parcel_id: str
    parcel_ulpin: str
    engine_version: str = "1.0.0-cadastral-validator"
    data_version: Optional[str] = None
    is_valid: bool
    quality_score: QualityScoreBreakdown
    total_rules_executed: int
    total_rules_passed: int
    total_rules_failed: int
    critical_errors_count: int
    warnings_count: int
    info_count: int
    entity_counts: Dict[str, int]
    issues: List[ValidationIssue]
    clash_findings: List[DetailedClashFinding]
    recommended_actions: List[str]

    model_config = ConfigDict(from_attributes=True)


class ValidationHistoryItem(BaseModel):
    """Compact summary of a historical validation run."""
    id: str
    validation_run_id: str
    target_entity_type: str
    target_entity_id: str
    engine_version: str
    is_valid: bool
    quality_score: float
    quality_grade: str
    critical_issues_count: int
    warnings_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
