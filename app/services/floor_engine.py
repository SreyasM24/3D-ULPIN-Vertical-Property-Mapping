"""
Floor Engine & Building Volumetric Modeler.

Validates floor elevation slices, detects vertical floor clashes/overlaps,
enforces ground reference rules for basements and elevated tiers,
and models deterministic building volumes.
"""

from typing import List, Dict, Any, Tuple, Optional
from app.core.exceptions import CadastreException
from app.core.spatial_volume import PrismVolume, VerticalClassification, classify_vertical_position


class FloorValidationReport:
    """Audit report for building floor strata consistency."""
    def __init__(self, building_id: str):
        self.building_id = building_id
        self.is_valid: bool = True
        self.total_floors: int = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.overlapping_floor_pairs: List[Tuple[str, str, float]] = []
        self.strata_summary: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "building_id": self.building_id,
            "is_valid": self.is_valid,
            "total_floors": self.total_floors,
            "errors": self.errors,
            "warnings": self.warnings,
            "overlapping_floor_pairs": [
                {"floor_a": a, "floor_b": b, "overlap_m": ov}
                for a, b, ov in self.overlapping_floor_pairs
            ],
            "strata_summary": self.strata_summary
        }


class FloorEngine:
    @staticmethod
    def compute_building_volume(
        footprint_geojson: Dict[str, Any],
        ground_elevation_m: float,
        total_height_m: float,
        basement_depth_m: float = 0.0
    ) -> PrismVolume:
        """
        Calculates the complete building volumetric envelope:
        - z_min = ground_elevation_m - basement_depth_m
        - z_max = ground_elevation_m + total_height_m
        - Volume = Footprint Area (m²) * Total Height (m)
        """
        z_min = round(ground_elevation_m - basement_depth_m, 3)
        z_max = round(ground_elevation_m + total_height_m, 3)

        return PrismVolume(
            footprint_geojson=footprint_geojson,
            z_min=z_min,
            z_max=z_max,
            ground_elevation_m=ground_elevation_m
        )

    @staticmethod
    def validate_building_floors(
        building_id: str,
        ground_elevation_m: float,
        total_height_m: float,
        floors: List[Dict[str, Any]],
        tolerance_m: float = 0.05
    ) -> FloorValidationReport:
        """
        Rigorously validates floor levels for a building:
        1. z_max > z_min for each floor
        2. Heights: floor_height_m = z_max - z_min
        3. Pairwise floor overlap detection (floors cannot share volumetric vertical elevation)
        4. Basement levels (level_number < 0 or code starting with 'B') must be below ground_elevation
        5. Elevated levels (level_number > 0 or code starting with 'L') must be above ground_elevation
        6. Topmost floor does not exceed building top elevation
        """
        report = FloorValidationReport(building_id)
        report.total_floors = len(floors)

        if not floors:
            report.warnings.append("Building currently has no registered floor levels.")
            return report

        building_top_z = ground_elevation_m + total_height_m

        # Sort floors by z_min ascending
        sorted_floors = sorted(floors, key=lambda f: f.get("z_min", 0.0))

        basements = []
        ground_floors = []
        elevated_floors = []

        for f in sorted_floors:
            f_code = f.get("level_code", "").upper()
            f_num = f.get("level_number", 0)
            z_min = f.get("z_min")
            z_max = f.get("z_max")

            # 1. Bounds check
            if z_min is None or z_max is None or z_max <= z_min:
                report.errors.append(f"Floor {f_code} has invalid vertical interval: z_min={z_min}, z_max={z_max}")
                continue

            height = round(z_max - z_min, 3)

            # 2. Building envelope check
            if z_max > building_top_z + tolerance_m:
                report.errors.append(
                    f"Floor {f_code} top ({z_max}m) exceeds building permissible height ({building_top_z}m)"
                )

            # 3. Ground reference datum checks
            is_basement = f_num < 0 or f_code.startswith("B") or f.get("level_type") == "BASEMENT"
            if is_basement:
                basements.append(f_code)
                if z_max > ground_elevation_m + 0.6:  # Allow standard 0.6m plinth/ground-slab tolerance
                    report.errors.append(
                        f"Basement floor {f_code} elevation ({z_max}m) extends above ground level ({ground_elevation_m}m)"
                    )
            elif f_num == 0 or f_code == "G00" or f.get("level_type") == "GROUND":
                ground_floors.append(f_code)
            else:
                elevated_floors.append(f_code)
                if z_min < ground_elevation_m - 0.6:
                    report.errors.append(
                        f"Elevated floor {f_code} base ({z_min}m) drops below ground level ({ground_elevation_m}m)"
                    )

        # 4. Pairwise vertical overlap detection
        n = len(sorted_floors)
        for i in range(n):
            for j in range(i + 1, n):
                f1 = sorted_floors[i]
                f2 = sorted_floors[j]
                overlap = min(f1["z_max"], f2["z_max"]) - max(f1["z_min"], f2["z_min"])
                if overlap > tolerance_m:
                    report.overlapping_floor_pairs.append((
                        f1.get("level_code", str(i)),
                        f2.get("level_code", str(j)),
                        round(overlap, 3)
                    ))
                    report.errors.append(
                        f"Vertical overlap between floor {f1.get('level_code')} and {f2.get('level_code')} by {overlap:.3f}m"
                    )

        report.is_valid = len(report.errors) == 0
        report.strata_summary = {
            "basement_count": len(basements),
            "ground_count": len(ground_floors),
            "elevated_count": len(elevated_floors),
            "ground_elevation_m": ground_elevation_m,
            "building_top_z": building_top_z,
            "lowest_z": sorted_floors[0]["z_min"] if sorted_floors else None,
            "highest_z": sorted_floors[-1]["z_max"] if sorted_floors else None
        }

        return report
