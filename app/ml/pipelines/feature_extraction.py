"""
End-to-End ML/AI Feature Extraction Pipeline.
Coordinates source inspection, preprocessing, building metric extraction,
multi-strategy height estimation, strata decomposition, confidence calibration,
and handoff to deterministic cadastral validation.
"""

from typing import Dict, Any, Optional, List
from app.ml.schemas import (
    PipelineResult,
    BuildingDetectionResult,
    BuildingFeatureResult,
    VerticalFeatureResult,
    EvidenceSourceType,
    ConfidenceLevel,
    DataStage,
    SourceProvenance,
    AnomalyResult,
)
from app.ml.models.building_detector import BuildingDetector
from app.ml.models.height_estimator import HeightEstimatorModel
from app.ml.models.floor_estimator import FloorEstimatorModel
from app.ml.models.anomaly_detector import CadastralMLAnomalyDetector
from app.ml.features.building_features import BuildingFeatureExtractor
from app.ml.features.vertical_features import VerticalFeatureExtractor
from app.ml.confidence.calibration import ConfidenceCalibrator
from app.ml.pipelines.vertical_cadastre import VerticalCadastreFeatureService
from app.ml.fusion.fusion_engine import MultiSourceEvidenceFusionEngine


class FeatureExtractionPipeline:
    """
    Orchestrates automated 3D feature extraction from remote sensing and architectural inputs.
    Strictly safeguards that estimates must undergo deterministic validation.
    """

    def __init__(self):
        self.building_detector = BuildingDetector()
        self.height_estimator = HeightEstimatorModel()
        self.floor_estimator = FloorEstimatorModel()
        self.anomaly_detector = CadastralMLAnomalyDetector()

    def process(self, inputs: Dict[str, Any]) -> PipelineResult:
        warnings: List[str] = []
        provenance: List[SourceProvenance] = []
        anomalies: List[AnomalyResult] = []

        # 1. Building Detection / Footprint Resolution
        detection: BuildingDetectionResult = self.building_detector.predict(inputs)
        footprint_geojson = detection.footprint_geojson
        has_footprint = bool(
            footprint_geojson and
            footprint_geojson.get("coordinates") and
            len(footprint_geojson["coordinates"]) > 0
        )

        if not has_footprint:
            warnings.append("No valid building footprint could be extracted or resolved.")
            return PipelineResult(
                status="FAILED",
                features=None,
                vertical_proposals=[],
                confidence=0.0,
                confidence_level=ConfidenceLevel.UNKNOWN,
                warnings=warnings,
                provenance=provenance,
                anomalies=anomalies,
                validation_ready=False
            )

        bld_mode = detection.processing_metadata.get("mode", "PASS_THROUGH_OBSERVED")
        provenance.append(
            SourceProvenance(
                source_type=detection.source,
                source_id=f"FOOTPRINT_{bld_mode}",
                method=bld_mode,
                confidence=detection.confidence or 0.85,
                uncertainty_m=detection.uncertainty_m
            )
        )

        # 2. Multi-Source Evidence Fusion & Height Estimation
        fusion_outcome = MultiSourceEvidenceFusionEngine.fuse(
            inputs=inputs,
            footprint_geojson=footprint_geojson,
            ai_regressor_fn=self.height_estimator.predict
        )
        height_res = self.height_estimator.predict(inputs)

        # If fusion selected a specific source, adopt its height and ground elevation
        if fusion_outcome.selected_height_m is not None:
            height_m = fusion_outcome.selected_height_m
            ground_z = fusion_outcome.selected_ground_elevation_m or 0.0
            height_uncertainty = fusion_outcome.uncertainty_m
            height_confidence = fusion_outcome.confidence
            height_method = fusion_outcome.method
        else:
            height_m = height_res.get("height_m")
            ground_z = height_res.get("ground_elevation_m", 0.0) or 0.0
            height_uncertainty = height_res.get("uncertainty_m")
            height_confidence = height_res.get("confidence", 0.7)
            height_method = height_res.get("method", "UNKNOWN")

        src_map = {
            "EXPLICIT_SURVEY_METADATA": EvidenceSourceType.BUILDING_METADATA,
            "POINT_CLOUD": EvidenceSourceType.POINT_CLOUD,
            "DSM_DTM": EvidenceSourceType.DSM_DTM,
            "DRONE_PHOTOGRAMMETRY": EvidenceSourceType.DRONE_PHOTOGRAMMETRY,
            "CAD_FLOOR_PLAN": EvidenceSourceType.CAD_FLOOR_PLAN,
            "AI_REGRESSION": EvidenceSourceType.DRONE_PHOTOGRAMMETRY,
            "DETERMINISTIC_CASCADE": EvidenceSourceType.ASSUMPTION_FALLBACK,
        }
        height_source = src_map.get(fusion_outcome.selected_source, height_res.get("source", EvidenceSourceType.ASSUMPTION_FALLBACK))

        # Check for evidence conflict
        if fusion_outcome.conflict.conflict_detected:
            warnings.append(f"EVIDENCE_CONFLICT: {fusion_outcome.conflict.explanation}")
            anomalies.append(
                AnomalyResult(
                    anomaly_type="EVIDENCE_CONFLICT",
                    severity=fusion_outcome.conflict.conflict_severity,
                    confidence=0.95,
                    explanation=fusion_outcome.conflict.explanation,
                    requires_review=True
                )
            )

        if height_m is None:
            warnings.append("Building height could not be established from available sensors or metadata.")
        else:
            sel_cand = next((c for c in fusion_outcome.candidates_evaluated if c.source_type == fusion_outcome.selected_source), None)
            cand_details = sel_cand.details if sel_cand else (height_res.get("evidence_metadata") or {})
            provenance.append(
                SourceProvenance(
                    source_type=height_source,
                    source_id=f"HEIGHT_{height_method}",
                    method=height_method,
                    confidence=height_confidence,
                    uncertainty_m=height_uncertainty,
                    coverage=sel_cand.coverage.value if sel_cand else height_res.get("coverage", "VALID"),
                    uncertainty_basis=cand_details.get("uncertainty_basis") or height_res.get("uncertainty_basis"),
                    metadata={
                        **cand_details,
                        "source_reference": sel_cand.source_reference if sel_cand else height_res.get("source_reference"),
                        "why_selected": fusion_outcome.why_selected,
                        "ai_status": fusion_outcome.ai_status,
                        "conflict_detected": fusion_outcome.conflict.conflict_detected,
                        "conflict_severity": fusion_outcome.conflict.conflict_severity,
                        "conflict_details": fusion_outcome.conflict.model_dump(),
                    }
                )
            )

        # 3. Floor Strata Decomposition
        floor_inputs = dict(inputs)
        floor_inputs["height_m"] = height_m
        floor_inputs["ground_elevation_m"] = ground_z
        floor_inputs["height_source"] = height_source
        floor_inputs["height_method"] = height_method
        floor_inputs["height_uncertainty_m"] = height_uncertainty
        floor_res = self.floor_estimator.predict(floor_inputs)
        strata: List[VerticalFeatureResult] = floor_res.get("strata", [])
        floor_count = floor_res.get("estimated_floor_count", len(strata))
        floor_source = floor_res.get("source", EvidenceSourceType.DETERMINISTIC_BASELINE)
        floor_method = floor_res.get("method", "UNKNOWN")

        if floor_count > 0:
            provenance.append(
                SourceProvenance(
                    source_type=floor_source,
                    source_id=f"FLOOR_{floor_method}",
                    method=floor_method,
                    confidence=floor_res.get("confidence", 0.7),
                    uncertainty_m=floor_res.get("uncertainty_m")
                )
            )

        if not strata:
            warnings.append("Vertical strata could not be decomposed due to insufficient height data.")
        if floor_res.get("assumptions"):
            warnings.extend(floor_res["assumptions"])

        # 4. Building Feature Extraction (Projected UTM Metrics)
        building_features = BuildingFeatureExtractor.extract_features(
            footprint_geojson=footprint_geojson,
            height_m=height_m,
            floor_count=floor_count,
            ground_elevation_m=ground_z,
            source_type=detection.source,
            confidence=detection.confidence or 0.85,
            uncertainty_m=detection.uncertainty_m
        )

        # 5. Anomaly Inspection
        anomaly_inputs = {
            "height_m": height_m,
            "floor_count": floor_count,
            "footprint_geojson": footprint_geojson
        }
        detected_anomalies = self.anomaly_detector.predict(anomaly_inputs)
        anomalies.extend(detected_anomalies)

        # 6. Confidence & Uncertainty Calibration
        evidence_sources = [detection.source]
        if height_source:
            evidence_sources.append(height_source)

        conf_score, conf_level, uncertainty_m, assumptions = ConfidenceCalibrator.calibrate(
            evidence_sources=evidence_sources,
            method=height_method
        )
        warnings.extend(assumptions)

        # 7. Verification Readiness Handoff
        validation_ready = bool(has_footprint and height_m and len(strata) > 0)
        status = "SUCCESS" if validation_ready else ("PARTIAL" if has_footprint else "FAILED")

        return PipelineResult(
            status=status,
            features=building_features,
            vertical_proposals=strata,
            confidence=conf_score,
            confidence_level=conf_level,
            uncertainty_m=uncertainty_m,
            warnings=warnings,
            provenance=provenance,
            anomalies=anomalies,
            validation_ready=validation_ready,
            fusion_outcome=fusion_outcome.model_dump(),
            conflict_detected=fusion_outcome.conflict.conflict_detected
        )
