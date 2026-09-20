"""
Floor Estimator & Vertical Strata Decomposition Engine.
SIH 26011 - 3D ULPIN & Vertical Property Mapping System.

Decomposes building vertical envelopes into candidate floor strata:
basement (underground), ground, upper floors (elevated), and rooftop structures.

CRITICAL ARCHITECTURAL PRINCIPLE:
Floor estimation is deterministic, rule-based, and evidence-driven.
It is NOT claimed as a trained ML neural network.
AI proposes height/footprint evidence; this deterministic engine constructs
auditable candidate vertical strata subject to legal cadastral constraints.
"""

from typing import Dict, Any, Optional, List, Tuple
import os
from app.ml.models.base import BaseFeatureModel
from app.ml.schemas import (
    ModelStatus,
    EvidenceSourceType,
    ConfidenceLevel,
    DataStage,
    VerticalFeatureResult,
)
from app.core.config import settings
from app.core.spatial_volume import VerticalClassification


class FloorEstimatorModel(BaseFeatureModel):
    """
    Evidence-driven deterministic vertical strata decomposition engine.
    Combines height evidence, architectural heuristics, and cadastral constraints
    under a strict 5-tier evidence hierarchy.
    """

    def __init__(self, weights_path: Optional[str] = None):
        super().__init__(
            model_name="FloorEstimator_StrataDecomposer",
            model_version="0.2.0",
            model_type="STRATA_DECOMPOSER",
            weights_path=weights_path
        )
        self.load()

    def load(self) -> bool:
        """
        Confirms the deterministic strata decomposition engine is ready.
        Honest declaration: requires NO trained neural network weights.
        """
        self.status = ModelStatus.ACTIVE
        return True

    def health(self) -> Dict[str, Any]:
        """Returns runtime health probe and honest architectural description."""
        base = super().health()
        base.update({
            "is_ready": True,
            "status": "ACTIVE",
            "is_ml_model": False,
            "engine": "EVIDENCE_BASED_STRATA_DECOMPOSER",
            "methodology": "DETERMINISTIC_PARAMETRIC_DECOMPOSITION",
            "evidence_hierarchy_levels": 5,
            "notes": (
                "Deterministic evidence-driven strata decomposition engine. "
                "Explicitly not a trained neural network; combines sensor evidence "
                "with cadastral constraints."
            )
        })
        return base

    def metadata(self) -> Dict[str, Any]:
        """Exposes engine specification, configuration defaults, and evidence hierarchy."""
        base = super().metadata()
        base.update({
            "is_ready": True,
            "status": "ACTIVE",
            "requires_weights": False,
            "is_ml_model": False,
            "supported_backends": ["DETERMINISTIC_RULES", "CAD_FLOOR_PARSER"],
            "evidence_hierarchy": [
                "TIER_1: EXPLICIT_FLOOR_COUNT",
                "TIER_2: ARCHITECTURAL_FLOOR_PLAN",
                "TIER_3: OBSERVED_HEIGHT_DECOMPOSITION",
                "TIER_4: AI_HEIGHT_DECOMPOSITION",
                "TIER_5: DETERMINISTIC_BASELINE",
                "TIER_6: UNRESOLVED"
            ]
        })
        return base

    def predict(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decomposes building vertical envelope into candidate floor strata
        using a strict 5-tier evidence hierarchy.
        """
        # Read configurable floor height parameters
        cfg = inputs.get("floor_config") or {}
        min_fl_h = float(cfg.get("min_floor_height_m", getattr(settings, "MIN_FLOOR_HEIGHT_M", 2.6)))
        typical_fl_h = float(cfg.get("typical_floor_height_m", getattr(settings, "DEFAULT_FLOOR_HEIGHT_M", 3.0)))
        max_fl_h = float(cfg.get("max_floor_height_m", getattr(settings, "MAX_FLOOR_HEIGHT_M", 4.5)))
        ground_fl_h = float(cfg.get("ground_floor_height_m", getattr(settings, "DEFAULT_GROUND_FLOOR_HEIGHT_M", 3.8)))
        base_fl_h = float(cfg.get("basement_floor_height_m", getattr(settings, "DEFAULT_BASEMENT_HEIGHT_M", 3.5)))
        parapet_h = float(cfg.get("roof_parapet_allowance_m", 0.8))

        ground_z = float(inputs.get("ground_elevation_m", 0.0) or 0.0)
        basement_floors = int(inputs.get("basement_floors", inputs.get("basement_count", 0)) or 0)
        
        # Raw height inputs
        raw_height = inputs.get("total_height_m") if inputs.get("total_height_m") is not None else inputs.get("height_m")
        height_m = float(raw_height) if raw_height is not None else None
        
        # Source provenance of height
        height_source = inputs.get("height_source") or inputs.get("source")
        height_uncertainty = inputs.get("height_uncertainty_m")
        
        # Explicit floor count inputs
        raw_floors = inputs.get("floor_count") if inputs.get("floor_count") is not None else inputs.get("floors_above_ground")
        explicit_floor_count = int(raw_floors) if raw_floors is not None else None

        # ====================================================================
        # TIER 2: ARCHITECTURAL / CAD / BIM FLOOR INFORMATION
        # ====================================================================
        explicit_floors = inputs.get("floors") or inputs.get("floor_plans") or inputs.get("bim_data")
        if explicit_floors and isinstance(explicit_floors, list) and len(explicit_floors) > 0:
            strata: List[VerticalFeatureResult] = []
            for f in explicit_floors:
                z_min = float(f["z_min"])
                z_max = float(f["z_max"])
                code = f.get("level_code", f"L{f.get('level_number', 1):02d}")
                v_class = "UNDERGROUND" if z_max <= ground_z + 0.1 else ("GROUND_LEVEL" if z_min <= ground_z < z_max else "ELEVATED")
                strata.append(
                    VerticalFeatureResult(
                        level_code=code,
                        z_min=round(z_min, 2),
                        z_max=round(z_max, 2),
                        estimated_height_m=round(z_max - z_min, 2),
                        classification=v_class,
                        confidence=0.95,
                        confidence_level=ConfidenceLevel.HIGH,
                        uncertainty_m=0.05,
                        source=EvidenceSourceType.CAD_FLOOR_PLAN,
                        stage=DataStage.OBSERVED
                    )
                )
            return {
                "estimated_floor_count": len(strata),
                "strata": strata,
                "confidence": 0.95,
                "confidence_level": ConfidenceLevel.HIGH,
                "uncertainty_m": 0.05,
                "method": "ARCHITECTURAL_FLOOR_PLAN",
                "source": EvidenceSourceType.CAD_FLOOR_PLAN,
                "evidence_tier": 2,
                "requires_review": False,
                "candidates": {"typical": len(strata)},
                "assumptions": ["Explicit architectural drawing / BIM elevations parsed directly"]
            }

        # Guard: If no height and no floor count, or impossible negative height
        if (height_m is None or height_m <= 0.0) and explicit_floor_count is None:
            return {
                "estimated_floor_count": 0,
                "strata": [],
                "confidence": 0.0,
                "confidence_level": ConfidenceLevel.UNKNOWN,
                "uncertainty_m": None,
                "method": "UNRESOLVED",
                "source": EvidenceSourceType.UNRESOLVED,
                "evidence_tier": 6,
                "requires_review": True,
                "candidates": {},
                "assumptions": ["Insufficient height and floor count data to establish vertical strata"]
            }

        # Guard: Impossible single floor height
        if height_m is not None and height_m > 0 and height_m < min_fl_h and explicit_floor_count is None:
            return {
                "estimated_floor_count": 0,
                "strata": [],
                "confidence": 0.0,
                "confidence_level": ConfidenceLevel.UNKNOWN,
                "uncertainty_m": None,
                "method": "UNRESOLVED",
                "source": EvidenceSourceType.UNRESOLVED,
                "evidence_tier": 6,
                "requires_review": True,
                "candidates": {},
                "assumptions": [f"Building height ({height_m:.2f}m) is below minimum occupiable floor height ({min_fl_h:.2f}m)"]
            }

        # ====================================================================
        # DETERMINE EVIDENCE TIER AND SOURCE CLASSIFICATION
        # ====================================================================
        is_explicit_survey = (
            explicit_floor_count is not None and (
                str(height_source).upper() in ("EXPLICIT_SURVEY", "EXPLICIT_FLOOR_COUNT", "SURVEY_METADATA", "CADASTRAL_RECORD")
                or inputs.get("is_survey_record") is True
                or inputs.get("source") in ("EXPLICIT_SURVEY", "EXPLICIT_FLOOR_COUNT")
                or (not height_source and not inputs.get("source"))
            )
        )

        observed_height_tokens = {
            "OBSERVED_ELEVATION_EVIDENCE", "OBSERVED_SURVEY_METADATA", "OBSERVED_LIDAR",
            "POINT_CLOUD", "DSM_DTM", "DSM_DTM_DIFFERENCE", "EXPLICIT_METADATA"
        }
        ai_height_tokens = {
            "AI_REGRESSION", "AI_HEIGHT_ESTIMATE", "AI_TABULAR_REGRESSION"
        }

        h_source_str = str(height_source).upper() if height_source else ""

        if is_explicit_survey:
            evidence_tier = 1
            source_enum = EvidenceSourceType.EXPLICIT_FLOOR_COUNT
            method_str = "EXPLICIT_FLOOR_COUNT"
            base_confidence = 0.98
            base_uncertainty = 0.05
            requires_review = False
        elif any(token in h_source_str for token in observed_height_tokens):
            evidence_tier = 3
            source_enum = EvidenceSourceType.OBSERVED_HEIGHT_DECOMPOSITION
            method_str = "OBSERVED_HEIGHT_DECOMPOSITION"
            base_confidence = 0.88
            base_uncertainty = 0.30
            requires_review = False
        elif any(token in h_source_str for token in ai_height_tokens):
            evidence_tier = 4
            source_enum = EvidenceSourceType.AI_HEIGHT_DECOMPOSITION
            method_str = "AI_HEIGHT_DECOMPOSITION"
            base_confidence = 0.68
            base_uncertainty = 0.80
            requires_review = True
        else:
            evidence_tier = 5
            source_enum = EvidenceSourceType.DETERMINISTIC_BASELINE
            method_str = "DETERMINISTIC_BASELINE"
            base_confidence = 0.55
            base_uncertainty = 1.00
            requires_review = True

        assumptions: List[str] = []

        # ====================================================================
        # CANDIDATE PLAUSIBILITY ANALYSIS (From Height)
        # ====================================================================
        candidates: Dict[str, int] = {}
        if height_m is not None and height_m > 0:
            eff_height = max(height_m - parapet_h, height_m * 0.9) if height_m > (ground_fl_h + typical_fl_h) else height_m
            
            # 1. Conservative (higher floor heights, fewer floors)
            rem_cons = max(0.0, eff_height - ground_fl_h)
            cand_cons = 1 + int(rem_cons / max_fl_h)
            candidates["conservative"] = max(1, cand_cons)

            # 2. Typical (standard heights)
            rem_typ = max(0.0, eff_height - ground_fl_h)
            cand_typ = 1 + max(0, round(rem_typ / typical_fl_h))
            candidates["typical"] = max(1, cand_typ)

            # 3. Dense (minimum compliant floor heights)
            rem_dense = max(0.0, eff_height - min_fl_h)
            cand_dense = 1 + int(rem_dense / min_fl_h)
            candidates["dense"] = max(1, cand_dense)

        # ====================================================================
        # RESOLVE ABOVE-GROUND FLOORS AND FLOOR SLICE HEIGHTS
        # ====================================================================
        if explicit_floor_count is not None:
            floors_above = max(1, explicit_floor_count)
            assumptions.append(f"Used explicit floor count ({floors_above} floors above ground)")
        elif height_m is not None:
            floors_above = candidates.get("typical", 1)
            assumptions.append(
                f"Decomposed height ({height_m:.2f}m) into {floors_above} above-ground floors "
                f"(candidates: conservative={candidates.get('conservative')}, "
                f"typical={candidates.get('typical')}, dense={candidates.get('dense')})"
            )
        else:
            floors_above = 1

        # Check for ambiguity in candidates (only when estimating from height, not explicit survey)
        if not is_explicit_survey and candidates and candidates.get("conservative") != candidates.get("dense"):
            if candidates.get("dense", 0) - candidates.get("conservative", 0) >= 2:
                assumptions.append("Significant floor count ambiguity across conservative vs dense parameters")
                base_confidence -= 0.05
                requires_review = True

        # Check for height/floor count impossibility
        if height_m is not None and floors_above > 0:
            min_possible_h = floors_above * min_fl_h - 0.5
            max_possible_h = floors_above * max_fl_h + 3.0
            if height_m < min_possible_h:
                assumptions.append(
                    f"Warning: Building height {height_m:.2f}m is physically insufficient for {floors_above} floors "
                    f"(min required: {min_possible_h:.2f}m at {min_fl_h}m/floor)"
                )
                base_confidence -= 0.25
                requires_review = True
            elif height_m > max_possible_h:
                assumptions.append(
                    f"Warning: Building height {height_m:.2f}m is exceptionally high for {floors_above} floors "
                    f"(exceeds {max_possible_h:.2f}m at {max_fl_h}m/floor)"
                )
                base_confidence -= 0.15
                requires_review = True

        # Calculate actual floor heights
        if height_m is not None:
            if floors_above == 1:
                actual_ground_h = round(height_m, 2)
                upper_floor_h = 0.0
            else:
                # Distribute height: ground floor gets standard or proportional
                if height_m <= ground_fl_h:
                    actual_ground_h = round(height_m / floors_above, 2)
                    upper_floor_h = round(height_m / floors_above, 2)
                else:
                    actual_ground_h = round(ground_fl_h, 2)
                    upper_floor_h = round((height_m - actual_ground_h) / (floors_above - 1), 2)
        else:
            # When height is not provided, use default heights
            actual_ground_h = ground_fl_h
            upper_floor_h = typical_fl_h

        # ====================================================================
        # CONSTRUCT VERTICAL STRATA SLICES (Basement -> Ground -> Upper)
        # ====================================================================
        strata_list: List[VerticalFeatureResult] = []

        # 1. Basements (below ground elevation)
        if basement_floors > 0:
            current_z = ground_z
            for b_idx in range(1, basement_floors + 1):
                b_code = f"B{b_idx:02d}"
                b_z_min = round(current_z - base_fl_h, 2)
                b_z_max = round(current_z, 2)
                strata_list.insert(0, VerticalFeatureResult(
                    level_code=b_code,
                    z_min=b_z_min,
                    z_max=b_z_max,
                    estimated_height_m=base_fl_h,
                    classification="UNDERGROUND",
                    confidence=round(max(0.4, base_confidence - 0.05), 2),
                    confidence_level=ConfidenceLevel.HIGH if base_confidence >= 0.8 else ConfidenceLevel.MEDIUM,
                    uncertainty_m=round(base_uncertainty + 0.1, 2),
                    source=source_enum,
                    stage=DataStage.ESTIMATED
                ))
                current_z = b_z_min
            assumptions.append(f"Decomposed {basement_floors} basement levels below ground datum ({base_fl_h}m per sub-level)")

        # 2. Ground Floor
        current_z = ground_z
        ground_ceiling = round(current_z + actual_ground_h, 2)
        strata_list.append(VerticalFeatureResult(
            level_code="G00",
            z_min=round(current_z, 2),
            z_max=ground_ceiling,
            estimated_height_m=actual_ground_h,
            classification="GROUND_LEVEL",
            confidence=round(base_confidence, 2),
            confidence_level=ConfidenceLevel.HIGH if base_confidence >= 0.8 else (
                ConfidenceLevel.MEDIUM if base_confidence >= 0.6 else ConfidenceLevel.LOW
            ),
            uncertainty_m=round(base_uncertainty, 2),
            source=source_enum,
            stage=DataStage.ESTIMATED
        ))
        current_z = ground_ceiling

        # 3. Upper Floors
        for fl_idx in range(1, floors_above):
            fl_code = f"L{fl_idx:02d}"
            fl_top = round(current_z + upper_floor_h, 2)
            strata_list.append(VerticalFeatureResult(
                level_code=fl_code,
                z_min=round(current_z, 2),
                z_max=fl_top,
                estimated_height_m=upper_floor_h,
                classification="ELEVATED",
                confidence=round(base_confidence, 2),
                confidence_level=ConfidenceLevel.HIGH if base_confidence >= 0.8 else (
                    ConfidenceLevel.MEDIUM if base_confidence >= 0.6 else ConfidenceLevel.LOW
                ),
                uncertainty_m=round(base_uncertainty, 2),
                source=source_enum,
                stage=DataStage.ESTIMATED
            ))
            current_z = fl_top

        # Uncertainty penalty if height uncertainty is provided
        if height_uncertainty is not None and height_uncertainty > 1.0:
            penalty = min(0.15, (height_uncertainty - 1.0) * 0.05)
            base_confidence -= penalty
            base_uncertainty += height_uncertainty * 0.2
            assumptions.append(f"Confidence reduced by {penalty:.2f} due to height sensor uncertainty (±{height_uncertainty:.2f}m)")

        final_confidence = round(max(0.1, min(0.99, base_confidence)), 3)
        if final_confidence >= 0.80:
            final_level = ConfidenceLevel.HIGH
        elif final_confidence >= 0.55:
            final_level = ConfidenceLevel.MEDIUM
        elif final_confidence > 0.0:
            final_level = ConfidenceLevel.LOW
        else:
            final_level = ConfidenceLevel.UNKNOWN

        total_floors = basement_floors + floors_above

        return {
            "estimated_floor_count": total_floors,
            "floors_above_ground": floors_above,
            "basement_floors": basement_floors,
            "strata": strata_list,
            "confidence": final_confidence,
            "confidence_level": final_level,
            "uncertainty_m": round(base_uncertainty, 2),
            "method": method_str,
            "source": source_enum,
            "evidence_tier": evidence_tier,
            "requires_review": requires_review or (final_confidence < 0.70),
            "candidates": candidates,
            "config": {
                "min_floor_height_m": min_fl_h,
                "typical_floor_height_m": typical_fl_h,
                "max_floor_height_m": max_fl_h,
                "ground_floor_height_m": ground_fl_h,
                "basement_floor_height_m": base_fl_h,
                "roof_parapet_allowance_m": parapet_h
            },
            "assumptions": assumptions
        }
