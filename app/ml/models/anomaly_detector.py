"""
Cadastral ML Anomaly Detector Adapter.
Integrates with ml_anomaly_hook.py to flag spatial, vertical, and structural
anomalies for human review without declaring authoritative legal invalidity.
"""

from typing import List, Dict, Any, Optional
from app.ml.models.base import BaseFeatureModel
from app.ml.schemas import (
    ModelStatus,
    AnomalyResult,
)
from app.services.ml_anomaly_hook import CadastralAnomalyDetectionHook
from app.core.config import settings


class CadastralMLAnomalyDetector(BaseFeatureModel, CadastralAnomalyDetectionHook):
    """
    ML/Statistical Anomaly Detector for 3D Cadastral Digital Twins.
    Flags statistical outliers, geometric discrepancies, and impossible vertical geometries.
    """

    def __init__(self, weights_path: Optional[str] = None):
        super().__init__(
            model_name="CadastralAnomalyDetector_Ensemble",
            model_version="0.1.0",
            model_type="ANOMALY_DETECTOR",
            weights_path=weights_path
        )
        self.load()

    def load(self) -> bool:
        self.status = ModelStatus.ACTIVE  # Rule-guided statistical heuristic detector is always active
        return True

    def predict(self, inputs: Dict[str, Any]) -> List[AnomalyResult]:
        """Runs candidate anomaly checks across building and strata definitions."""
        anomalies: List[AnomalyResult] = []

        height_m = inputs.get("height_m") or inputs.get("total_height_m")
        max_h = getattr(settings, "MAX_REASONABLE_BUILDING_HEIGHT_M", 350.0)
        min_fl_h = getattr(settings, "MIN_REASONABLE_FLOOR_HEIGHT_M", 2.2)

        # 1. Unusual building height outlier
        if height_m is not None:
            if float(height_m) > max_h:
                anomalies.append(
                    AnomalyResult(
                        anomaly_type="UNUSUAL_BUILDING_HEIGHT",
                        severity="WARNING",
                        confidence=0.92,
                        explanation=f"Building height ({height_m:.1f}m) exceeds typical urban threshold ({max_h}m). Verify skyscraper status.",
                        requires_review=True
                    )
                )
            elif float(height_m) < 1.8:
                anomalies.append(
                    AnomalyResult(
                        anomaly_type="IMPLAUSIBLY_LOW_HEIGHT",
                        severity="WARNING",
                        confidence=0.88,
                        explanation=f"Building height ({height_m:.2f}m) is below human habitable minimum. Check elevation datum.",
                        requires_review=True
                    )
                )

        # 2. Floor / Height Inconsistency
        floor_count = inputs.get("floor_count") or inputs.get("floors_above_ground")
        if height_m is not None and floor_count is not None and int(floor_count) > 0:
            avg_fl_h = float(height_m) / int(floor_count)
            if avg_fl_h < min_fl_h:
                anomalies.append(
                    AnomalyResult(
                        anomaly_type="FLOOR_HEIGHT_COMPRESSION",
                        severity="WARNING",
                        confidence=0.85,
                        explanation=f"Implied average floor height ({avg_fl_h:.2f}m) across {floor_count} floors is below standard minimum ({min_fl_h}m).",
                        requires_review=True
                    )
                )
            elif avg_fl_h > 15.0:
                anomalies.append(
                    AnomalyResult(
                        anomaly_type="EXCESSIVE_FLOOR_HEIGHT",
                        severity="ADVISORY",
                        confidence=0.80,
                        explanation=f"Average floor height ({avg_fl_h:.2f}m) is unusually large. May represent high-bay industrial or atrium spaces.",
                        requires_review=True
                    )
                )

        # 3. Disconnected footprint parts
        footprint = inputs.get("footprint_geojson")
        if footprint and footprint.get("type") == "MultiPolygon":
            coords = footprint.get("coordinates", [])
            if len(coords) > 1:
                anomalies.append(
                    AnomalyResult(
                        anomaly_type="DISCONNECTED_FOOTPRINT_MULTIPOLYGON",
                        severity="ADVISORY",
                        confidence=0.75,
                        explanation=f"Footprint contains {len(coords)} disconnected components. Check for detached annexes or digitizing artifacts.",
                        requires_review=True
                    )
                )

        return anomalies

    def detect_anomalies(self, digital_twin_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Implementation of CadastralAnomalyDetectionHook for digital twin validation."""
        summary = digital_twin_data.get("summary", {})
        results = self.predict({
            "total_height_m": summary.get("max_height_m"),
            "floor_count": summary.get("total_floors"),
            "footprint_geojson": digital_twin_data.get("parcel", {}).get("geometry_geojson")
        })
        return [r.model_dump() for r in results]

    def health(self) -> Dict[str, Any]:
        """Returns runtime health probe and honest architectural description."""
        base = super().health()
        base.update({
            "is_ready": True,
            "status": "ACTIVE",
            "is_ml_model": False,
            "engine": "DETERMINISTIC_ADVISORY_ANOMALY_DETECTOR",
            "methodology": "RULE_BASED_STATISTICAL_HEURISTICS",
            "requires_weights": False,
            "notes": (
                "Deterministic rule-based advisory anomaly detector. "
                "Inspects heights, floor ratios, and multipolygon footprints without mutating cadastral records."
            )
        })
        return base

    def metadata(self) -> Dict[str, Any]:
        """Exposes engine specification, configuration defaults, and detected anomaly rules."""
        base = super().metadata()
        base.update({
            "is_ready": True,
            "status": "ACTIVE",
            "requires_weights": False,
            "is_ml_model": False,
            "supported_backends": ["DETERMINISTIC_RULES", "SPATIAL_HEURISTICS"],
            "detected_rules": [
                "UNUSUAL_BUILDING_HEIGHT",
                "IMPLAUSIBLY_LOW_HEIGHT",
                "FLOOR_HEIGHT_COMPRESSION",
                "EXCESSIVE_FLOOR_HEIGHT",
                "DISCONNECTED_FOOTPRINT_MULTIPOLYGON"
            ]
        })
        return base

