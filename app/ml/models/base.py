"""
Base AI/ML Feature Model Interface.
Establishes standardized lifecycle (load, predict, health, metadata)
supporting future PyTorch / ONNX Runtime / TensorFlow model backends.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.ml.schemas import ModelStatus


class BaseFeatureModel(ABC):
    """
    Abstract contract for all AI/ML models in the 3D cadastral feature pipeline.
    Guarantees that unconfigured models report status='NOT_CONFIGURED' rather than
    fabricating predictions or throwing unhandled errors.
    """

    def __init__(
        self,
        model_name: str,
        model_version: str = "0.1.0",
        model_type: str = "FEATURE_EXTRACTOR",
        weights_path: Optional[str] = None
    ):
        self.model_name = model_name
        self.model_version = model_version
        self.model_type = model_type
        self.weights_path = weights_path
        self.status: ModelStatus = ModelStatus.NOT_CONFIGURED
        self.loaded_at: Optional[datetime] = None

    @abstractmethod
    def load(self) -> bool:
        """Loads model weights or confirms weights configuration."""
        pass

    @abstractmethod
    def predict(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Executes inference or falls back gracefully."""
        pass

    def health(self) -> Dict[str, Any]:
        """Returns health probe and runtime readiness of the model."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_type": self.model_type,
            "status": self.status.value,
            "is_ready": self.status == ModelStatus.ACTIVE,
            "weights_path": self.weights_path,
            "loaded_at": self.loaded_at.isoformat() if self.loaded_at else None
        }

    def metadata(self) -> Dict[str, Any]:
        """Exposes model descriptor, supported input modalities, and provenance."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_type": self.model_type,
            "status": self.status.value,
            "requires_weights": True,
            "supported_backends": ["ONNX", "PyTorch", "DeterministicFallback"]
        }
