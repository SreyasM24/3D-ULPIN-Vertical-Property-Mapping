"""
Cadastral Spatial Relationship Engine.

Rigorously verifies 2D and 3D containment across the cadastral hierarchy:
- Parcel contains Building
- Building contains Floor
- Floor contains Unit
- Building contains Unit
- Parcel contains Unit

Supports multi-floor units (e.g. duplexes, parking ramps, vertical utility shafts)
with transparent classification rather than blind rejection.
"""

from typing import Dict, Any, Optional, Tuple, List
from enum import Enum
from pydantic import BaseModel, Field

from app.core.spatial_volume import PrismVolume
from app.services.spatial_engine import (
    evaluate_building_containment,
    geojson_to_shapely,
)


class ContainmentStatus(str, Enum):
    CONTAINED = "CONTAINED"
    PARTIALLY_OUTSIDE = "PARTIALLY_OUTSIDE"
    COMPLETELY_OUTSIDE = "COMPLETELY_OUTSIDE"
    INVALID_Z_RANGE = "INVALID_Z_RANGE"
    MULTI_FLOOR_SPAN = "MULTI_FLOOR_SPAN"
    INVALID_GEOMETRY = "INVALID_GEOMETRY"


class SpatialRelationshipResult(BaseModel):
    """Structured audit of hierarchical spatial relationship."""
    relationship_type: str
    parent_id: str
    child_id: str
    is_valid: bool
    status: ContainmentStatus
    intersection_area_sqm: float
    excess_area_sqm: float
    excess_percentage: float
    z_conformance: bool
    is_multi_floor: bool = False
    message: str


