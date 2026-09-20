"""
Vertical Cadastral Features & Volumetric Envelopes.
Constructs candidate 3D vertical property volumes reusing existing
SpatialVolume, PrismVolume, and FloorEngine.

Supports single-floor units, duplex/multi-floor units, vertical utility shafts,
elevator cores, and parking ramps with continuous volumetric bounds.
"""

from typing import List, Dict, Any, Optional
from app.ml.schemas import (
    VerticalFeatureResult,
    EvidenceSourceType,
    ConfidenceLevel,
    DataStage,
)
from app.core.spatial_volume import (
    PrismVolume,
    classify_vertical_position,
    VerticalClassification,
)
from app.services.floor_engine import FloorEngine


class VerticalFeatureExtractor:
    """
    Constructs candidate volumetric 3D property spaces from footprint and vertical strata.
    Reuses existing PrismVolume and FloorEngine without code duplication.
    """

    @classmethod
    def propose_vertical_units(
        cls,
        footprint_geojson: Dict[str, Any],
        strata_levels: List[VerticalFeatureResult],
        units_per_floor: int = 1,
        ground_elevation_m: float = 0.0,
        multi_floor_configs: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Proposes candidate vertical units for each stratum level, plus any
        multi-floor duplex or vertical infrastructure units.
        """
        proposed_units: List[Dict[str, Any]] = []
        level_map: Dict[str, VerticalFeatureResult] = {fl.level_code: fl for fl in strata_levels}

        # 1. Standard single-floor units
        for fl in strata_levels:
            level_code = fl.level_code
            z_min = fl.z_min
            z_max = fl.z_max
            h = fl.estimated_height_m

            # Calculate metric prism volume using existing PrismVolume
            try:
                prism = PrismVolume(
                    footprint_geojson=footprint_geojson,
                    z_min=z_min,
                    z_max=z_max,
                    ground_elevation_m=ground_elevation_m
                )
                carpet_area = prism.area_sqm
                volume_m3 = prism.volume_cu_m
                v_class = prism.vertical_classification.value
            except Exception:
                carpet_area = 0.0
                volume_m3 = 0.0
                v_class = fl.classification

            source_val = fl.source.value if hasattr(fl.source, "value") else str(fl.source)

            for u_idx in range(1, units_per_floor + 1):
                unit_number = f"{level_code}-{u_idx:02d}"
                unit_code = f"U-{unit_number}"
                u_type = "APARTMENT" if "L" in level_code or "G" in level_code else "BASEMENT"

                proposed_units.append({
                    "unit_number": unit_number,
                    "unit_code": unit_code,
                    "unit_type": u_type,
                    "level_code": level_code,
                    "z_min": z_min,
                    "z_max": z_max,
                    "height_m": h,
                    "carpet_area_sqm": carpet_area,
                    "volume_cu_m": volume_m3,
                    "classification": v_class,
                    "is_multi_floor": False,
                    "floor_span": [level_code],
                    "stage": DataStage.ESTIMATED.value,
                    "footprint_geojson": footprint_geojson,
                    "confidence": fl.confidence,
                    "uncertainty_m": fl.uncertainty_m,
                    "source": source_val
                })

        # 2. Multi-floor units (Duplexes, Vertical Utility Shafts, Elevator Cores, Ramps)
        if multi_floor_configs:
            for m_cfg in multi_floor_configs:
                spanned_codes = m_cfg.get("level_codes") or m_cfg.get("floor_span", [])
                matching_levels = [level_map[c] for c in spanned_codes if c in level_map]

                if not matching_levels:
                    continue

                span_z_min = min(l.z_min for l in matching_levels)
                span_z_max = max(l.z_max for l in matching_levels)
                span_h = round(span_z_max - span_z_min, 2)
                m_geom = m_cfg.get("footprint_geojson") or footprint_geojson

                try:
                    prism = PrismVolume(
                        footprint_geojson=m_geom,
                        z_min=span_z_min,
                        z_max=span_z_max,
                        ground_elevation_m=ground_elevation_m
                    )
                    carpet_area = prism.area_sqm
                    volume_m3 = prism.volume_cu_m
                    v_class = prism.vertical_classification.value
                except Exception:
                    carpet_area = 0.0
                    volume_m3 = 0.0
                    v_class = "MULTI_LEVEL_INFRASTRUCTURE" if len(matching_levels) > 2 else "ELEVATED"

                unit_num = m_cfg.get("unit_number", f"DUPLEX-{matching_levels[0].level_code}")
                unit_code = m_cfg.get("unit_code", f"U-{unit_num.replace(' ', '')}")
                unit_type = m_cfg.get("unit_type", "DUPLEX")

                proposed_units.append({
                    "unit_number": unit_num,
                    "unit_code": unit_code,
                    "unit_type": unit_type,
                    "level_code": matching_levels[0].level_code,
                    "z_min": span_z_min,
                    "z_max": span_z_max,
                    "height_m": span_h,
                    "carpet_area_sqm": carpet_area,
                    "volume_cu_m": volume_m3,
                    "classification": v_class,
                    "is_multi_floor": True,
                    "floor_span": [l.level_code for l in matching_levels],
                    "stage": DataStage.ESTIMATED.value,
                    "footprint_geojson": m_geom,
                    "confidence": min(l.confidence for l in matching_levels),
                    "uncertainty_m": max((l.uncertainty_m or 0.1) for l in matching_levels),
                    "source": matching_levels[0].source.value if hasattr(matching_levels[0].source, "value") else str(matching_levels[0].source)
                })

        return proposed_units
