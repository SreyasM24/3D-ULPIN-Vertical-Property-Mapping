"""
Vertical Cadastre Feature Service.
Bridges ML/estimated features into candidate cadastral geometries
and connects them to the existing deterministic validation engine.
"""

from typing import List, Dict, Any, Optional
from app.ml.schemas import (
    BuildingFeatureResult,
    VerticalFeatureResult,
    DataStage,
    EvidenceSourceType,
    ConfidenceLevel,
)
from app.ml.features.vertical_features import VerticalFeatureExtractor
from app.services.floor_engine import FloorEngine
from app.services.cadastral_relationship_engine import CadastralRelationshipEngine


class VerticalCadastreFeatureService:
    """
    Constructs candidate cadastral floor levels and vertical units from ML estimates.
    Directly feeds proposed geometries into the deterministic validation engine.
    """

    @classmethod
    def generate_candidate_cadastre(
        cls,
        footprint_geojson: Dict[str, Any],
        ground_elevation_m: float,
        total_height_m: float,
        strata_levels: List[VerticalFeatureResult],
        units_per_floor: int = 2,
        parent_parcel_id: Optional[str] = None,
        building_code: str = "BLD-PROP",
        multi_floor_configs: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Transforms estimated strata into candidate FloorLevel and VerticalUnit proposals,
        and tests them against deterministic floor strata rules.
        """
        # 1. Propose candidate units (including multi-floor duplexes/shafts)
        candidate_units = VerticalFeatureExtractor.propose_vertical_units(
            footprint_geojson=footprint_geojson,
            strata_levels=strata_levels,
            units_per_floor=units_per_floor,
            ground_elevation_m=ground_elevation_m,
            multi_floor_configs=multi_floor_configs
        )

        # 2. Form candidate floor strata definitions
        candidate_floors = []
        for idx, fl in enumerate(strata_levels):
            level_num = idx if "G" in fl.level_code else (
                -int(fl.level_code[1:]) if "B" in fl.level_code else int(fl.level_code[1:])
            )
            candidate_floors.append({
                "level_code": fl.level_code,
                "level_number": level_num,
                "z_min": fl.z_min,
                "z_max": fl.z_max,
                "floor_height_m": fl.estimated_height_m,
                "footprint_geojson": footprint_geojson,
                "classification": fl.classification
            })

        # 3. Perform deterministic floor validation check on candidate strata
        floor_report = FloorEngine.validate_building_floors(
            building_id=building_code,
            ground_elevation_m=ground_elevation_m,
            total_height_m=total_height_m,
            floors=candidate_floors
        )

        return {
            "building_code": building_code,
            "parent_parcel_id": parent_parcel_id,
            "ground_elevation_m": ground_elevation_m,
            "total_height_m": total_height_m,
            "candidate_floors": candidate_floors,
            "candidate_units": candidate_units,
            "deterministic_floor_validation": floor_report.to_dict(),
            "is_cadastrally_consistent": floor_report.is_valid,
            "stage": DataStage.ESTIMATED.value
        }
