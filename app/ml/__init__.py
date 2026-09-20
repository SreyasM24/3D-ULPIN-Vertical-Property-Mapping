"""
ML/AI-Assisted 3D Feature Extraction Engine for SIH 26011.
Proposes, detects, and estimates 3D cadastral features with explicit uncertainty
before handing them to the deterministic cadastral validation engine.
"""

from app.ml.schemas import (
    EvidenceSourceType,
    ConfidenceLevel,
    DataStage,
    ModelStatus,
    MLCapability,
    BuildingDetectionResult,
    BuildingFeatureResult,
    VerticalFeatureResult,
    AnomalyResult,
    SourceProvenance,
    PipelineResult,
)

__all__ = [
    "EvidenceSourceType",
    "ConfidenceLevel",
    "DataStage",
    "ModelStatus",
    "MLCapability",
    "BuildingDetectionResult",
    "BuildingFeatureResult",
    "VerticalFeatureResult",
    "AnomalyResult",
    "SourceProvenance",
    "PipelineResult",
]