class CadastralRelationshipEngine:
    @staticmethod
    def check_parcel_contains_building(
        parcel: Any,
        building: Any,
        tolerance_sqm: float = 0.05
    ) -> SpatialRelationshipResult:
        """Verifies if LandParcel topologically contains Building footprint."""
        res = evaluate_building_containment(
            building.footprint_geojson,
            parcel.geometry_geojson,
            tolerance_sqm=tolerance_sqm
        )
        return SpatialRelationshipResult(
            relationship_type="PARCEL_CONTAINS_BUILDING",
            parent_id=str(parcel.id),
            child_id=str(building.id),
            is_valid=res["is_contained"],
            status=ContainmentStatus(res["status"]),
            intersection_area_sqm=res["intersection_area_sqm"],
            excess_area_sqm=res["excess_area_sqm"],
            excess_percentage=res["excess_percentage"],
            z_conformance=True,
            message=res["message"]
        )

    @staticmethod
    def check_building_contains_floor(
        building: Any,
        floor: Any,
        tolerance_sqm: float = 0.05,
        tolerance_z_m: float = 0.1
    ) -> SpatialRelationshipResult:
        """Verifies if Building contains Floor footprint and vertical bounds."""
        # 1. 2D footprint check
        floor_geom = floor.footprint_geojson or building.footprint_geojson
        containment = evaluate_building_containment(
            floor_geom,
            building.footprint_geojson,
            tolerance_sqm=tolerance_sqm
        )

        # 2. Vertical Z check
        building_top_z = building.ground_elevation_m + building.total_height_m
        building_bottom_z = building.ground_elevation_m - (building.basement_floors * 4.0)

        z_valid = (
            floor.z_min >= building_bottom_z - tolerance_z_m and
            floor.z_max <= building_top_z + tolerance_z_m
        )

        status = ContainmentStatus(containment["status"])
        if not z_valid and containment["is_contained"]:
            status = ContainmentStatus.INVALID_Z_RANGE

        is_valid = containment["is_contained"] and z_valid
        msg = containment["message"] if not containment["is_contained"] else (
            "Floor vertically conforms to building envelope" if z_valid else
            f"Floor elevation [{floor.z_min}, {floor.z_max}] exceeds building vertical bounds [{building_bottom_z}, {building_top_z}]"
        )

        return SpatialRelationshipResult(
            relationship_type="BUILDING_CONTAINS_FLOOR",
            parent_id=str(building.id),
            child_id=str(floor.id),
            is_valid=is_valid,
            status=status,
            intersection_area_sqm=containment["intersection_area_sqm"],
            excess_area_sqm=containment["excess_area_sqm"],
            excess_percentage=containment["excess_percentage"],
            z_conformance=z_valid,
            message=msg
        )

    @staticmethod
    def check_floor_contains_unit(
        floor: Any,
        unit: Any,
        tolerance_sqm: float = 0.05,
        tolerance_z_m: float = 0.15,
        allow_multi_floor: bool = True
    ) -> SpatialRelationshipResult:
        """
        Verifies if Floor contains Vertical Property Unit.
        Supports multi-floor units (e.g. duplex apartments, parking ramps, vertical shafts).
        """
        building = floor.building
        outer_geom = floor.footprint_geojson or building.footprint_geojson

        containment = evaluate_building_containment(
            unit.footprint_geojson,
            outer_geom,
            tolerance_sqm=tolerance_sqm
        )

        # Vertical check
        spans_multiple_floors = (
            unit.z_min < floor.z_min - tolerance_z_m or
            unit.z_max > floor.z_max + tolerance_z_m
        )

        z_valid = True
        status = ContainmentStatus(containment["status"])

        if spans_multiple_floors:
            if allow_multi_floor:
                status = ContainmentStatus.MULTI_FLOOR_SPAN
                msg = (
                    f"Unit '{unit.unit_number}' spans multiple vertical strata "
                    f"[{unit.z_min}m to {unit.z_max}m] relative to floor [{floor.z_min}m to {floor.z_max}m]."
                )
            else:
                z_valid = False
                status = ContainmentStatus.INVALID_Z_RANGE
                msg = f"Unit elevation range [{unit.z_min}, {unit.z_max}] exceeds floor bounds [{floor.z_min}, {floor.z_max}]."
        else:
            msg = containment["message"]

        is_valid = containment["is_contained"] and z_valid

        return SpatialRelationshipResult(
            relationship_type="FLOOR_CONTAINS_UNIT",
            parent_id=str(floor.id),
            child_id=str(unit.id),
            is_valid=is_valid,
            status=status,
            intersection_area_sqm=containment["intersection_area_sqm"],
            excess_area_sqm=containment["excess_area_sqm"],
            excess_percentage=containment["excess_percentage"],
            z_conformance=not spans_multiple_floors,
            is_multi_floor=spans_multiple_floors,
            message=msg
        )

    @staticmethod
    def check_building_contains_unit(
        building: Any,
        unit: Any,
        tolerance_sqm: float = 0.05,
        tolerance_z_m: float = 0.2
    ) -> SpatialRelationshipResult:
        """Verifies if Building directly contains Unit in both 2D footprint and vertical envelope."""
        containment = evaluate_building_containment(
            unit.footprint_geojson,
            building.footprint_geojson,
            tolerance_sqm=tolerance_sqm
        )

        building_top_z = building.ground_elevation_m + building.total_height_m
        building_bottom_z = building.ground_elevation_m - (building.basement_floors * 5.0)

        z_valid = (
            unit.z_min >= building_bottom_z - tolerance_z_m and
            unit.z_max <= building_top_z + tolerance_z_m
        )

        status = ContainmentStatus(containment["status"])
        if not z_valid and containment["is_contained"]:
            status = ContainmentStatus.INVALID_Z_RANGE

        is_valid = containment["is_contained"] and z_valid
        msg = containment["message"] if not containment["is_contained"] else (
            "Unit strictly enclosed inside building envelope" if z_valid else
            f"Unit vertical range [{unit.z_min}, {unit.z_max}] exceeds building vertical bounds."
        )

        return SpatialRelationshipResult(
            relationship_type="BUILDING_CONTAINS_UNIT",
            parent_id=str(building.id),
            child_id=str(unit.id),
            is_valid=is_valid,
            status=status,
            intersection_area_sqm=containment["intersection_area_sqm"],
            excess_area_sqm=containment["excess_area_sqm"],
            excess_percentage=containment["excess_percentage"],
            z_conformance=z_valid,
            message=msg
        )

    @staticmethod
    def check_parcel_contains_unit(
        parcel: Any,
        unit: Any,
        tolerance_sqm: float = 0.05
    ) -> SpatialRelationshipResult:
        """Verifies if LandParcel 2D boundary contains Unit footprint."""
        res = evaluate_building_containment(
            unit.footprint_geojson,
            parcel.geometry_geojson,
            tolerance_sqm=tolerance_sqm
        )
        return SpatialRelationshipResult(
            relationship_type="PARCEL_CONTAINS_UNIT",
            parent_id=str(parcel.id),
            child_id=str(unit.id),
            is_valid=res["is_contained"],
            status=ContainmentStatus(res["status"]),
            intersection_area_sqm=res["intersection_area_sqm"],
            excess_area_sqm=res["excess_area_sqm"],
            excess_percentage=res["excess_percentage"],
            z_conformance=True,
            message=res["message"]
        )
