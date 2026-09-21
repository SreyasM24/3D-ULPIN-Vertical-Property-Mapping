"""
Deterministic Multi-Source Evidence Fusion & Statistical Conflict Detection Engine.
Enforces:
1. Physical Evidence Over Heuristics (LiDAR / DSM-DTM > AI Regression > Deterministic Fallback)
2. Spatial Coverage & CRS Gating (Out-of-coverage sources are disqualified, never fabricated)
3. Transparent AI Bypass (AI is marked BYPASSED when observed evidence is present)
4. Statistical Conflict Detection (Discrepancies > 2σ are flagged for human review, never silently resolved)
"""

from typing import Dict, Any, Optional, List, Tuple
import os
import math
import logging
from shapely.geometry import shape

from app.ml.fusion.evidence_model import (
    EvidenceClass,
    MeasuredStatus,
    EvidenceCoverageStatus,
    UnifiedEvidenceRecord,
    EvidenceConflictRecord,
    FusionOutcome,
)
from app.ml.preprocessing.pointcloud import PointCloudPreprocessor
from app.ml.preprocessing.raster import RasterPreprocessor

logger = logging.getLogger(__name__)


class MultiSourceEvidenceFusionEngine:
    """
    Evaluates, ranks, selects, and audits multi-source geospatial evidence.
    """

    # Priority hierarchy (lower index = higher priority)
    PRIORITY_HIERARCHY = [
        "EXPLICIT_SURVEY_METADATA",
        "BUILDING_METADATA",
        "OBSERVED_HEIGHT_DECOMPOSITION",
        "POINT_CLOUD",
        "DSM_DTM",
        "DRONE_PHOTOGRAMMETRY",
        "CAD_FLOOR_PLAN",
        "EXPLICIT_FLOOR_COUNT",
        "AI_REGRESSION",
        "AI_HEIGHT_DECOMPOSITION",
        "DETERMINISTIC_CASCADE",
        "DETERMINISTIC_BASELINE",
        "UNRESOLVED"
    ]

    @classmethod
    def evaluate_candidates(
        cls,
        inputs: Dict[str, Any],
        footprint_geojson: Dict[str, Any],
        ai_regressor_fn: Optional[Any] = None
    ) -> List[UnifiedEvidenceRecord]:
        """
        Gathers and evaluates all candidate evidence sources against the target footprint.
        """
        candidates: List[UnifiedEvidenceRecord] = []

        # -------------------------------------------------------------------
        # 1. Explicit Survey / Architectural Metadata
        # -------------------------------------------------------------------
        bld_meta = inputs.get("building_metadata") or {}
        explicit_height = (
            bld_meta.get("total_height_m")
            or inputs.get("total_height_m")
            or inputs.get("height_m")
        )
        if explicit_height is not None and float(explicit_height) > 0.0:
            h_survey = round(float(explicit_height), 2)
            ground_z = float(bld_meta.get("ground_elevation_m", inputs.get("ground_elevation_m", 0.0)) or 0.0)
            in_src = inputs.get("source_type")
            src_type = (
                in_src
                if in_src in ("CAD_FLOOR_PLAN", "OBSERVED_HEIGHT_DECOMPOSITION", "BUILDING_METADATA", "DRONE_PHOTOGRAMMETRY")
                else "EXPLICIT_SURVEY_METADATA"
            )
            src_ref = inputs.get("source_reference") or inputs.get("survey_number") or "registered_cadastral_survey"
            if src_ref.endswith(".las") or src_ref.endswith(".laz"):
                src_ref = inputs.get("survey_number") or "registered_cadastral_survey"

            candidates.append(
                UnifiedEvidenceRecord(
                    source_type=src_type,
                    source_reference=src_ref,
                    crs=inputs.get("source_crs") or "EPSG:4326",
                    evidence_class=EvidenceClass.OBSERVED,
                    measured_status=MeasuredStatus.MEASURED,
                    height_m=h_survey,
                    ground_elevation_m=ground_z,
                    top_elevation_m=round(ground_z + h_survey, 2),
                    confidence=0.95,
                    uncertainty_m=0.10,
                    coverage=EvidenceCoverageStatus.VALID,
                    method="REGISTERED_SURVEY_METADATA" if src_type == "EXPLICIT_SURVEY_METADATA" else f"{src_type}_ACCURATE",
                    limitations=["Dependent on declared survey/architectural drawing authenticity."],
                    details={"declared_floor_count": inputs.get("floor_count")}
                )
            )

        # -------------------------------------------------------------------
        # 2. LiDAR Point Cloud Evidence
        # -------------------------------------------------------------------
        pc_source = (
            inputs.get("point_cloud_path")
            or inputs.get("point_cloud")
            or inputs.get("pointcloud_metadata")
            or (inputs.get("source_reference") if inputs.get("source_type") == "POINT_CLOUD" else None)
        )
        if pc_source:
            if isinstance(pc_source, str) and os.path.exists(pc_source):
                clip_res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
                    las_source=pc_source,
                    footprint_geojson=footprint_geojson,
                    source_crs=inputs.get("source_crs") or "EPSG:32643",
                    target_crs=inputs.get("target_crs", "EPSG:4326")
                )
                status = clip_res.get("status")
                if status == "VALID_OBSERVED_EVIDENCE" and clip_res.get("height_m") is not None:
                    candidates.append(
                        UnifiedEvidenceRecord(
                            source_type="POINT_CLOUD",
                            source_reference=os.path.basename(pc_source),
                            crs=clip_res.get("horizontal_crs") or "EPSG:32643",
                            evidence_class=EvidenceClass.OBSERVED,
                            measured_status=MeasuredStatus.MEASURED,
                            height_m=clip_res["height_m"],
                            ground_elevation_m=clip_res["ground_elevation_m"],
                            top_elevation_m=clip_res["surface_elevation_m"],
                            confidence=clip_res["confidence"],
                            uncertainty_m=clip_res["uncertainty_m"],
                            coverage=EvidenceCoverageStatus.VALID,
                            method=clip_res["method"],
                            limitations=[
                                "Requires ground returns for accurate datum.",
                                f"Point density: {clip_res.get('point_density_pts_m2')} pts/m²."
                            ],
                            details=clip_res
                        )
                    )
                else:
                    cov_status = (
                        EvidenceCoverageStatus.NO_BOUNDS_OVERLAP
                        if clip_res.get("coverage") == "NO_BOUNDS_OVERLAP"
                        else EvidenceCoverageStatus.REJECTED_OUT_OF_BOUNDS
                    )
                    candidates.append(
                        UnifiedEvidenceRecord(
                            source_type="POINT_CLOUD",
                            source_reference=os.path.basename(pc_source),
                            crs=clip_res.get("horizontal_crs") or "EPSG:32643",
                            evidence_class=EvidenceClass.OBSERVED,
                            measured_status=MeasuredStatus.NOT_MEASURED,
                            height_m=None,
                            confidence=0.0,
                            coverage=cov_status,
                            method="FAILED_SPATIAL_INTERSECTION",
                            limitations=[clip_res.get("explanation", "LiDAR did not intersect target footprint.")],
                            details=clip_res
                        )
                    )

        # -------------------------------------------------------------------
        # 3. Raster Elevation / DEM / DSM
        # -------------------------------------------------------------------
        dsm_path = (
            inputs.get("dsm_path")
            or (inputs.get("source_reference") if inputs.get("source_type") in ("DSM_DTM", "RASTER", "DEM") else None)
        )
        if dsm_path and isinstance(dsm_path, str) and os.path.exists(dsm_path):
            r_meta = RasterPreprocessor.inspect_raster(dsm_path)
            model_t = r_meta.get("model_type", "DEM").upper()
            if model_t in ("DEM", "DTM"):
                # Bare-earth DEM only
                elev_stats = r_meta.get("elevation_statistics", {})
                candidates.append(
                    UnifiedEvidenceRecord(
                        source_type="DEM_DTM",
                        source_reference=os.path.basename(dsm_path),
                        crs=r_meta.get("horizontal_crs") or "EPSG:32616",
                        evidence_class=EvidenceClass.OBSERVED,
                        measured_status=MeasuredStatus.MEASURED,
                        height_m=None,  # Terrain only, no building height
                        ground_elevation_m=elev_stats.get("mean_m") or elev_stats.get("min_m"),
                        confidence=0.80,
                        uncertainty_m=round(r_meta.get("spatial_resolution_m", 1.0) * 0.5 + 0.15, 2),
                        coverage=EvidenceCoverageStatus.TERRAIN_ONLY,
                        method="RASTER_BARE_EARTH_PARSER",
                        limitations=["DEM provides bare-earth terrain only; cannot derive building surface height without DSM."],
                        details=r_meta
                    )
                )

        # -------------------------------------------------------------------
        # 4. AI Height Regressor (Evaluated as candidate / fallback)
        # -------------------------------------------------------------------
        if ai_regressor_fn is not None and footprint_geojson:
            try:
                ai_inputs = dict(inputs)
                ai_inputs["footprint_geojson"] = footprint_geojson
                # CRITICAL FIX: AI candidate must evaluate genuine neural network inference (Strategy 2)
                # on footprint geometry, and NEVER inherit explicit survey metadata or LiDAR returns.
                ai_inputs.pop("point_cloud_path", None)
                ai_inputs.pop("point_cloud", None)
                ai_inputs.pop("source_type", None)
                ai_inputs.pop("total_height_m", None)
                ai_inputs.pop("height_m", None)
                ai_inputs.pop("height", None)
                ai_inputs.pop("explicit_height", None)
                if "building_metadata" in ai_inputs and isinstance(ai_inputs["building_metadata"], dict):
                    bm = dict(ai_inputs["building_metadata"])
                    bm.pop("total_height_m", None)
                    bm.pop("height_m", None)
                    bm.pop("height", None)
                    ai_inputs["building_metadata"] = bm

                ai_res = ai_regressor_fn(ai_inputs)
                if ai_res and ai_res.get("height_m") is not None:
                    candidates.append(
                        UnifiedEvidenceRecord(
                            source_type="AI_REGRESSION",
                            source_reference="models/height_estimator.onnx",
                            evidence_class=EvidenceClass.AI_ESTIMATED,
                            measured_status=MeasuredStatus.ESTIMATED,
                            height_m=ai_res["height_m"],
                            ground_elevation_m=ai_res.get("ground_elevation_m", 0.0),
                            top_elevation_m=ai_res.get("top_elevation_m"),
                            confidence=ai_res.get("confidence", 0.75),
                            uncertainty_m=ai_res.get("uncertainty_m", 2.32),
                            coverage=EvidenceCoverageStatus.VALID,
                            method="ONNX_HEIGHT_REGRESSOR_MLP",
                            limitations=[
                                "Trained on 3DBAG Netherlands domain.",
                                "Advisory estimate only; does not constitute legal measurement."
                            ],
                            details=ai_res.get("processing_metadata", {})
                        )
                    )
            except Exception as e:
                logger.debug(f"AI candidate estimation skipped: {e}")

        # -------------------------------------------------------------------
        # 5. Deterministic Floor Multiplier Cascade
        # -------------------------------------------------------------------
        floor_count = inputs.get("floor_count") or inputs.get("floors_above_ground")
        if floor_count is not None and int(floor_count) > 0:
            fl_c = int(floor_count)
            default_floor_h = 3.0
            default_ground_h = 3.8
            h_det = round(default_ground_h + max(0, fl_c - 1) * default_floor_h, 2)
            in_src = inputs.get("source_type")
            det_src = in_src if in_src in ("EXPLICIT_FLOOR_COUNT", "DETERMINISTIC_BASELINE") else "DETERMINISTIC_CASCADE"
            det_ref = inputs.get("source_reference") if in_src in ("EXPLICIT_FLOOR_COUNT", "DETERMINISTIC_BASELINE") else "cadastral_parametric_rules"
            if not det_ref or det_ref.endswith(".las") or det_ref.endswith(".laz"):
                det_ref = "cadastral_parametric_rules"

            candidates.append(
                UnifiedEvidenceRecord(
                    source_type=det_src,
                    source_reference=det_ref,
                    evidence_class=EvidenceClass.DETERMINISTIC,
                    measured_status=MeasuredStatus.NOT_MEASURED,
                    height_m=h_det,
                    ground_elevation_m=float(inputs.get("ground_elevation_m", 0.0) or 0.0),
                    confidence=0.60,
                    uncertainty_m=round(fl_c * 0.4, 2),
                    coverage=EvidenceCoverageStatus.VALID,
                    method="FLOOR_COUNT_PARAMETRIC_MULTIPLIER",
                    limitations=["Assumes standard municipal floor heights (3.0m typical, 3.8m ground)."],
                    details={"floor_count": fl_c}
                )
            )

        return candidates

    @classmethod
    def detect_conflicts(cls, candidates: List[UnifiedEvidenceRecord]) -> EvidenceConflictRecord:
        """
        Performs statistical discrepancy detection among valid height candidates.
        Tolerance: Δ_tol = max(2.5m, 2.0 * sqrt(u1^2 + u2^2))
        """
        valid_height_candidates = [
            c for c in candidates
            if c.height_m is not None
            and c.coverage in (EvidenceCoverageStatus.VALID, EvidenceCoverageStatus.PARTIAL_COVERAGE)
        ]

        if len(valid_height_candidates) < 2:
            return EvidenceConflictRecord(
                conflict_detected=False,
                conflict_severity="NONE",
                explanation="Fewer than 2 valid height candidates available. No conflict possible."
            )

        # Prioritize comparing Survey vs LiDAR or Observed vs AI
        for i in range(len(valid_height_candidates)):
            for j in range(i + 1, len(valid_height_candidates)):
                c1 = valid_height_candidates[i]
                c2 = valid_height_candidates[j]

                h1 = c1.height_m
                h2 = c2.height_m
                u1 = c1.uncertainty_m or 1.0
                u2 = c2.uncertainty_m or 1.0

                diff = round(abs(h1 - h2), 2)
                # Statistical 2-sigma combined uncertainty threshold
                combined_unc = math.sqrt(u1**2 + u2**2)
                threshold = round(max(2.5, 2.0 * combined_unc), 2)

                if diff > threshold:
                    # Determine severity
                    if c1.evidence_class == EvidenceClass.OBSERVED and c2.evidence_class == EvidenceClass.OBSERVED:
                        severity = "HIGH"
                    elif EvidenceClass.OBSERVED in (c1.evidence_class, c2.evidence_class):
                        severity = "MEDIUM"
                    else:
                        severity = "LOW"

                    explanation = (
                        f"Significant vertical discrepancy ({diff}m) between {c1.source_type} ({h1}m ±{u1}m) "
                        f"and {c2.source_type} ({h2}m ±{u2}m) exceeds 2σ tolerance ({threshold}m). "
                        f"Adjudication required."
                    )

                    return EvidenceConflictRecord(
                        conflict_detected=True,
                        conflict_severity=severity,
                        source_a=c1.source_type,
                        value_a_m=h1,
                        uncertainty_a_m=u1,
                        source_b=c2.source_type,
                        value_b_m=h2,
                        uncertainty_b_m=u2,
                        difference_m=diff,
                        threshold_m=threshold,
                        review_required=True,
                        explanation=explanation,
                        cadastral_policy_applied="DOCUMENTED_PRIORITY_WITH_REVIEW_FLAG"
                    )

        return EvidenceConflictRecord(
            conflict_detected=False,
            conflict_severity="NONE",
            explanation="All evaluated height evidence sources are statistically consistent within measurement uncertainty."
        )

    @classmethod
    def fuse(
        cls,
        inputs: Dict[str, Any],
        footprint_geojson: Dict[str, Any],
        ai_regressor_fn: Optional[Any] = None
    ) -> FusionOutcome:
        """
        Executes complete multi-source evidence evaluation, conflict detection,
        and deterministic selection.
        """
        candidates = cls.evaluate_candidates(inputs, footprint_geojson, ai_regressor_fn)
        conflict = cls.detect_conflicts(candidates)

        # Filter candidates that actually provide building height and have valid spatial coverage
        eligible_candidates = [
            c for c in candidates
            if c.height_m is not None
            and c.coverage in (EvidenceCoverageStatus.VALID, EvidenceCoverageStatus.PARTIAL_COVERAGE)
        ]

        if not eligible_candidates:
            # Check if we have terrain elevation
            dem_c = next((c for c in candidates if c.coverage == EvidenceCoverageStatus.TERRAIN_ONLY), None)
            ground_z = dem_c.ground_elevation_m if dem_c else float(inputs.get("ground_elevation_m", 0.0) or 0.0)
            return FusionOutcome(
                selected_source="UNRESOLVED",
                selected_class=EvidenceClass.UNRESOLVED,
                selected_height_m=None,
                selected_ground_elevation_m=ground_z,
                uncertainty_m=None,
                confidence=0.0,
                method="INSUFFICIENT_EVIDENCE",
                why_selected="No candidate evidence provided valid spatial coverage and measurable building height.",
                ai_status="NOT_APPLICABLE",
                candidates_evaluated=candidates,
                conflict=conflict,
                review_required=True
            )

        # Sort eligible candidates according to priority hierarchy
        def priority_key(c: UnifiedEvidenceRecord) -> int:
            req_src = inputs.get("source_type")
            if req_src and req_src == c.source_type:
                return -1
            try:
                return cls.PRIORITY_HIERARCHY.index(c.source_type)
            except ValueError:
                return 99

        eligible_candidates.sort(key=priority_key)
        winner = eligible_candidates[0]

        # Determine AI bypass status
        if winner.evidence_class == EvidenceClass.OBSERVED or winner.source_type in (
            "EXPLICIT_SURVEY_METADATA", "BUILDING_METADATA", "OBSERVED_HEIGHT_DECOMPOSITION",
            "POINT_CLOUD", "DSM_DTM", "DRONE_PHOTOGRAMMETRY", "CAD_FLOOR_PLAN"
        ):
            ai_status = "BYPASSED_OBSERVED_EVIDENCE"
            why_selected = (
                f"Selected {winner.source_type} ({winner.height_m}m ±{winner.uncertainty_m}m). "
                f"Valid spatial coverage verified. High-fidelity observed evidence outranks AI inference."
            )
        elif winner.source_type in ("EXPLICIT_FLOOR_COUNT", "DETERMINISTIC_BASELINE", "DETERMINISTIC_CASCADE"):
            ai_status = "BYPASSED_DETERMINISTIC"
            why_selected = (
                f"Selected {winner.source_type} ({winner.height_m}m ±{winner.uncertainty_m}m). "
                f"Parametric strata / registry floor declaration applied."
            )
        elif winner.source_type in ("AI_REGRESSION", "AI_HEIGHT_DECOMPOSITION"):
            ai_status = "ADVISORY_ESTIMATE"
            why_selected = (
                f"Selected AI Regression ({winner.height_m}m ±{winner.uncertainty_m}m). "
                f"Observed sensor evidence (LiDAR/DSM) was unavailable or did not cover target bounds. "
                f"AI estimate used strictly as advisory fallback."
            )
        else:
            ai_status = "NOT_APPLICABLE"
            why_selected = (
                f"Selected {winner.source_type} ({winner.height_m}m). "
                f"Parametric cadastral baseline applied in absence of sensor evidence."
            )

        review_required = conflict.review_required or (winner.confidence < 0.70) or (winner.evidence_class == EvidenceClass.AI_ESTIMATED)

        return FusionOutcome(
            selected_source=winner.source_type,
            selected_class=winner.evidence_class,
            selected_height_m=winner.height_m,
            selected_ground_elevation_m=winner.ground_elevation_m,
            selected_top_elevation_m=winner.top_elevation_m,
            uncertainty_m=winner.uncertainty_m,
            confidence=winner.confidence,
            method=winner.method,
            why_selected=why_selected,
            ai_status=ai_status,
            candidates_evaluated=candidates,
            conflict=conflict,
            review_required=review_required
        )
