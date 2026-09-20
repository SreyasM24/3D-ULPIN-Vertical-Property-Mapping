"""
Floor Features & Strata Decomposition.
Extracts floor counts, vertical strata slices, and level codes from architectural
drawings, BIM models, or height estimates.
"""

from typing import Dict, Any, Optional
from app.ml.models.floor_estimator import FloorEstimatorModel


class FloorFeatureExtractor:
    """Extracts floor strata features and estimates vertical building strata."""

    _model = FloorEstimatorModel()

    @classmethod
    def extract_floors(cls, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decomposes building envelope into vertical strata slices.
        """
        return cls._model.predict(inputs)
