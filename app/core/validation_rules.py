"""
Modular Cadastral Validation Rule Engine & Standard Rule Catalogue.
Provides independently testable, deterministic validation rules for SIH 26011.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Type
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.validation import explain_validity

from app.schemas.validation import (
    RuleSeverity,
    RuleCategory,
    ValidationRuleDefinition,
    ValidationIssue,
)
from app.services.spatial_engine import (
    geojson_to_shapely,
    evaluate_building_containment,
    compute_projected_spatial_metrics,
)
from app.services.geometry_normalization import GeometryNormalizationService


class CadastralValidationRule(ABC):
    """Abstract base class for all deterministic cadastral validation rules."""
    rule_id: str
    category: RuleCategory
    severity: RuleSeverity
    title: str
    description: str
    affected_entity_types: List[str]

    @classmethod
    def get_definition(cls) -> ValidationRuleDefinition:
        return ValidationRuleDefinition(
            rule_id=cls.rule_id,
            category=cls.category,
            severity=cls.severity,
            title=cls.title,
            description=cls.description,
            affected_entity_types=cls.affected_entity_types
        )

    @abstractmethod
    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        """
        Executes deterministic rule check against the context.
        Returns ValidationIssue if rule condition is violated, or None if passed.
        """
        pass


# ============================================================================
# 1. GEOMETRY VALIDATION RULES
# ============================================================================

class RuleGeo001ValidGeometry(CadastralValidationRule):
    rule_id = "RULE-GEO-001"
    category = RuleCategory.GEOMETRY
    severity = RuleSeverity.ERROR
    title = "Valid OGC / GeoJSON Polygon Structure"
    description = "Checks that polygon geometry contains no self-intersections or self-tangencies."
    affected_entity_types = ["PARCEL", "BUILDING", "FLOOR", "UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        geojson = context.get("geometry_geojson") or context.get("footprint_geojson")
        entity_id = str(context.get("id", "UNKNOWN"))
        entity_type = context.get("entity_type", "ENTITY")
        identifier = context.get("identifier", entity_id)

        if not geojson or not isinstance(geojson, dict):
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_identifier=identifier,
                measured_values={"geometry_present": False},
                expected_condition="Valid GeoJSON dictionary geometry",
                actual_condition="Missing or non-dictionary geometry",
                explanation=f"{entity_type} {identifier} has missing or malformed GeoJSON.",
                suggested_remediation="Supply a valid GeoJSON Polygon or MultiPolygon."
            )

        try:
            geom = shape(geojson)
            if not geom.is_valid:
                reason = explain_validity(geom)
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    entity_identifier=identifier,
                    measured_values={"validity_reason": reason},
                    expected_condition="OGC Simple Feature validity (is_valid == True)",
                    actual_condition=f"Invalid geometry: {reason}",
                    explanation=f"{entity_type} {identifier} geometry is topologically invalid: {reason}.",
                    suggested_remediation="Reconstruct polygon boundary vertices to eliminate self-intersections."
                )
        except Exception as e:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_identifier=identifier,
                measured_values={"parse_error": str(e)},
                expected_condition="Parsable GeoJSON geometry",
                actual_condition=f"Parse exception: {str(e)}",
                explanation=f"{entity_type} {identifier} coordinates could not be parsed.",
                suggested_remediation="Verify coordinate array syntax."
            )
        return None


class RuleGeo002RingClosure(CadastralValidationRule):
    rule_id = "RULE-GEO-002"
    category = RuleCategory.GEOMETRY
    severity = RuleSeverity.ERROR
    title = "Linear Ring Closure and Minimum Coordinates"
    description = "Checks that exterior and interior rings are closed (first==last) with at least 4 coordinate pairs."
    affected_entity_types = ["PARCEL", "BUILDING", "FLOOR", "UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        geojson = context.get("geometry_geojson") or context.get("footprint_geojson")
        entity_id = str(context.get("id", "UNKNOWN"))
        entity_type = context.get("entity_type", "ENTITY")
        identifier = context.get("identifier", entity_id)

        if not geojson or not isinstance(geojson, dict):
            return None  # Caught by RULE-GEO-001

        coords = geojson.get("coordinates")
        g_type = geojson.get("type")
        if not coords or g_type not in ("Polygon", "MultiPolygon"):
            return None

        rings = coords if g_type == "Polygon" else [r for p in coords for r in p]
        for idx, ring in enumerate(rings):
            if not isinstance(ring, list) or len(ring) < 4:
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    entity_identifier=identifier,
                    measured_values={"ring_index": idx, "point_count": len(ring) if isinstance(ring, list) else 0},
                    expected_condition="Linear ring must contain at least 4 coordinate pairs",
                    actual_condition=f"Ring {idx} contains fewer than 4 points",
                    explanation=f"{entity_type} {identifier} contains a degenerate linear ring.",
                    suggested_remediation="Ensure every boundary polygon has at least 3 distinct vertices plus closure point."
                )
            if ring[0][:2] != ring[-1][:2]:
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    entity_identifier=identifier,
                    measured_values={"first_point": ring[0][:2], "last_point": ring[-1][:2]},
                    expected_condition="First and last coordinates of ring must be identical",
                    actual_condition="Ring is open (first != last)",
                    explanation=f"{entity_type} {identifier} linear ring is not closed.",
                    suggested_remediation="Append the starting coordinate to the end of the ring sequence."
                )
        return None


class RuleGeo003PositiveArea(CadastralValidationRule):
    rule_id = "RULE-GEO-003"
    category = RuleCategory.GEOMETRY
    severity = RuleSeverity.ERROR
    title = "Non-Empty Footprint with Positive Metric Area"
    description = "Checks that the geometry is non-empty and has a positive projected surface area (> 0.1 m²)."
    affected_entity_types = ["PARCEL", "BUILDING", "FLOOR", "UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        geojson = context.get("geometry_geojson") or context.get("footprint_geojson")
        entity_id = str(context.get("id", "UNKNOWN"))
        entity_type = context.get("entity_type", "ENTITY")
        identifier = context.get("identifier", entity_id)

        if not geojson:
            return None

        area = 0.0
        try:
            metrics = compute_projected_spatial_metrics(geojson)
            area = metrics["area_sqm"]
        except Exception:
            try:
                geom = shape(geojson)
                area = float(geom.area)
            except Exception:
                area = 0.0

        if area < 0.1:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_identifier=identifier,
                measured_values={"area_sqm": area},
                expected_condition="Projected metric area >= 0.1 m²",
                actual_condition=f"Area is {area:.3f} m²",
                explanation=f"{entity_type} {identifier} has zero or near-zero footprint area.",
                suggested_remediation="Verify footprint coordinates represent an actual spatial perimeter."
            )
        return None


class RuleGeo004DisconnectedMultiPolygon(CadastralValidationRule):
    rule_id = "RULE-GEO-004"
    category = RuleCategory.GEOMETRY
    severity = RuleSeverity.WARNING
    title = "Disconnected MultiPolygon Structure Audit"
    description = "Flags multi-part MultiPolygons when a single contiguous cadastral boundary is typically expected."
    affected_entity_types = ["PARCEL", "UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        geojson = context.get("geometry_geojson") or context.get("footprint_geojson")
        entity_id = str(context.get("id", "UNKNOWN"))
        entity_type = context.get("entity_type", "ENTITY")
        identifier = context.get("identifier", entity_id)

        if not geojson or geojson.get("type") != "MultiPolygon":
            return None

        coords = geojson.get("coordinates", [])
        if len(coords) > 1:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_identifier=identifier,
                measured_values={"polygon_parts_count": len(coords)},
                expected_condition="Single contiguous polygon boundary",
                actual_condition=f"MultiPolygon with {len(coords)} separate components",
                explanation=f"{entity_type} {identifier} is represented as {len(coords)} disjoint parts.",
                suggested_remediation="Confirm whether this entity is genuinely a non-contiguous holding."
            )
        return None


class RuleGeo005NormalizationDrift(CadastralValidationRule):
    rule_id = "RULE-GEO-005"
    category = RuleCategory.GEOMETRY
    severity = RuleSeverity.WARNING
    title = "Geometry Normalization Drift Audit"
    description = "Detects whether automatic geometry healing altered the original cadastral area by > 1%."
    affected_entity_types = ["PARCEL", "BUILDING", "UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        geojson = context.get("geometry_geojson") or context.get("footprint_geojson")
        entity_id = str(context.get("id", "UNKNOWN"))
        entity_type = context.get("entity_type", "ENTITY")
        identifier = context.get("identifier", entity_id)

        if not geojson:
            return None

        try:
            norm = GeometryNormalizationService.normalize_geojson(geojson)
            if norm.was_repaired and norm.area_change_pct > 1.0:
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    entity_identifier=identifier,
                    measured_values={
                        "area_change_pct": norm.area_change_pct,
                        "repairs_applied": norm.repair_actions
                    },
                    expected_condition="Repaired geometry area change <= 1.0%",
                    actual_condition=f"Geometry area changed by {norm.area_change_pct:.2f}%",
                    explanation=f"{entity_type} {identifier} required significant geometric healing that altered area.",
                    suggested_remediation="Re-survey or re-digitize boundary to match original legal cadastral map."
                )
        except Exception:
            return None
        return None


# ============================================================================
# 2. HIERARCHICAL VALIDATION RULES
# ============================================================================

class RuleHier001BuildingInParcel(CadastralValidationRule):
    rule_id = "RULE-HIER-001"
    category = RuleCategory.HIERARCHY
    severity = RuleSeverity.ERROR
    title = "Building Footprint Contained in Land Parcel"
    description = "Verifies that the building 2D footprint does not extend beyond parent parcel boundaries."
    affected_entity_types = ["BUILDING"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        bld_geom = context.get("footprint_geojson")
        pcl_geom = context.get("parcel_geometry_geojson")
        bld_id = str(context.get("id", "UNKNOWN"))
        bld_code = context.get("building_code", bld_id)

        if not bld_geom or not pcl_geom:
            return None

        res = evaluate_building_containment(bld_geom, pcl_geom, tolerance_sqm=0.05)
        if not res["is_contained"]:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="BUILDING",
                entity_id=bld_id,
                entity_identifier=bld_code,
                measured_values={
                    "excess_area_sqm": res["excess_area_sqm"],
                    "excess_percentage": res["excess_percentage"],
                    "status": res["status"]
                },
                expected_condition="Building footprint completely enclosed in parcel boundary",
                actual_condition=f"Building extends outside parcel by {res['excess_area_sqm']:.2f} m² ({res['excess_percentage']}%)",
                explanation=f"Building {bld_code} spills outside the parent land parcel.",
                suggested_remediation="Adjust building footprint coordinates or parcel boundary alignment."
            )
        return None


class RuleHier002FloorInBuilding(CadastralValidationRule):
    rule_id = "RULE-HIER-002"
    category = RuleCategory.HIERARCHY
    severity = RuleSeverity.ERROR
    title = "Floor Footprint Contained in Building Envelope"
    description = "Checks that individual floor boundary does not spill outside the building structural footprint."
    affected_entity_types = ["FLOOR"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        floor_geom = context.get("footprint_geojson")
        bld_geom = context.get("building_footprint_geojson")
        floor_id = str(context.get("id", "UNKNOWN"))
        level_code = context.get("level_code", floor_id)

        if not floor_geom or not bld_geom:
            return None  # Typical floors without custom footprint inherit building footprint

        res = evaluate_building_containment(floor_geom, bld_geom, tolerance_sqm=0.05)
        if not res["is_contained"]:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="FLOOR",
                entity_id=floor_id,
                entity_identifier=level_code,
                measured_values={
                    "excess_area_sqm": res["excess_area_sqm"],
                    "excess_percentage": res["excess_percentage"]
                },
                expected_condition="Floor boundary within building footprint envelope",
                actual_condition=f"Floor extends outside building by {res['excess_area_sqm']:.2f} m²",
                explanation=f"Floor level {level_code} extends beyond the building's permissible footprint.",
                suggested_remediation="Clip floor slab boundary to building footprint envelope."
            )
        return None


class RuleHier003UnitInParentFootprint(CadastralValidationRule):
    rule_id = "RULE-HIER-003"
    category = RuleCategory.HIERARCHY
    severity = RuleSeverity.ERROR
    title = "Unit Footprint Contained in Floor/Building Boundary"
    description = "Checks that a vertical unit footprint is within its parent floor/building perimeter."
    affected_entity_types = ["UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        unit_geom = context.get("footprint_geojson")
        parent_geom = context.get("floor_footprint_geojson") or context.get("building_footprint_geojson")
        unit_id = str(context.get("id", "UNKNOWN"))
        unit_num = context.get("unit_number", unit_id)

        if not unit_geom or not parent_geom:
            return None

        res = evaluate_building_containment(unit_geom, parent_geom, tolerance_sqm=0.05)
        if not res["is_contained"]:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="UNIT",
                entity_id=unit_id,
                entity_identifier=unit_num,
                measured_values={
                    "excess_area_sqm": res["excess_area_sqm"],
                    "excess_percentage": res["excess_percentage"]
                },
                expected_condition="Unit footprint enclosed within floor/building footprint",
                actual_condition=f"Unit extends outside by {res['excess_area_sqm']:.2f} m² ({res['excess_percentage']}%)",
                explanation=f"Unit {unit_num} perimeter exceeds the floor perimeter.",
                suggested_remediation="Align unit interior walls to remain within floor boundaries."
            )
        return None


class RuleHier004UnitInBuildingZ(CadastralValidationRule):
    rule_id = "RULE-HIER-004"
    category = RuleCategory.HIERARCHY
    severity = RuleSeverity.ERROR
    title = "Unit Vertical Elevation within Building Vertical Range"
    description = "Verifies that unit elevations do not exceed building permissible roofline or deepest basement."
    affected_entity_types = ["UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        z_min = context.get("z_min")
        z_max = context.get("z_max")
        bld_top_z = context.get("building_top_z")
        bld_bottom_z = context.get("building_bottom_z")
        unit_id = str(context.get("id", "UNKNOWN"))
        unit_num = context.get("unit_number", unit_id)

        if z_min is None or z_max is None or bld_top_z is None or bld_bottom_z is None:
            return None

        tol = 0.2
        if z_max > bld_top_z + tol or z_min < bld_bottom_z - tol:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="UNIT",
                entity_id=unit_id,
                entity_identifier=unit_num,
                measured_values={
                    "unit_z_min": z_min, "unit_z_max": z_max,
                    "bld_bottom_z": bld_bottom_z, "bld_top_z": bld_top_z
                },
                expected_condition=f"Elevation within building envelope [{bld_bottom_z:.2f}, {bld_top_z:.2f}]",
                actual_condition=f"Unit elevation range is [{z_min:.2f}, {z_max:.2f}]",
                explanation=f"Unit {unit_num} vertical limits lie outside the building's vertical envelope.",
                suggested_remediation="Correct unit elevation metadata or update building total height."
            )
        return None


class RuleHier005UnitFloorElevationMatch(CadastralValidationRule):
    rule_id = "RULE-HIER-005"
    category = RuleCategory.HIERARCHY
    severity = RuleSeverity.ERROR
    title = "Unit Elevation Conforms to Parent Floor Strata"
    description = "Checks that unit elevation conforms to parent floor, respecting multi-floor units (duplexes/shafts)."
    affected_entity_types = ["UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        unit_z_min = context.get("z_min")
        unit_z_max = context.get("z_max")
        fl_z_min = context.get("floor_z_min")
        fl_z_max = context.get("floor_z_max")
        unit_type = str(context.get("unit_type", "APARTMENT")).upper()
        is_multi_floor = context.get("is_multi_floor", False)
        unit_id = str(context.get("id", "UNKNOWN"))
        unit_num = context.get("unit_number", unit_id)

        if unit_z_min is None or unit_z_max is None or fl_z_min is None or fl_z_max is None:
            return None

        # Multi-floor recognized types
        MULTI_FLOOR_TYPES = {"DUPLEX", "ELEVATOR_SHAFT", "RAMP", "UTILITY_RISER", "TUNNEL", "STAIRWELL"}
        if is_multi_floor or unit_type in MULTI_FLOOR_TYPES:
            # Multi-floor units are permitted to extend past single floor bounds
            return None

        tol = 0.15
        if unit_z_min < fl_z_min - tol or unit_z_max > fl_z_max + tol:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="UNIT",
                entity_id=unit_id,
                entity_identifier=unit_num,
                measured_values={
                    "unit_range": [unit_z_min, unit_z_max],
                    "floor_range": [fl_z_min, fl_z_max]
                },
                expected_condition=f"Unit elevation within floor strata [{fl_z_min:.2f}, {fl_z_max:.2f}]",
                actual_condition=f"Unit spans [{unit_z_min:.2f}, {unit_z_max:.2f}]",
                explanation=f"Unit {unit_num} elevation exceeds parent floor bounds without multi-floor designation.",
                suggested_remediation="Designate as multi-floor unit or adjust unit elevation boundaries."
            )
        return None


class RuleHier006OrphanedEntity(CadastralValidationRule):
    rule_id = "RULE-HIER-006"
    category = RuleCategory.HIERARCHY
    severity = RuleSeverity.ERROR
    title = "Orphaned Entity Integrity Check"
    description = "Checks that child entity maintains a valid, non-null reference to its parent entity."
    affected_entity_types = ["BUILDING", "FLOOR", "UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        entity_id = str(context.get("id", "UNKNOWN"))
        entity_type = context.get("entity_type", "ENTITY")
        parent_id = context.get("parent_id")
        identifier = context.get("identifier", entity_id)

        if not parent_id:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_identifier=identifier,
                measured_values={"parent_id": None},
                expected_condition="Valid parent relationship link",
                actual_condition="parent_id is null or empty",
                explanation=f"{entity_type} {identifier} is an orphan entity without a parent assignment.",
                suggested_remediation="Link entity to its appropriate parent in the cadastral hierarchy."
            )
        return None


# ============================================================================
# 3. FLOOR STRATA TOPOLOGY RULES
# ============================================================================

class RuleFlr001NonOverlappingFloors(CadastralValidationRule):
    rule_id = "RULE-FLR-001"
    category = RuleCategory.FLOOR_STRATA
    severity = RuleSeverity.ERROR
    title = "Non-Overlapping Vertical Floor Strata"
    description = "Detects volumetric vertical overlap between floor elevation slices in the same building."
    affected_entity_types = ["BUILDING"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        floors = context.get("floors", [])
        bld_id = str(context.get("id", "UNKNOWN"))
        bld_code = context.get("building_code", bld_id)
        tol_m = context.get("tolerance_m", 0.05)

        if len(floors) < 2:
            return None

        sorted_f = sorted(floors, key=lambda f: f.get("z_min", 0.0))
        for i in range(len(sorted_f)):
            for j in range(i + 1, len(sorted_f)):
                f1, f2 = sorted_f[i], sorted_f[j]
                overlap = min(f1["z_max"], f2["z_max"]) - max(f1["z_min"], f2["z_min"])
                if overlap > tol_m:
                    return ValidationIssue(
                        rule_id=self.rule_id,
                        category=self.category,
                        severity=self.severity,
                        entity_type="BUILDING",
                        entity_id=bld_id,
                        entity_identifier=bld_code,
                        measured_values={
                            "floor_a": f1.get("level_code"),
                            "floor_b": f2.get("level_code"),
                            "overlap_m": round(overlap, 3)
                        },
                        expected_condition="Floors must not vertically intersect",
                        actual_condition=f"Overlap of {overlap:.3f}m between {f1.get('level_code')} and {f2.get('level_code')}",
                        explanation=f"Floors {f1.get('level_code')} and {f2.get('level_code')} occupy overlapping vertical elevation.",
                        suggested_remediation="Adjust floor elevation bounds to eliminate slab/strata collision."
                    )
        return None


class RuleFlr002VerticalFloorGaps(CadastralValidationRule):
    rule_id = "RULE-FLR-002"
    category = RuleCategory.FLOOR_STRATA
    severity = RuleSeverity.WARNING
    title = "Vertical Strata Gap Audit"
    description = "Detects unassigned vertical gaps between consecutive floors; distinguishes open space from missing data."
    affected_entity_types = ["BUILDING"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        floors = context.get("floors", [])
        bld_id = str(context.get("id", "UNKNOWN"))
        bld_code = context.get("building_code", bld_id)
        max_gap_tol_m = 0.5  # Typical floor slab thickness / plenum allowance

        if len(floors) < 2:
            return None

        sorted_f = sorted(floors, key=lambda f: f.get("z_min", 0.0))
        for i in range(len(sorted_f) - 1):
            f1 = sorted_f[i]
            f2 = sorted_f[i + 1]
            gap = f2["z_min"] - f1["z_max"]
            if gap > max_gap_tol_m:
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type="BUILDING",
                    entity_id=bld_id,
                    entity_identifier=bld_code,
                    measured_values={
                        "lower_floor": f1.get("level_code"),
                        "upper_floor": f2.get("level_code"),
                        "gap_m": round(gap, 3)
                    },
                    expected_condition=f"Vertical gap between consecutive floors <= {max_gap_tol_m}m",
                    actual_condition=f"Unassigned gap of {gap:.2f}m between {f1.get('level_code')} and {f2.get('level_code')}",
                    explanation=f"Vertical void ({gap:.2f}m) detected between floors {f1.get('level_code')} and {f2.get('level_code')}. "
                                "May represent intentional open space, mechanical plenum, or missing floor representation.",
                    suggested_remediation="Verify if this represents a double-height void or missing intermediate floor."
                )
        return None


class RuleFlr003DuplicateFloorCodes(CadastralValidationRule):
    rule_id = "RULE-FLR-003"
    category = RuleCategory.FLOOR_STRATA
    severity = RuleSeverity.ERROR
    title = "Unique Floor Level Codes per Building"
    description = "Enforces that floor level codes (e.g. L01, B01) are unique within the building."
    affected_entity_types = ["BUILDING"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        floors = context.get("floors", [])
        bld_id = str(context.get("id", "UNKNOWN"))
        bld_code = context.get("building_code", bld_id)

        seen_codes = set()
        duplicates = []
        for f in floors:
            code = f.get("level_code", "").upper()
            if code in seen_codes:
                duplicates.append(code)
            seen_codes.add(code)

        if duplicates:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="BUILDING",
                entity_id=bld_id,
                entity_identifier=bld_code,
                measured_values={"duplicate_codes": duplicates},
                expected_condition="Unique floor level codes within building",
                actual_condition=f"Duplicate floor code(s): {', '.join(duplicates)}",
                explanation=f"Building {bld_code} has multiple floors with the same level code.",
                suggested_remediation="Assign distinct identifiers to each floor stratum."
            )
        return None


class RuleFlr004MonotonicFloorOrdering(CadastralValidationRule):
    rule_id = "RULE-FLR-004"
    category = RuleCategory.FLOOR_STRATA
    severity = RuleSeverity.ERROR
    title = "Monotonic Floor Level Number Ordering"
    description = "Checks that floor level numbers strictly increase with elevation Z."
    affected_entity_types = ["BUILDING"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        floors = context.get("floors", [])
        bld_id = str(context.get("id", "UNKNOWN"))
        bld_code = context.get("building_code", bld_id)

        if len(floors) < 2:
            return None

        # Sort by z_min
        sorted_by_z = sorted(floors, key=lambda f: f.get("z_min", 0.0))
        for i in range(len(sorted_by_z) - 1):
            f1, f2 = sorted_by_z[i], sorted_by_z[i + 1]
            num1 = f1.get("level_number", 0)
            num2 = f2.get("level_number", 0)
            if num1 >= num2:
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type="BUILDING",
                    entity_id=bld_id,
                    entity_identifier=bld_code,
                    measured_values={
                        "floor_lower": f1.get("level_code"), "level_number_lower": num1,
                        "floor_upper": f2.get("level_code"), "level_number_upper": num2
                    },
                    expected_condition="Floor level number increases monotonically with elevation",
                    actual_condition=f"Floor {f1.get('level_code')} (num: {num1}) is below {f2.get('level_code')} (num: {num2})",
                    explanation=f"Inconsistent floor numbering in building {bld_code}: elevation order contradicts level number.",
                    suggested_remediation="Renumber floors so that level numbers monotonically ascend with elevation."
                )
        return None


class RuleFlr005ValidFloorBounds(CadastralValidationRule):
    rule_id = "RULE-FLR-005"
    category = RuleCategory.FLOOR_STRATA
    severity = RuleSeverity.ERROR
    title = "Valid Floor Elevation Range and Realistic Height"
    description = "Enforces z_max > z_min and floor height between 1.5m and 35m."
    affected_entity_types = ["FLOOR"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        floor_id = str(context.get("id", "UNKNOWN"))
        level_code = context.get("level_code", floor_id)
        z_min = context.get("z_min")
        z_max = context.get("z_max")

        if z_min is None or z_max is None or z_max <= z_min:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="FLOOR",
                entity_id=floor_id,
                entity_identifier=level_code,
                measured_values={"z_min": z_min, "z_max": z_max},
                expected_condition="z_max strictly greater than z_min",
                actual_condition=f"z_min={z_min}, z_max={z_max}",
                explanation=f"Floor {level_code} has inverted or zero vertical bounds.",
                suggested_remediation="Specify positive vertical interval where z_max > z_min."
            )

        h = z_max - z_min
        if h < 1.5 or h > 35.0:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=RuleSeverity.WARNING,
                entity_type="FLOOR",
                entity_id=floor_id,
                entity_identifier=level_code,
                measured_values={"floor_height_m": round(h, 2)},
                expected_condition="Realistic floor height (1.5m - 35m)",
                actual_condition=f"Floor height is {h:.2f}m",
                explanation=f"Floor {level_code} has an unusual height ({h:.2f}m).",
                suggested_remediation="Verify elevation datum and survey measurements."
            )
        return None


class RuleFlr006BasementDatumConsistency(CadastralValidationRule):
    rule_id = "RULE-FLR-006"
    category = RuleCategory.FLOOR_STRATA
    severity = RuleSeverity.ERROR
    title = "Basement Strata Datum Consistency"
    description = "Checks that basement levels do not breach ground elevation beyond standard plinth tolerance."
    affected_entity_types = ["FLOOR"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        floor_id = str(context.get("id", "UNKNOWN"))
        level_code = str(context.get("level_code", "")).upper()
        level_num = context.get("level_number", 0)
        level_type = str(context.get("level_type", "")).upper()
        z_max = context.get("z_max")
        ground_z = context.get("ground_elevation_m", 0.0)

        is_basement = level_num < 0 or level_code.startswith("B") or level_type == "BASEMENT"
        if is_basement and z_max is not None:
            plinth_tol = 0.8
            if z_max > ground_z + plinth_tol:
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type="FLOOR",
                    entity_id=floor_id,
                    entity_identifier=level_code,
                    measured_values={"z_max": z_max, "ground_elevation_m": ground_z},
                    expected_condition=f"Basement ceiling <= ground datum + {plinth_tol}m",
                    actual_condition=f"Basement ceiling is at {z_max:.2f}m (ground is {ground_z:.2f}m)",
                    explanation=f"Basement {level_code} extends above ground level into elevated space.",
                    suggested_remediation="Reclassify stratum as podium/ground or adjust elevation datum."
                )
        return None


class RuleFlr007ElevatedDatumConsistency(CadastralValidationRule):
    rule_id = "RULE-FLR-007"
    category = RuleCategory.FLOOR_STRATA
    severity = RuleSeverity.ERROR
    title = "Elevated Floor Datum Consistency"
    description = "Checks that above-ground elevated floors do not extend below ground datum."
    affected_entity_types = ["FLOOR"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        floor_id = str(context.get("id", "UNKNOWN"))
        level_code = str(context.get("level_code", "")).upper()
        level_num = context.get("level_number", 0)
        z_min = context.get("z_min")
        ground_z = context.get("ground_elevation_m", 0.0)

        is_elevated = level_num > 0 or level_code.startswith("L")
        if is_elevated and z_min is not None:
            plinth_tol = 0.8
            if z_min < ground_z - plinth_tol:
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type="FLOOR",
                    entity_id=floor_id,
                    entity_identifier=level_code,
                    measured_values={"z_min": z_min, "ground_elevation_m": ground_z},
                    expected_condition=f"Elevated floor base >= ground datum - {plinth_tol}m",
                    actual_condition=f"Elevated floor base is at {z_min:.2f}m (ground is {ground_z:.2f}m)",
                    explanation=f"Elevated floor {level_code} drops below ground into subterranean space.",
                    suggested_remediation="Check ground datum elevation or reclassify floor as basement."
                )
        return None


# ============================================================================
# 4. 3D TOPOLOGY & OVERLAP RULES
# ============================================================================

class RuleTopo001PropertyConflict(CadastralValidationRule):
    rule_id = "RULE-TOPO-001"
    category = RuleCategory.TOPOLOGY_3D
    severity = RuleSeverity.ERROR
    title = "Private Property Volumetric Intersection"
    description = "Flags true volumetric clashes between private property units as critical cadastral errors."
    affected_entity_types = ["UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        clashes = context.get("clashes", [])
        for c in clashes:
            if c.classification.value == "CRITICAL":
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type="UNIT",
                    entity_id=c.entity_a_id,
                    entity_identifier=c.entity_a_identifier,
                    measured_values={
                        "conflicting_entity_id": c.entity_b_id,
                        "conflicting_identifier": c.entity_b_identifier,
                        "overlap_volume_cu_m": c.estimated_overlap_volume_cu_m,
                        "horizontal_overlap_sqm": c.horizontal_overlap_sqm,
                        "vertical_overlap_m": c.vertical_overlap_m
                    },
                    expected_condition="Volumetric property boundaries must be strictly disjoint",
                    actual_condition=f"Overlaps {c.entity_b_identifier} by {c.estimated_overlap_volume_cu_m:.2f} m³",
                    explanation=f"Private units {c.entity_a_identifier} and {c.entity_b_identifier} occupy the same physical space.",
                    suggested_remediation="Revise 3D unit partition plans to eliminate overlapping volume."
                )
        return None


class RuleTopo002NearBoundaryTolerance(CadastralValidationRule):
    rule_id = "RULE-TOPO-002"
    category = RuleCategory.TOPOLOGY_3D
    severity = RuleSeverity.WARNING
    title = "Near-Boundary Tolerance Discrepancy"
    description = "Flags minor boundary overlaps within tolerance limits for verification."
    affected_entity_types = ["UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        clashes = context.get("clashes", [])
        for c in clashes:
            if c.classification.value == "WARNING":
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type="UNIT",
                    entity_id=c.entity_a_id,
                    entity_identifier=c.entity_a_identifier,
                    measured_values={
                        "conflicting_identifier": c.entity_b_identifier,
                        "overlap_area_sqm": c.horizontal_overlap_sqm
                    },
                    expected_condition="Clean coincident shared boundary vertices",
                    actual_condition=f"Minor tolerance overlap of {c.horizontal_overlap_sqm:.3f} m²",
                    explanation=f"Units {c.entity_a_identifier} and {c.entity_b_identifier} have a minor boundary tolerance overlap.",
                    suggested_remediation="Snap shared boundary vertices to ensure exact coincident edges."
                )
        return None


class RuleTopo003CommonAreaCoexistence(CadastralValidationRule):
    rule_id = "RULE-TOPO-003"
    category = RuleCategory.TOPOLOGY_3D
    severity = RuleSeverity.INFO
    title = "Common Area and Service Coexistence"
    description = "Identifies legitimate shared utility, circulation, or common space coexistence."
    affected_entity_types = ["UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        clashes = context.get("clashes", [])
        for c in clashes:
            if c.classification.value == "INFO":
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type="UNIT",
                    entity_id=c.entity_a_id,
                    entity_identifier=c.entity_a_identifier,
                    measured_values={
                        "common_infrastructure_identifier": c.entity_b_identifier,
                        "overlap_volume_cu_m": c.estimated_overlap_volume_cu_m
                    },
                    expected_condition="Permissible dual-use / common infrastructure",
                    actual_condition=f"Coexists with {c.entity_b_identifier}",
                    explanation=f"Units {c.entity_a_identifier} and {c.entity_b_identifier} share permissible common/utility space.",
                    suggested_remediation="No remediation required if authorized under common area bylaws."
                )
        return None


# ============================================================================
# 5. UNIT INTEGRITY RULES
# ============================================================================

class RuleUnit001ZeroNearZeroVolume(CadastralValidationRule):
    rule_id = "RULE-UNIT-001"
    category = RuleCategory.UNIT_INTEGRITY
    severity = RuleSeverity.ERROR
    title = "Zero or Suspiciously Near-Zero Unit Volume"
    description = "Checks that 3D unit volume is at least 1.0 m³."
    affected_entity_types = ["UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        vol = context.get("volume_cu_m", 0.0)
        unit_id = str(context.get("id", "UNKNOWN"))
        unit_num = context.get("unit_number", unit_id)

        if vol < 1.0:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="UNIT",
                entity_id=unit_id,
                entity_identifier=unit_num,
                measured_values={"volume_cu_m": vol},
                expected_condition="Unit volume >= 1.0 m³",
                actual_condition=f"Volume is {vol:.2f} m³",
                explanation=f"Unit {unit_num} has an implausibly small or zero volumetric space.",
                suggested_remediation="Ensure unit footprint area and height are positive and correctly scaled."
            )
        return None


class RuleUnit002DuplicateUnitIdentifiers(CadastralValidationRule):
    rule_id = "RULE-UNIT-002"
    category = RuleCategory.UNIT_INTEGRITY
    severity = RuleSeverity.ERROR
    title = "Unique Unit Identifiers per Building"
    description = "Checks that unit codes or numbers are unique within the same building."
    affected_entity_types = ["BUILDING"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        units = context.get("units", [])
        bld_id = str(context.get("id", "UNKNOWN"))
        bld_code = context.get("building_code", bld_id)

        seen = set()
        duplicates = []
        for u in units:
            identifier = u.get("unit_number") or u.get("unit_code")
            if identifier:
                if identifier in seen:
                    duplicates.append(identifier)
                seen.add(identifier)

        if duplicates:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="BUILDING",
                entity_id=bld_id,
                entity_identifier=bld_code,
                measured_values={"duplicate_units": duplicates},
                expected_condition="Unique unit numbers within building",
                actual_condition=f"Duplicate unit number(s): {', '.join(duplicates)}",
                explanation=f"Building {bld_code} contains multiple units with identical identifiers.",
                suggested_remediation="Assign distinct unit numbers or codes to avoid registry conflicts."
            )
        return None


class RuleUnit003UlpinCollision(CadastralValidationRule):
    rule_id = "RULE-UNIT-003"
    category = RuleCategory.UNIT_INTEGRITY
    severity = RuleSeverity.ERROR
    title = "Unique 3D ULPIN Assignment"
    description = "Enforces that 3D ULPINs are globally unique across all property units."
    affected_entity_types = ["UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        ulpins = context.get("all_ulpins", [])
        unit_ulpin = context.get("ulpin_3d")
        unit_id = str(context.get("id", "UNKNOWN"))
        unit_num = context.get("unit_number", unit_id)

        if unit_ulpin and ulpins.count(unit_ulpin) > 1:
            return ValidationIssue(
                rule_id=self.rule_id,
                category=self.category,
                severity=self.severity,
                entity_type="UNIT",
                entity_id=unit_id,
                entity_identifier=unit_num,
                measured_values={"ulpin_3d": unit_ulpin},
                expected_condition="Globally unique 3D ULPIN",
                actual_condition=f"3D ULPIN '{unit_ulpin}' is assigned to multiple entities",
                explanation=f"Unit {unit_num} shares an identical 3D ULPIN with another unit.",
                suggested_remediation="Regenerate 3D ULPIN using unique spatial and hierarchical parameters."
            )
        return None


# ============================================================================
# 6. INFRASTRUCTURE & UNDERGROUND/ELEVATED COEXISTENCE RULES
# ============================================================================

class RuleInf001InfrastructureIntersection(CadastralValidationRule):
    rule_id = "RULE-INF-001"
    category = RuleCategory.INFRASTRUCTURE
    severity = RuleSeverity.WARNING
    title = "Infrastructure Crossing / Unrecorded Easement"
    description = "Flags intersection between private property and infrastructure when easement status is unrecorded."
    affected_entity_types = ["UNIT"]

    def evaluate(self, context: Dict[str, Any]) -> Optional[ValidationIssue]:
        clashes = context.get("clashes", [])
        for c in clashes:
            if c.classification.value == "UNKNOWN_REQUIRES_REVIEW":
                return ValidationIssue(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=self.severity,
                    entity_type="UNIT",
                    entity_id=c.entity_a_id,
                    entity_identifier=c.entity_a_identifier,
                    measured_values={
                        "crossing_entity": c.entity_b_identifier,
                        "overlap_volume_cu_m": c.estimated_overlap_volume_cu_m
                    },
                    expected_condition="Registered infrastructure easement or clear spatial separation",
                    actual_condition=f"Physical intersection with {c.entity_b_identifier}; easement status unknown",
                    explanation=f"Unit {c.entity_a_identifier} intersects {c.entity_b_identifier}. "
                                "Legal rights and service easements cannot be confirmed from geometry alone.",
                    suggested_remediation="Verify whether a formal utility easement or right-of-way deed exists."
                )
        return None


# ============================================================================
# RULE REGISTRY
# ============================================================================

class ValidationRuleRegistry:
    """Central registry of deterministic cadastral validation rules."""

    _RULES: Dict[str, CadastralValidationRule] = {}

    @classmethod
    def register(cls, rule_cls: Type[CadastralValidationRule]) -> None:
        instance = rule_cls()
        cls._RULES[instance.rule_id] = instance

    @classmethod
    def get_rule(cls, rule_id: str) -> Optional[CadastralValidationRule]:
        return cls._RULES.get(rule_id)

    @classmethod
    def list_rules(cls) -> List[ValidationRuleDefinition]:
        return [r.get_definition() for r in cls._RULES.values()]

    @classmethod
    def get_rules_by_category(cls, category: RuleCategory) -> List[CadastralValidationRule]:
        return [r for r in cls._RULES.values() if r.category == category]


# Register all built-in rules
for rule_class in [
    # Geometry
    RuleGeo001ValidGeometry,
    RuleGeo002RingClosure,
    RuleGeo003PositiveArea,
    RuleGeo004DisconnectedMultiPolygon,
    RuleGeo005NormalizationDrift,
    # Hierarchy
    RuleHier001BuildingInParcel,
    RuleHier002FloorInBuilding,
    RuleHier003UnitInParentFootprint,
    RuleHier004UnitInBuildingZ,
    RuleHier005UnitFloorElevationMatch,
    RuleHier006OrphanedEntity,
    # Floor Strata
    RuleFlr001NonOverlappingFloors,
    RuleFlr002VerticalFloorGaps,
    RuleFlr003DuplicateFloorCodes,
    RuleFlr004MonotonicFloorOrdering,
    RuleFlr005ValidFloorBounds,
    RuleFlr006BasementDatumConsistency,
    RuleFlr007ElevatedDatumConsistency,
    # Topology 3D
    RuleTopo001PropertyConflict,
    RuleTopo002NearBoundaryTolerance,
    RuleTopo003CommonAreaCoexistence,
    # Unit Integrity
    RuleUnit001ZeroNearZeroVolume,
    RuleUnit002DuplicateUnitIdentifiers,
    RuleUnit003UlpinCollision,
    # Infrastructure
    RuleInf001InfrastructureIntersection,
]:
    ValidationRuleRegistry.register(rule_class)
