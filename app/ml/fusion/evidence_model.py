"""
Multi-Source Evidence Model & Data Contracts.
Strictly distinguishes OBSERVED, AI_ESTIMATED, DETERMINISTIC, UNRESOLVED, and TEST_FIXTURE.
Never converts AI estimates into observed evidence or fabricates sensor coverage.
"""

from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class EvidenceClass(str, Enum):
    OBSERVED = "OBSERVED"                  # Directly measured by calibrated physical sensor
    AI_ESTIMATED = "AI_ESTIMATED"          # Inferred via trained neural network or statistical model
    DETERMINISTIC = "DETERMINISTIC"        # Geometrically or parametrically constructed by rules
    UNRESOLVED = "UNRESOLVED"              # Missing or indeterminate evidence
    TEST_FIXTURE = "TEST_FIXTURE"          # Synthetic test fixture for verification only


class MeasuredStatus(str, Enum):
    MEASURED = "MEASURED"                  # Physical sensor returns exist
    ESTIMATED = "ESTIMATED"                # Statistical or model estimation
    NOT_MEASURED = "NOT_MEASURED"          # No sensor measurement available


class EvidenceCoverageStatus(str, Enum):
    VALID = "VALID"                                  # Spatial coverage verified over target footprint
    NO_BOUNDS_OVERLAP = "NO_BOUNDS_OVERLAP"          # Sensor artifact spatial bounds do not intersect target
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"            # Incomplete coverage (< 50% overlap)
    TERRAIN_ONLY = "TERRAIN_ONLY"                    # Bare-earth DEM only, no roof surface returns
    INSUFFICIENT_RETURNS = "INSUFFICIENT_RETURNS"    # Too few points (< 3 points) inside footprint
    REJECTED_OUT_OF_BOUNDS = "REJECTED_OUT_OF_BOUNDS"
    UNVERIFIED = "UNVERIFIED"


class UnifiedEvidenceRecord(BaseModel):
    """Auditable evidence record across all modalities."""
    source_type: str
    source_reference: str
    crs: Optional[str] = None
    spatial_bounds: Optional[Dict[str, Any]] = None
    evidence_class: EvidenceClass
    measured_status: MeasuredStatus
    height_m: Optional[float] = None
    ground_elevation_m: Optional[float] = None
    top_elevation_m: Optional[float] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertainty_m: Optional[float] = Field(default=None, ge=0.0)
    coverage: EvidenceCoverageStatus = EvidenceCoverageStatus.UNVERIFIED
    method: str
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    limitations: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class EvidenceConflictRecord(BaseModel):
    """Records statistically significant discrepancies between evidence sources."""
    conflict_detected: bool = False
    conflict_severity: str = "NONE"      # NONE, LOW, MEDIUM, HIGH
    source_a: Optional[str] = None
    value_a_m: Optional[float] = None
    uncertainty_a_m: Optional[float] = None
    source_b: Optional[str] = None
    value_b_m: Optional[float] = None
    uncertainty_b_m: Optional[float] = None
    difference_m: Optional[float] = None
    threshold_m: Optional[float] = None
    review_required: bool = False
    explanation: str = "No conflict detected among active evidence sources."
    cadastral_policy_applied: str = "DOCUMENTED_EVIDENCE_PRIORITY"


class FusionOutcome(BaseModel):
    """Definitive outcome of multi-source evidence evaluation and selection."""
    selected_source: str
    selected_class: EvidenceClass
    selected_height_m: Optional[float] = None
    selected_ground_elevation_m: Optional[float] = None
    selected_top_elevation_m: Optional[float] = None
    uncertainty_m: Optional[float] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    method: str
    why_selected: str
    ai_status: str                       # BYPASSED_OBSERVED_EVIDENCE, ADVISORY_ESTIMATE, NOT_APPLICABLE
    candidates_evaluated: List[UnifiedEvidenceRecord] = Field(default_factory=list)
    conflict: EvidenceConflictRecord = Field(default_factory=EvidenceConflictRecord)
    review_required: bool = False
