"""
Temporal 3D Change & Cadastral Property Intelligence Service.
SIH 26011 - 3D ULPIN & Vertical Property Mapping System.

Performs deterministic geometric and attribution differences between
a registered baseline Digital Twin and a subsequent survey or AI proposal.

CRITICAL PRINCIPLES:
1. Registered cadastral state is the baseline.
2. New imagery/elevation/geometry provides observations.
3. Advisory only - does NOT make legal ownership decisions.
4. Does NOT claim structural collapse prediction or disaster forecasting.
5. Does NOT automatically mutate registered cadastral truth without surveyor review.
"""

from typing import Dict, Any, Optional, List, Tuple
import uuid
import shapely.geometry
from shapely.geometry import shape, Polygon, MultiPolygon
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.schemas.temporal_change import (
    DigitalTwinSnapshot,
    TemporalComparisonConfig,
    TemporalChangeReport,
    ChangeEvent,
    ChangeType,
    ChangeClassification,
    FootprintChangeClass,
    ChangeSeverity,
    FootprintComparisonResult,
    HeightComparisonResult,
    FloorComparisonResult,
    UnitComparisonResult,
)
from app.models.parcel import LandParcel
from app.models.building import Building
from app.models.floor import FloorLevel
from app.models.unit import VerticalUnit
from app.services.spatial_engine import (
    geojson_to_shapely,
    compute_projected_spatial_metrics,
)
from app.core.spatial_volume import (
    classify_vertical_position,
    VerticalClassification,
)
from app.core.exceptions import EntityNotFoundException, CadastreException
from app.ml.models.anomaly_detector import CadastralMLAnomalyDetector


