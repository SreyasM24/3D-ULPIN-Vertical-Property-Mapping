"""
Base Ingestion Adapter Interface for Cadastral Datasets.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import hashlib
from app.schemas.provenance import IngestionResult, DatasetProvenance, SourceType


def compute_sha256_bytes(content: bytes) -> str:
    """Computes SHA-256 hex digest of raw binary content."""
    return hashlib.sha256(content).hexdigest()


def compute_sha256_str(content: str) -> str:
    """Computes SHA-256 hex digest of string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class BaseIngestionAdapter(ABC):
    """Abstract base class for all spatial data ingestion adapters."""

    def __init__(self, source_name: str, source_type: SourceType):
        self.source_name = source_name
        self.source_type = source_type

    @abstractmethod
    def ingest(self, content: Any, options: Optional[Dict[str, Any]] = None) -> IngestionResult:
        """Ingests raw content and returns an IngestionResult with full provenance."""
        pass
