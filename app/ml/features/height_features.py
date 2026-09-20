"""
Height Feature Extraction & Strategy Resolution.
Orchestrates multi-strategy building height determination and uncertainty quantification.
"""

from typing import Dict, Any, Optional
from app.ml.models.height_estimator import HeightEstimatorModel


class HeightFeatureExtractor:
    """Extracts height features from heterogeneous remote sensing and metadata inputs."""

    _model = HeightEstimatorModel()

    @classmethod
    def extract_height(cls, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs multi-strategy height estimator:
        OBSERVED_EVIDENCE (LiDAR/DSM/Metadata) -> AI_REGRESSION (ONNX) -> FLOOR_COUNT_FALLBACK -> UNKNOWN
        """
        model = HeightEstimatorModel()
        return model.predict(inputs)