class TemporalChangeService:
    """
    Orchestrates deterministic comparison of versioned 3D digital twins.
    """

    @classmethod
    def create_snapshot_from_parcel(cls, db: Session, parcel_id: str) -> DigitalTwinSnapshot:
        """
        Builds an authoritative baseline DigitalTwinSnapshot from the registered database.
        """
        parcel = db.get(LandParcel, parcel_id)
        if not parcel:
            raise EntityNotFoundException("LandParcel", parcel_id)

        building = db.execute(
            select(Building).where(Building.parcel_id == parcel.id).order_by(Building.created_at)
        ).scalars().first()

        floors_orm = []
        units_orm = []
        if building:
            floors_orm = db.execute(
                select(FloorLevel).where(FloorLevel.building_id == building.id).order_by(FloorLevel.level_number)
            ).scalars().all()
            for fl in floors_orm:
                fl_units = db.execute(
                    select(VerticalUnit).where(VerticalUnit.floor_id == fl.id).order_by(VerticalUnit.unit_number)
                ).scalars().all()
                units_orm.extend(fl_units)

        footprint = building.footprint_geojson if building else parcel.geometry_geojson
        ground_z = building.ground_elevation_m if building else (parcel.base_elevation_m or 0.0)
        total_h = building.total_height_m if building else 0.0

        floors_data = [
            {
                "id": str(f.id),
                "level_code": f.level_code,
                "level_number": f.level_number,
                "z_min": f.z_min,
                "z_max": f.z_max,
                "floor_height_m": f.floor_height_m,
                "classification": "UNDERGROUND" if f.level_code.startswith("B") else ("GROUND_LEVEL" if f.level_code == "G00" else "ELEVATED")
            }
            for f in floors_orm
        ]

        units_data = [
            {
                "id": str(u.id),
                "unit_number": u.unit_number,
                "unit_code": u.unit_code,
                "ulpin_3d": u.ulpin_3d,
                "z_min": u.z_min,
                "z_max": u.z_max,
                "carpet_area_sqm": u.carpet_area_sqm,
                "volume_cu_m": u.volume_cu_m,
                "is_multi_floor": u.is_multi_floor,
                "floor_span": u.floor_span,
                "classification": classify_vertical_position(u.z_min, u.z_max, ground_z).value
            }
            for u in units_orm
        ]

        bld_meta = building.spatial_metadata if building and building.spatial_metadata else {}

        return DigitalTwinSnapshot(
            snapshot_id=f"SNAP-REG-{str(parcel.id)[:8].upper()}",
            entity_id=str(parcel.id),
            version="REGISTERED_TRUTH",
            observation_timestamp=parcel.created_at.isoformat() if hasattr(parcel.created_at, "isoformat") else str(parcel.created_at),
            source="REGISTERED_CADASTRAL_TRUTH",
            footprint_geojson=footprint,
            ground_elevation_m=ground_z,
            total_height_m=total_h,
            height_source=bld_meta.get("height_source", "OBSERVED_SURVEY_METADATA"),
            height_uncertainty_m=bld_meta.get("uncertainty_m", 0.10),
            floors=floors_data,
            units=units_data,
            provenance={
                "parcel_ulpin": parcel.ulpin,
                "survey_number": parcel.survey_number,
                "state_code": parcel.state_code
            }
        )

    @classmethod
    def compare_footprints(
        cls,
        baseline_geom: Optional[Dict[str, Any]],
        new_geom: Optional[Dict[str, Any]],
        config: TemporalComparisonConfig
    ) -> FootprintComparisonResult:
        """
        Rigorously compares baseline and new building footprints via Shapely geometry operations.
        Computes metric area differences, perimeter differences, intersection, union, IoU,
        and centroid displacement.
        """
        if not baseline_geom and not new_geom:
            return FootprintComparisonResult(
                baseline_area_sqm=0.0, new_area_sqm=0.0, area_delta_sqm=0.0, area_pct_change=0.0,
                baseline_perimeter_m=0.0, new_perimeter_m=0.0, perimeter_delta_m=0.0,
                intersection_area_sqm=0.0, union_area_sqm=0.0, iou=1.0,
                centroid_displacement_m=0.0, classification=FootprintChangeClass.NO_SIGNIFICANT_CHANGE,
                is_significant=False
            )

        if not baseline_geom and new_geom:
            new_metrics = compute_projected_spatial_metrics(new_geom)
            return FootprintComparisonResult(
                baseline_area_sqm=0.0,
                new_area_sqm=new_metrics["area_sqm"],
                area_delta_sqm=new_metrics["area_sqm"],
                area_pct_change=100.0,
                baseline_perimeter_m=0.0,
                new_perimeter_m=new_metrics["perimeter_m"],
                perimeter_delta_m=new_metrics["perimeter_m"],
                intersection_area_sqm=0.0,
                union_area_sqm=new_metrics["area_sqm"],
                iou=0.0,
                centroid_displacement_m=0.0,
                classification=FootprintChangeClass.NEW_BUILDING,
                is_significant=True
            )

        if baseline_geom and not new_geom:
            base_metrics = compute_projected_spatial_metrics(baseline_geom)
            return FootprintComparisonResult(
                baseline_area_sqm=base_metrics["area_sqm"],
                new_area_sqm=0.0,
                area_delta_sqm=-base_metrics["area_sqm"],
                area_pct_change=-100.0,
                baseline_perimeter_m=base_metrics["perimeter_m"],
                new_perimeter_m=0.0,
                perimeter_delta_m=-base_metrics["perimeter_m"],
                intersection_area_sqm=0.0,
                union_area_sqm=base_metrics["area_sqm"],
                iou=0.0,
                centroid_displacement_m=0.0,
                classification=FootprintChangeClass.REMOVED_BUILDING,
                is_significant=True
            )

        try:
            base_metrics = compute_projected_spatial_metrics(baseline_geom)
            new_metrics = compute_projected_spatial_metrics(new_geom)

            poly_b = geojson_to_shapely(baseline_geom, auto_heal=True)
            poly_n = geojson_to_shapely(new_geom, auto_heal=True)

            # Intersection and Union in relative geometric domain
            inter = poly_b.intersection(poly_n)
            uni = poly_b.union(poly_n)
            iou = round(float(inter.area / uni.area), 4) if uni.area > 0 else 1.0

            area_delta = round(new_metrics["area_sqm"] - base_metrics["area_sqm"], 2)
            area_pct = round((area_delta / base_metrics["area_sqm"]) * 100, 2) if base_metrics["area_sqm"] > 0 else 0.0
            perim_delta = round(new_metrics["perimeter_m"] - base_metrics["perimeter_m"], 2)

            # Centroid displacement calculation (in meters)
            c_lat_b, c_lon_b = base_metrics["centroid_lat"], base_metrics["centroid_lon"]
            c_lat_n, c_lon_n = new_metrics["centroid_lat"], new_metrics["centroid_lon"]
            import math
            dy = (c_lat_n - c_lat_b) * 111132.92
            dx = (c_lon_n - c_lon_b) * (111412.84 * math.cos(math.radians((c_lat_b + c_lat_n) / 2.0)))
            displacement_m = round(math.sqrt(dx * dx + dy * dy), 3)

            # Intersected area in square meters
            inter_sqm = round(base_metrics["area_sqm"] * iou, 2)
            uni_sqm = round(base_metrics["area_sqm"] + new_metrics["area_sqm"] - inter_sqm, 2)
        except Exception:
            return FootprintComparisonResult(
                baseline_area_sqm=0.0,
                new_area_sqm=0.0,
                area_delta_sqm=0.0,
                area_pct_change=0.0,
                baseline_perimeter_m=0.0,
                new_perimeter_m=0.0,
                perimeter_delta_m=0.0,
                intersection_area_sqm=0.0,
                union_area_sqm=0.0,
                iou=0.0,
                centroid_displacement_m=0.0,
                classification=FootprintChangeClass.UNRESOLVED,
                is_significant=True,
            )

        # Classification
        is_sig = (
            iou < config.iou_significance_threshold or
            abs(area_delta) >= config.area_delta_threshold_sqm or
            displacement_m >= config.centroid_displacement_threshold_m
        )

        if not is_sig:
            classification = FootprintChangeClass.NO_SIGNIFICANT_CHANGE
        elif iou >= 0.80 and abs(area_pct) < 15.0:
            classification = FootprintChangeClass.MINOR_GEOMETRY_CHANGE
        else:
            classification = FootprintChangeClass.MAJOR_GEOMETRY_CHANGE

        return FootprintComparisonResult(
            baseline_area_sqm=base_metrics["area_sqm"],
            new_area_sqm=new_metrics["area_sqm"],
            area_delta_sqm=area_delta,
            area_pct_change=area_pct,
            baseline_perimeter_m=base_metrics["perimeter_m"],
            new_perimeter_m=new_metrics["perimeter_m"],
            perimeter_delta_m=perim_delta,
            intersection_area_sqm=inter_sqm,
            union_area_sqm=uni_sqm,
            iou=iou,
            centroid_displacement_m=displacement_m,
            classification=classification,
            is_significant=is_sig
        )

    @classmethod
    def compare_heights(
        cls,
        baseline_h: Optional[float],
        new_h: Optional[float],
        baseline_source: str,
        new_source: str,
        baseline_unc: Optional[float],
        new_unc: Optional[float],
        config: TemporalComparisonConfig
    ) -> HeightComparisonResult:
        """
        Compares baseline and new building heights with uncertainty adjustments.
        Strictly distinguishes OBSERVED_HEIGHT_CHANGE from AI_ESTIMATED_HEIGHT_CHANGE.
        """
        if baseline_h is None or new_h is None:
            return HeightComparisonResult(
                baseline_height_m=baseline_h,
                new_height_m=new_h,
                baseline_source=baseline_source,
                new_source=new_source,
                is_significant=False,
                classification="NO_CHANGE",
                requires_review=False
            )

        delta = round(new_h - baseline_h, 2)
        pct = round((delta / baseline_h) * 100, 2) if baseline_h > 0 else 0.0

        total_unc = (baseline_unc or 0.20) + (new_unc or 0.20)
        unc_adjusted = round(max(0.0, abs(delta) - total_unc), 2)
        is_sig = abs(delta) >= config.height_delta_threshold_m

        is_ai = "AI" in str(new_source).upper() or "REGRESSION" in str(new_source).upper()
        if is_ai:
            classification = "AI_ESTIMATED_HEIGHT_CHANGE"
            requires_review = is_sig
        elif "OBSERVED" in str(new_source).upper() or "LIDAR" in str(new_source).upper() or "DSM" in str(new_source).upper():
            classification = "OBSERVED_HEIGHT_CHANGE"
            requires_review = is_sig and abs(delta) > 1.50
        else:
            classification = "DETERMINISTIC_HEIGHT_CHANGE"
            requires_review = is_sig

        return HeightComparisonResult(
            baseline_height_m=baseline_h,
            new_height_m=new_h,
            height_delta_m=delta,
            height_pct_change=pct,
            baseline_source=baseline_source,
            new_source=new_source,
            uncertainty_adjusted_delta_m=unc_adjusted,
            is_significant=is_sig,
            classification=classification,
            requires_review=requires_review
        )

    @classmethod
    def compare_floors(
        cls,
        baseline_floors: List[Dict[str, Any]],
        new_floors: List[Dict[str, Any]]
    ) -> FloorComparisonResult:
        """
        Compares vertical floor strata between baseline and new observation.
        Detects added/removed floors, basement additions/removals, and level elevation shifts.
        """
        base_map = {f.get("level_code"): f for f in baseline_floors if f.get("level_code")}
        new_map = {f.get("level_code"): f for f in new_floors if f.get("level_code")}

        added = [code for code in new_map if code not in base_map]
        removed = [code for code in base_map if code not in new_map]

        altered = []
        for code, n_fl in new_map.items():
            if code in base_map:
                b_fl = base_map[code]
                z_min_diff = round(n_fl.get("z_min", 0.0) - b_fl.get("z_min", 0.0), 2)
                z_max_diff = round(n_fl.get("z_max", 0.0) - b_fl.get("z_max", 0.0), 2)
                if abs(z_min_diff) > 0.10 or abs(z_max_diff) > 0.10:
                    altered.append({
                        "level_code": code,
                        "previous_z_min": b_fl.get("z_min"),
                        "previous_z_max": b_fl.get("z_max"),
                        "new_z_min": n_fl.get("z_min"),
                        "new_z_max": n_fl.get("z_max"),
                        "z_shift_m": max(abs(z_min_diff), abs(z_max_diff))
                    })

        base_basements = sum(1 for code in base_map if code.startswith("B"))
        new_basements = sum(1 for code in new_map if code.startswith("B"))
        base_elevated = len(base_map) - base_basements
        new_elevated = len(new_map) - new_basements

        requires_review = bool(added or removed or altered)

        return FloorComparisonResult(
            baseline_floor_count=len(base_map),
            new_floor_count=len(new_map),
            floor_count_delta=len(new_map) - len(base_map),
            added_floors=added,
            removed_floors=removed,
            altered_floors=altered,
            basement_delta=new_basements - base_basements,
            elevated_delta=new_elevated - base_elevated,
            requires_review=requires_review
        )

    @classmethod
    def compare_units(
        cls,
        baseline_units: List[Dict[str, Any]],
        new_units: List[Dict[str, Any]]
    ) -> UnitComparisonResult:
        """
        Compares vertical property units between baseline and new observation.
        """
        base_map = {u.get("unit_number", u.get("unit_code")): u for u in baseline_units}
        new_map = {u.get("unit_number", u.get("unit_code")): u for u in new_units}

        added = [num for num in new_map if num not in base_map]
        removed = [num for num in base_map if num not in new_map]

        altered = []
        for num, n_u in new_map.items():
            if num in base_map:
                b_u = base_map[num]
                vol_delta = round(n_u.get("volume_cu_m", 0.0) - b_u.get("volume_cu_m", 0.0), 2)
                area_delta = round(n_u.get("carpet_area_sqm", 0.0) - b_u.get("carpet_area_sqm", 0.0), 2)
                class_changed = n_u.get("classification") != b_u.get("classification")
                span_changed = n_u.get("floor_span") != b_u.get("floor_span")

                if abs(vol_delta) > 5.0 or abs(area_delta) > 1.5 or class_changed or span_changed:
                    altered.append({
                        "unit_identifier": num,
                        "volume_delta_cu_m": vol_delta,
                        "area_delta_sqm": area_delta,
                        "previous_classification": b_u.get("classification"),
                        "new_classification": n_u.get("classification"),
                        "floor_span_changed": span_changed
                    })

        requires_review = bool(added or removed or altered)

        return UnitComparisonResult(
            baseline_unit_count=len(base_map),
            new_unit_count=len(new_map),
            unit_count_delta=len(new_map) - len(base_map),
            added_units=added,
            removed_units=removed,
            altered_units=altered,
            requires_review=requires_review
        )

    @classmethod
    def compare_digital_twins(
        cls,
        baseline: DigitalTwinSnapshot,
        observation: DigitalTwinSnapshot,
        config: Optional[TemporalComparisonConfig] = None
    ) -> TemporalChangeReport:
        """
        Executes end-to-end temporal change comparison between two digital twin snapshots.
        Synthesizes footprint, height, floor, and unit metrics into auditable ChangeEvents
        and a calibrated TECHNICAL_CHANGE_SCORE.
        """
        cfg = config or TemporalComparisonConfig()
        comparison_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"

        # Determine overall classification
        if cfg.is_test_fixture or "TEST" in str(observation.source).upper():
            change_class = ChangeClassification.TEST_FIXTURE_CHANGE
        elif "AI" in str(observation.source).upper() or "REGRESSION" in str(observation.source).upper():
            change_class = ChangeClassification.AI_ESTIMATED_CHANGE
        elif "OBSERVED" in str(observation.source).upper() or "LIDAR" in str(observation.source).upper() or "SURVEY" in str(observation.source).upper():
            change_class = ChangeClassification.OBSERVED_CHANGE
        else:
            change_class = ChangeClassification.DETERMINISTIC_CHANGE

        events: List[ChangeEvent] = []

        # 1. Footprint Comparison
        footprint_cmp = cls.compare_footprints(
            baseline_geom=baseline.footprint_geojson,
            new_geom=observation.footprint_geojson,
            config=cfg
        )

        if footprint_cmp.classification == FootprintChangeClass.NEW_BUILDING:
            events.append(
                ChangeEvent(
                    change_type=ChangeType.BUILDING_ADDED,
                    change_classification=change_class,
                    entity_type="BUILDING",
                    entity_id=observation.entity_id,
                    new_value=footprint_cmp.new_area_sqm,
                    magnitude=footprint_cmp.new_area_sqm,
                    unit="m2",
                    confidence=0.90 if change_class != ChangeClassification.AI_ESTIMATED_CHANGE else 0.70,
                    source=observation.source,
                    requires_review=True,
                    explanation=f"New structure detected with footprint area {footprint_cmp.new_area_sqm:.1f} m²."
                )
            )
        elif footprint_cmp.classification == FootprintChangeClass.REMOVED_BUILDING:
            events.append(
                ChangeEvent(
                    change_type=ChangeType.BUILDING_REMOVED,
                    change_classification=change_class,
                    entity_type="BUILDING",
                    entity_id=baseline.entity_id,
                    previous_value=footprint_cmp.baseline_area_sqm,
                    magnitude=footprint_cmp.baseline_area_sqm,
                    unit="m2",
                    confidence=0.90 if change_class != ChangeClassification.AI_ESTIMATED_CHANGE else 0.70,
                    source=observation.source,
                    requires_review=True,
                    explanation="Registered structure footprint is no longer observed in the new survey."
                )
            )
        elif footprint_cmp.classification == FootprintChangeClass.UNRESOLVED:
            events.append(
                ChangeEvent(
                    change_type=ChangeType.GEOMETRY_UNCERTAIN,
                    change_classification=change_class,
                    entity_type="BUILDING",
                    entity_id=observation.entity_id,
                    previous_value=None,
                    new_value=None,
                    magnitude=0.0,
                    unit="m2",
                    confidence=0.10,
                    source=observation.source,
                    requires_review=True,
                    explanation="Geometry could not be topologically resolved or compared due to invalid coordinates."
                )
            )
        elif footprint_cmp.is_significant:
            events.append(
                ChangeEvent(
                    change_type=ChangeType.FOOTPRINT_CHANGED,
                    change_classification=change_class,
                    entity_type="BUILDING",
                    entity_id=observation.entity_id,
                    previous_value=footprint_cmp.baseline_area_sqm,
                    new_value=footprint_cmp.new_area_sqm,
                    magnitude=abs(footprint_cmp.area_delta_sqm),
                    unit="m2",
                    confidence=0.88 if change_class != ChangeClassification.AI_ESTIMATED_CHANGE else 0.65,
                    source=observation.source,
                    requires_review=True,
                    explanation=(
                        f"Building footprint modified by {footprint_cmp.area_delta_sqm:+.2f} m² "
                        f"({footprint_cmp.area_pct_change:+.1f}%), IoU={footprint_cmp.iou:.3f}, "
                        f"centroid shift={footprint_cmp.centroid_displacement_m:.2f}m."
                    )
                )
            )

        # 2. Height Comparison
        height_cmp = cls.compare_heights(
            baseline_h=baseline.total_height_m,
            new_h=observation.total_height_m,
            baseline_source=baseline.height_source or baseline.source,
            new_source=observation.height_source or observation.source,
            baseline_unc=baseline.height_uncertainty_m,
            new_unc=observation.height_uncertainty_m,
            config=cfg
        )

        if height_cmp.is_significant:
            events.append(
                ChangeEvent(
                    change_type=ChangeType.HEIGHT_CHANGED,
                    change_classification=change_class,
                    entity_type="BUILDING",
                    entity_id=observation.entity_id,
                    previous_value=height_cmp.baseline_height_m,
                    new_value=height_cmp.new_height_m,
                    magnitude=abs(height_cmp.height_delta_m or 0.0),
                    unit="m",
                    confidence=0.85 if "AI" not in height_cmp.new_source else 0.68,
                    source=height_cmp.new_source,
                    requires_review=height_cmp.requires_review,
                    explanation=(
                        f"Building height altered by {height_cmp.height_delta_m:+.2f}m "
                        f"({height_cmp.height_pct_change:+.1f}%) "
                        f"via {height_cmp.classification}."
                    )
                )
            )

        # 3. Floor Comparison
        floor_cmp = cls.compare_floors(
            baseline_floors=baseline.floors,
            new_floors=observation.floors
        )

        if floor_cmp.floor_count_delta != 0 or floor_cmp.added_floors or floor_cmp.removed_floors or floor_cmp.altered_floors:
            events.append(
                ChangeEvent(
                    change_type=ChangeType.FLOOR_STRUCTURE_CHANGED,
                    change_classification=change_class,
                    entity_type="BUILDING",
                    entity_id=observation.entity_id,
                    previous_value=floor_cmp.baseline_floor_count,
                    new_value=floor_cmp.new_floor_count,
                    magnitude=abs(floor_cmp.floor_count_delta),
                    unit="floors",
                    confidence=0.85 if change_class != ChangeClassification.AI_ESTIMATED_CHANGE else 0.65,
                    source=observation.source,
                    requires_review=True,
                    explanation=(
                        f"Floor configuration altered: delta={floor_cmp.floor_count_delta:+d} floors. "
                        f"Added: {floor_cmp.added_floors}, Removed: {floor_cmp.removed_floors}, "
                        f"Altered levels: {len(floor_cmp.altered_floors)}."
                    )
                )
            )

        if floor_cmp.basement_delta != 0:
            events.append(
                ChangeEvent(
                    change_type=ChangeType.BASEMENT_CHANGED,
                    change_classification=change_class,
                    entity_type="BUILDING",
                    entity_id=observation.entity_id,
                    magnitude=abs(floor_cmp.basement_delta),
                    unit="floors",
                    confidence=0.80,
                    source=observation.source,
                    requires_review=True,
                    explanation=f"Basement strata altered by {floor_cmp.basement_delta:+d} sub-levels."
                )
            )

        if floor_cmp.elevated_delta != 0:
            events.append(
                ChangeEvent(
                    change_type=ChangeType.ELEVATED_STRUCTURE_CHANGED,
                    change_classification=change_class,
                    entity_type="BUILDING",
                    entity_id=observation.entity_id,
                    magnitude=abs(floor_cmp.elevated_delta),
                    unit="floors",
                    confidence=0.80,
                    source=observation.source,
                    requires_review=True,
                    explanation=f"Elevated storeys altered by {floor_cmp.elevated_delta:+d} floors."
                )
            )

        # 4. Unit Comparison
        unit_cmp = cls.compare_units(
            baseline_units=baseline.units,
            new_units=observation.units
        )

        if unit_cmp.unit_count_delta != 0 or unit_cmp.added_units or unit_cmp.removed_units or unit_cmp.altered_units:
            events.append(
                ChangeEvent(
                    change_type=ChangeType.VERTICAL_UNIT_CHANGED,
                    change_classification=change_class,
                    entity_type="BUILDING",
                    entity_id=observation.entity_id,
                    previous_value=unit_cmp.baseline_unit_count,
                    new_value=unit_cmp.new_unit_count,
                    magnitude=abs(unit_cmp.unit_count_delta) or len(unit_cmp.altered_units),
                    unit="units",
                    confidence=0.80,
                    source=observation.source,
                    requires_review=True,
                    explanation=(
                        f"Vertical property units modified: delta={unit_cmp.unit_count_delta:+d}, "
                        f"added={len(unit_cmp.added_units)}, removed={len(unit_cmp.removed_units)}, "
                        f"altered={len(unit_cmp.altered_units)}."
                    )
                )
            )

        # 5. Technical Change Score Calculation (Normalized 0.0 to 1.0)
        # Factors: IoU displacement, height delta, floor delta, unit delta
        iou_component = (1.0 - footprint_cmp.iou) * 0.35 if footprint_cmp.classification not in (
            FootprintChangeClass.NEW_BUILDING, FootprintChangeClass.REMOVED_BUILDING
        ) else 0.35

        h_delta = abs(height_cmp.height_delta_m or 0.0)
        h_component = min(1.0, h_delta / 12.0) * 0.35

        fl_delta = abs(floor_cmp.floor_count_delta)
        fl_component = min(1.0, fl_delta / 4.0) * 0.20

        u_delta = abs(unit_cmp.unit_count_delta) + len(unit_cmp.altered_units)
        u_component = min(1.0, u_delta / 8.0) * 0.10

        technical_score = round(min(1.0, iou_component + h_component + fl_component + u_component), 3)
        if len(events) == 0:
            technical_score = 0.0

        if technical_score < 0.05:
            severity = ChangeSeverity.NONE
        elif technical_score < 0.25:
            severity = ChangeSeverity.MINOR
        elif technical_score < 0.55:
            severity = ChangeSeverity.MODERATE
        elif technical_score < 0.80:
            severity = ChangeSeverity.SIGNIFICANT
        else:
            severity = ChangeSeverity.CRITICAL

        requires_review = any(e.requires_review for e in events) or severity in (
            ChangeSeverity.MODERATE, ChangeSeverity.SIGNIFICANT, ChangeSeverity.CRITICAL
        )

        # 6. Cross-reference Anomaly Detector
        detector = CadastralMLAnomalyDetector()
        anomalies = detector.predict({
            "height_m": observation.total_height_m,
            "floor_count": len(observation.floors) if observation.floors else None,
            "footprint_geojson": observation.footprint_geojson
        })
        cross_ref_anomalies = [a.model_dump() for a in anomalies]

        return TemporalChangeReport(
            comparison_id=comparison_id,
            baseline_snapshot_id=baseline.snapshot_id,
            observation_snapshot_id=observation.snapshot_id,
            entity_id=observation.entity_id,
            is_test_fixture=cfg.is_test_fixture or change_class == ChangeClassification.TEST_FIXTURE_CHANGE,
            technical_change_score=technical_score,
            change_severity=severity,
            requires_cadastral_review=requires_review,
            total_change_events=len(events),
            change_events=events,
            footprint_comparison=footprint_cmp,
            height_comparison=height_cmp,
            floor_comparison=floor_cmp,
            unit_comparison=unit_cmp,
            cross_referenced_anomalies=cross_ref_anomalies
        )
