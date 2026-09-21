"""
Building Feature Extraction.
Reuses existing spatial engine and projected UTM cartography to extract
metric area, perimeter, footprint, and 3D volumetric metrics from building detections.
"""

from typing import Dict, Any, Optional, List
from app.ml.schemas import (
    BuildingFeatureResult,
    EvidenceSourceType,
    ConfidenceLevel,
    DataStage,
    SourceProvenance,
)
from app.services.spatial_engine import (
    compute_projected_spatial_metrics,
    geojson_to_shapely,
)
from app.core.exceptions import InvalidGeometryException


class BuildingFeatureExtractor:
    """
    Extracts geometric, dimensional, and volumetric building features.
    Guarantees strict metric Cartesian UTM calculation (never degrees).
    """

    @classmethod
    def extract_features(
        cls,
        footprint_geojson: Dict[str, Any],
        height_m: Optional[float] = None,
        floor_count: Optional[int] = None,
        ground_elevation_m: Optional[float] = None,
        source_type: EvidenceSourceType = EvidenceSourceType.BUILDING_METADATA,
        confidence: float = 0.90,
        uncertainty_m: Optional[float] = 0.2
    ) -> BuildingFeatureResult:
        if not footprint_geojson or not isinstance(footprint_geojson, dict):
            raise InvalidGeometryException("Cannot extract building features from empty or non-dictionary geometry.")

        # Reuses existing projected UTM calculation
        metrics = compute_projected_spatial_metrics(footprint_geojson)
        area_m2 = metrics["area_sqm"]
        perimeter_m = metrics["perimeter_m"]
        normalized_geojson = metrics["normalized_geojson"]

        # Calculate volume if valid positive height exists
        volume_m3 = None
        if height_m is not None and height_m > 0.0:
            volume_m3 = round(area_m2 * height_m, 2)

        conf_level = ConfidenceLevel.HIGH if confidence >= 0.85 else (
            ConfidenceLevel.MEDIUM if confidence >= 0.65 else ConfidenceLevel.LOW
        )

        provenance = SourceProvenance(
            source_type=source_type,
            source_id="EXTRACTOR_PROJECTED_METRICS",
            method="UTM_CARTOGRAPHIC_PROJECTION",
            confidence=confidence,
            uncertainty_m=uncertainty_m
        )

        return BuildingFeatureResult(
            footprint_geojson=normalized_geojson,
            area_m2=area_m2,
            perimeter_m=perimeter_m,
            height_m=height_m,
            ground_elevation_m=ground_elevation_m,
            volume_m3=volume_m3,
            floor_count=floor_count,
            confidence=confidence,
            confidence_level=conf_level,
            uncertainty_m=uncertainty_m,
            feature_sources=[source_type],
            stage=DataStage.DERIVED,
            provenance=provenance
        )
