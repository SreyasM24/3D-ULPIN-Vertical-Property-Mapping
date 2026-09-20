"""
ML Anomaly Detection Extension Hook.
Provides a clean interface for future machine learning / statistical anomaly detection
without coupling the deterministic geometric validation engine to ML or LLMs.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class CadastralAnomalyDetectionHook(ABC):
    """
    Abstract interface for future ML-assisted cadastral anomaly detection.
    Guarantees architectural separation: ML models can flag candidate anomalies,
    but cannot override deterministic spatial/topological rules.
    """

    @abstractmethod
    def detect_anomalies(self, digital_twin_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scans digital twin records for statistical or spatial pattern anomalies.
        Returns a list of advisory anomaly notices.
        """
        pass


class DeterministicDefaultAnomalyHook(CadastralAnomalyDetectionHook):
    """
    Default production implementation: purely deterministic, no ML/LLM dependencies.
    Performs basic heuristic statistical sanity checks.
    """

    def detect_anomalies(self, digital_twin_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        anomalies = []
        summary = digital_twin_data.get("summary", {})
        total_units = summary.get("total_units", 0)
        total_volume = summary.get("total_volume_cu_m", 0.0)

        # Statistical sanity check: average unit volume
        if total_units > 0 and total_volume > 0:
            avg_vol = total_volume / total_units
            if avg_vol < 15.0:
                anomalies.append({
                    "hook": "STATISTICAL_UNIT_VOLUME_OUTLIER",
                    "severity": "ADVISORY",
                    "explanation": f"Average unit volume ({avg_vol:.1f} m³) is unusually small for typical urban dwellings.",
                    "confidence": 0.85
                })
            elif avg_vol > 5000.0:
                anomalies.append({
                    "hook": "STATISTICAL_UNIT_VOLUME_OUTLIER",
                    "severity": "ADVISORY",
                    "explanation": f"Average unit volume ({avg_vol:.1f} m³) is unusually large; may represent industrial halls.",
                    "confidence": 0.80
                })

        return anomalies


class MLCadastralAnomalyAdapter(CadastralAnomalyDetectionHook):
    """
    Adapter bridging ML feature models and digital twin anomaly detection.
    Combines deterministic statistical sanity checks with ML anomaly inspection.
    """

    def detect_anomalies(self, digital_twin_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        from app.ml.models.anomaly_detector import CadastralMLAnomalyDetector
        detector = CadastralMLAnomalyDetector()
        ml_anomalies = detector.detect_anomalies(digital_twin_data)

        # Also run baseline statistical checks
        baseline = DeterministicDefaultAnomalyHook().detect_anomalies(digital_twin_data)
        return baseline + ml_anomalies

