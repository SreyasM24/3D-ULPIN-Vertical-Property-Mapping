"""
Confidence & Uncertainty Calibration Engine.
Provides transparent, evidence-based technical confidence scores and uncertainty (±m).

DISCLAIMER:
These scores represent project-level algorithmic quality indicators and engineering assumptions.
They do NOT constitute empirical statistical calibration, official legal confidence, or title guarantee.
"""

from typing import List, Tuple, Optional
from app.ml.schemas import EvidenceSourceType, ConfidenceLevel


class ConfidenceCalibrator:
    """
    Calibrates technical confidence and vertical/horizontal uncertainty
    based on the quality and provenance of the underlying sensor evidence.
    """

    @classmethod
    def calibrate(
        cls,
        evidence_sources: List[EvidenceSourceType],
        method: str,
        resolution_m: Optional[float] = None
    ) -> Tuple[float, ConfidenceLevel, float, List[str]]:
        """
        Returns:
            (confidence_score, confidence_level, uncertainty_m, assumptions)
        """
        assumptions = []

        if EvidenceSourceType.DSM_DTM in evidence_sources:
            res = resolution_m or 0.5
            unc = round(res * 0.5 + 0.15, 2)
            score = 0.94 if res <= 0.5 else 0.82
            level = ConfidenceLevel.HIGH if score >= 0.85 else ConfidenceLevel.MEDIUM
            assumptions.append(f"DSM-DTM raster difference calculated with ground resolution {res}m")
            return score, level, unc, assumptions

        elif EvidenceSourceType.POINT_CLOUD in evidence_sources:
            unc = 0.25
            score = 0.92
            level = ConfidenceLevel.HIGH
            assumptions.append("Extracted directly from classified airborne/UAV LiDAR point cloud")
            return score, level, unc, assumptions

        elif EvidenceSourceType.BUILDING_METADATA in evidence_sources:
            unc = 0.10
            score = 0.95
            level = ConfidenceLevel.HIGH
            assumptions.append("Obtained directly from municipal survey or registered architectural metadata")
            return score, level, unc, assumptions

        elif EvidenceSourceType.CAD_FLOOR_PLAN in evidence_sources:
            unc = 0.15
            score = 0.88
            level = ConfidenceLevel.HIGH
            assumptions.append("Derived from georeferenced architectural floor plan / BIM level definitions")
            return score, level, unc, assumptions

        elif EvidenceSourceType.DRONE_PHOTOGRAMMETRY in evidence_sources:
            unc = 0.45
            score = 0.80
            level = ConfidenceLevel.MEDIUM
            assumptions.append("Reconstructed from UAV drone photogrammetry dense surface mesh")
            return score, level, unc, assumptions

        elif EvidenceSourceType.ASSUMPTION_FALLBACK in evidence_sources:
            unc = 1.50
            score = 0.55
            level = ConfidenceLevel.LOW
            assumptions.append("Heuristic estimate derived using standard floor height multiplier assumptions")
            return score, level, unc, assumptions

        # Unknown fallback
        return 0.0, ConfidenceLevel.UNKNOWN, 5.0, ["Insufficient evidence to determine technical confidence"]
