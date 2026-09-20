"""
Cadastre Service: Business logic for Land Parcels, Buildings, Floor Levels, and 3D Units.
"""

from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.parcel import LandParcel
from app.models.building import Building
from app.models.floor import FloorLevel
from app.models.unit import VerticalUnit
from app.schemas.parcel import ParcelCreate, ParcelUpdate
from app.schemas.building import BuildingCreate, BuildingUpdate
from app.schemas.floor import FloorCreate, FloorUpdate
from app.schemas.unit import UnitCreate, UnitUpdate
from app.core.exceptions import (
    EntityNotFoundException,
    DuplicateEntityException,
    SpatialContainmentException,
    SpatialClashException,
    CadastreException,
)
from app.services.ulpin_engine import generate_2d_ulpin, generate_3d_ulpin
from app.services.spatial_engine import (
    geojson_to_shapely,
    compute_centroid,
    compute_geodesic_area_sqm,
    compute_projected_spatial_metrics,
    compute_volumetric_bounds,
    check_containment,
    evaluate_building_containment,
    detect_3d_clashes,
    build_3d_geojson_feature,
)
from app.core.spatial_volume import classify_vertical_position, VerticalClassification, PrismVolume
from app.services.floor_engine import FloorEngine
from app.services.cadastral_relationship_engine import CadastralRelationshipEngine
from app.services.digital_twin_service import DigitalTwinService
from app.services.geojson_serializer import CadastralGeoJSONSerializer
from app.core.logging import logger


class CadastreService:
    # -------------------------------------------------------------
    # PARCELS
    # -------------------------------------------------------------
    @staticmethod
    def create_parcel(db: Session, data: ParcelCreate) -> LandParcel:
        geom_dict = data.geometry_geojson.model_dump()
        metrics = compute_projected_spatial_metrics(geom_dict)
        centroid_lat = metrics["centroid_lat"]
        centroid_lon = metrics["centroid_lon"]
        area_sqm = metrics["area_sqm"]

        # Generate deterministic 2D ULPIN
        ulpin = generate_2d_ulpin(
            lat=centroid_lat,
            lon=centroid_lon,
            state_code=data.state_code,
            survey_number=data.survey_number
        )

        existing = db.execute(select(LandParcel).where(LandParcel.ulpin == ulpin)).scalar_one_or_none()
        if existing:
            raise DuplicateEntityException("LandParcel", "ULPIN", ulpin)

        # Merge spatial metadata
        meta = dict(data.spatial_metadata or {})
        meta["source_crs"] = metrics["source_crs"]
        meta["projected_crs"] = metrics["projected_crs"]
        meta["perimeter_m"] = metrics["perimeter_m"]
        meta["bbox"] = metrics["bbox"]
        if metrics["was_repaired"]:
            meta["was_repaired"] = True
            meta["repair_actions"] = metrics["repair_actions"]

        parcel = LandParcel(
            ulpin=ulpin,
            state_code=data.state_code,
            district_code=data.district_code,
            village_code=data.village_code,
            survey_number=data.survey_number,
            subdivision_number=data.subdivision_number,
            area_sqm=area_sqm,
            centroid_lat=centroid_lat,
            centroid_lon=centroid_lon,
            base_elevation_m=data.base_elevation_m,
            geometry_geojson=metrics["normalized_geojson"],
            spatial_metadata=meta,
            status=data.status
        )
        db.add(parcel)
        db.commit()
        db.refresh(parcel)
        logger.info(f"Created LandParcel id={parcel.id}, ulpin={parcel.ulpin}, area={parcel.area_sqm} m2")
        return parcel

    @staticmethod
    def get_parcel(db: Session, parcel_id: str) -> LandParcel:
        parcel = db.get(LandParcel, parcel_id)
        if not parcel:
            raise EntityNotFoundException("LandParcel", parcel_id)
        return parcel

    @staticmethod
    def get_parcel_by_ulpin(db: Session, ulpin: str) -> LandParcel:
        parcel = db.execute(select(LandParcel).where(LandParcel.ulpin == ulpin)).scalar_one_or_none()
        if not parcel:
            raise EntityNotFoundException("LandParcel", ulpin)
        return parcel

    @staticmethod
    def list_parcels(db: Session, skip: int = 0, limit: int = 20) -> Tuple[List[LandParcel], int]:
        total = db.scalar(select(func.count(LandParcel.id))) or 0
        items = db.execute(select(LandParcel).offset(skip).limit(limit)).scalars().all()
        return list(items), total

    @staticmethod
    def update_parcel(db: Session, parcel_id: str, data: ParcelUpdate) -> LandParcel:
        parcel = CadastreService.get_parcel(db, parcel_id)
        update_data = data.model_dump(exclude_unset=True)

        if "geometry_geojson" in update_data and update_data["geometry_geojson"]:
            geom_dict = update_data["geometry_geojson"]
            poly = geojson_to_shapely(geom_dict)
            lat, lon = compute_centroid(poly)
            parcel.centroid_lat = lat
            parcel.centroid_lon = lon
            parcel.area_sqm = compute_geodesic_area_sqm(poly)
            parcel.geometry_geojson = geom_dict

        for key, value in update_data.items():
            if key != "geometry_geojson":
                setattr(parcel, key, value)

        db.commit()
        db.refresh(parcel)
        return parcel

    @staticmethod
    def delete_parcel(db: Session, parcel_id: str) -> None:
        parcel = CadastreService.get_parcel(db, parcel_id)
        db.delete(parcel)
        db.commit()

    # -------------------------------------------------------------
    # BUILDINGS
    # -------------------------------------------------------------
    @staticmethod
    def create_building(db: Session, data: BuildingCreate) -> Building:
        parcel = CadastreService.get_parcel(db, data.parcel_id)
        footprint_dict = data.footprint_geojson.model_dump()

        # Validate containment within parent parcel boundary using projected UTM
        containment = evaluate_building_containment(footprint_dict, parcel.geometry_geojson)
        if not containment["is_contained"]:
            raise SpatialContainmentException(
                f"Building footprint {containment['status']}: exceeds parent parcel by {containment['excess_area_sqm']:.2f} sq m ({containment['excess_percentage']}%)",
                details={"parcel_id": parcel.id, "containment": containment, "excess_sqm": containment["excess_area_sqm"]}
            )

        meta = dict(data.spatial_metadata or {})
        meta["building_area_sqm"] = containment["building_area_sqm"]

        building = Building(
            parcel_id=parcel.id,
            building_name=data.building_name,
            building_code=data.building_code,
            rera_number=data.rera_number,
            structure_type=data.structure_type,
            floors_above_ground=data.floors_above_ground,
            basement_floors=data.basement_floors,
            total_height_m=data.total_height_m,
            ground_elevation_m=data.ground_elevation_m,
            footprint_geojson=footprint_dict,
            spatial_metadata=data.spatial_metadata or {},
            status=data.status
        )
        db.add(building)
        db.commit()
        db.refresh(building)
        logger.info(f"Created Building id={building.id}, code={building.building_code}")
        return building

    @staticmethod
    def get_building(db: Session, building_id: str) -> Building:
        building = db.get(Building, building_id)
        if not building:
            raise EntityNotFoundException("Building", building_id)
        return building

    @staticmethod
    def list_buildings(
        db: Session, parcel_id: Optional[str] = None, skip: int = 0, limit: int = 20
    ) -> Tuple[List[Building], int]:
        stmt = select(Building)
        count_stmt = select(func.count(Building.id))
        if parcel_id:
            stmt = stmt.where(Building.parcel_id == parcel_id)
            count_stmt = count_stmt.where(Building.parcel_id == parcel_id)

        total = db.scalar(count_stmt) or 0
        items = db.execute(stmt.offset(skip).limit(limit)).scalars().all()
        return list(items), total

    @staticmethod
    def update_building(db: Session, building_id: str, data: BuildingUpdate) -> Building:
        building = CadastreService.get_building(db, building_id)
        update_data = data.model_dump(exclude_unset=True)

        if "footprint_geojson" in update_data and update_data["footprint_geojson"]:
            footprint_dict = update_data["footprint_geojson"]
            parcel = CadastreService.get_parcel(db, building.parcel_id)
            is_contained, excess = check_containment(footprint_dict, parcel.geometry_geojson)
            if not is_contained:
                raise SpatialContainmentException(
                    f"Updated building footprint exceeds parcel boundary by {excess:.2f} sq m"
                )
            building.footprint_geojson = footprint_dict

        for key, value in update_data.items():
            if key != "footprint_geojson":
                setattr(building, key, value)

        db.commit()
        db.refresh(building)
        return building

    @staticmethod
    def delete_building(db: Session, building_id: str) -> None:
        building = CadastreService.get_building(db, building_id)
        db.delete(building)
        db.commit()

    # -------------------------------------------------------------
    # FLOORS
    # -------------------------------------------------------------
    @staticmethod
    def create_floor(db: Session, data: FloorCreate) -> FloorLevel:
        building = CadastreService.get_building(db, data.building_id)
        floor_height = round(data.z_max - data.z_min, 3)

        footprint_dict = None
        if data.footprint_geojson:
            footprint_dict = data.footprint_geojson.model_dump()
            is_contained, excess = check_containment(footprint_dict, building.footprint_geojson)
            if not is_contained:
                raise SpatialContainmentException(
                    f"Floor footprint exceeds building footprint by {excess:.2f} sq m"
                )

        floor = FloorLevel(
            building_id=building.id,
            level_number=data.level_number,
            level_code=data.level_code.upper(),
            level_type=data.level_type,
            z_min=data.z_min,
            z_max=data.z_max,
            floor_height_m=floor_height,
            footprint_geojson=footprint_dict,
            spatial_metadata=data.spatial_metadata or {},
            status=data.status
        )
        db.add(floor)
        db.commit()
        db.refresh(floor)
        logger.info(f"Created FloorLevel id={floor.id}, code={floor.level_code}")
        return floor

    @staticmethod
    def get_floor(db: Session, floor_id: str) -> FloorLevel:
        floor = db.get(FloorLevel, floor_id)
        if not floor:
            raise EntityNotFoundException("FloorLevel", floor_id)
        return floor

    @staticmethod
    def list_floors(
        db: Session, building_id: Optional[str] = None, skip: int = 0, limit: int = 50
    ) -> Tuple[List[FloorLevel], int]:
        stmt = select(FloorLevel)
        count_stmt = select(func.count(FloorLevel.id))
        if building_id:
            stmt = stmt.where(FloorLevel.building_id == building_id)
            count_stmt = count_stmt.where(FloorLevel.building_id == building_id)

        total = db.scalar(count_stmt) or 0
        items = db.execute(stmt.offset(skip).limit(limit)).scalars().all()
        return list(items), total

    @staticmethod
    def update_floor(db: Session, floor_id: str, data: FloorUpdate) -> FloorLevel:
        floor = CadastreService.get_floor(db, floor_id)
        update_data = data.model_dump(exclude_unset=True)

        if "z_min" in update_data or "z_max" in update_data:
            new_z_min = update_data.get("z_min", floor.z_min)
            new_z_max = update_data.get("z_max", floor.z_max)
            if new_z_max <= new_z_min:
                raise ValueError("z_max must be greater than z_min")
            floor.floor_height_m = round(new_z_max - new_z_min, 3)

        for key, value in update_data.items():
            if key == "footprint_geojson" and value:
                floor.footprint_geojson = value.model_dump() if hasattr(value, "model_dump") else value
            else:
                setattr(floor, key, value)

        db.commit()
        db.refresh(floor)
        return floor

    @staticmethod
    def delete_floor(db: Session, floor_id: str) -> None:
        floor = CadastreService.get_floor(db, floor_id)
        db.delete(floor)
        db.commit()

    # -------------------------------------------------------------
    # VERTICAL UNITS (3D Cadastre)
    # -------------------------------------------------------------
    @staticmethod
    def create_unit(db: Session, data: UnitCreate, enforce_clash_free: bool = True) -> VerticalUnit:
        floor = CadastreService.get_floor(db, data.floor_id)
        building = floor.building
        parcel = building.parcel

        footprint_dict = data.footprint_geojson.model_dump()

        # 1. Verify vertical elevation conforms to floor bounds (or spanned floors if multi-floor)
        if data.is_multi_floor and data.floor_span:
            spanned_floors = db.execute(select(FloorLevel).where(FloorLevel.id.in_(data.floor_span))).scalars().all()
            if spanned_floors:
                span_z_min = min(f.z_min for f in spanned_floors)
                span_z_max = max(f.z_max for f in spanned_floors)
                if data.z_min < span_z_min - 0.1 or data.z_max > span_z_max + 0.1:
                    raise CadastreException(
                        f"Multi-floor unit elevation range [{data.z_min}, {data.z_max}] exceeds spanned floor bounds [{span_z_min}, {span_z_max}]"
                    )
            elif data.z_min < floor.z_min - 0.1 or data.z_max > floor.z_max + 0.1:
                raise CadastreException(
                    f"Unit elevation range [{data.z_min}, {data.z_max}] exceeds floor bounds [{floor.z_min}, {floor.z_max}]"
                )
        elif data.z_min < floor.z_min - 0.1 or data.z_max > floor.z_max + 0.1:
            raise CadastreException(
                f"Unit elevation range [{data.z_min}, {data.z_max}] exceeds floor bounds [{floor.z_min}, {floor.z_max}]"
            )

        # 2. Check 2D containment within building footprint (or floor footprint)
        outer_footprint = floor.footprint_geojson or building.footprint_geojson
        is_contained, excess = check_containment(footprint_dict, outer_footprint)
        if not is_contained:
            raise SpatialContainmentException(
                f"Unit footprint extends outside building/floor boundary by {excess:.2f} sq m",
                details={"floor_id": floor.id, "excess_sqm": excess}
            )

        # 3. Compute area & 3D volume
        vol_data = compute_volumetric_bounds(footprint_dict, data.z_min, data.z_max)

        # 4. Generate Prototype 3D ULPIN
        ulpin_3d = generate_3d_ulpin(
            base_ulpin=parcel.ulpin,
            level_code=floor.level_code,
            unit_code=data.unit_code
        )

        existing_unit = db.execute(select(VerticalUnit).where(VerticalUnit.ulpin_3d == ulpin_3d)).scalar_one_or_none()
        if existing_unit:
            raise DuplicateEntityException("VerticalUnit", "3D ULPIN", ulpin_3d)

        # 5. Check 3D clashes against other units on this building
        existing_units = db.execute(
            select(VerticalUnit)
            .join(FloorLevel, VerticalUnit.floor_id == FloorLevel.id)
            .where(FloorLevel.building_id == building.id)
        ).scalars().all()

        unit_dict_candidate = {
            "id": "candidate",
            "ulpin_3d": ulpin_3d,
            "unit_number": data.unit_number,
            "footprint_geojson": footprint_dict,
            "z_min": data.z_min,
            "z_max": data.z_max
        }
        units_to_check = [
            {
                "id": str(u.id),
                "ulpin_3d": u.ulpin_3d,
                "unit_number": u.unit_number,
                "footprint_geojson": u.footprint_geojson,
                "z_min": u.z_min,
                "z_max": u.z_max
            }
            for u in existing_units
        ] + [unit_dict_candidate]

        clashes = detect_3d_clashes(units_to_check)
        candidate_clashes = [c for c in clashes if c["unit_a_id"] == "candidate" or c["unit_b_id"] == "candidate"]

        if candidate_clashes and enforce_clash_free:
            raise SpatialClashException(
                f"Cannot register unit: 3D spatial collision detected with existing units.",
                clashes=candidate_clashes
            )

        unit = VerticalUnit(
            floor_id=floor.id,
            unit_number=data.unit_number,
            unit_code=data.unit_code.upper(),
            unit_type=data.unit_type,
            ulpin_3d=ulpin_3d,
            ulpin_status="PROTOTYPE_GENERATED",
            footprint_geojson=footprint_dict,
            z_min=data.z_min,
            z_max=data.z_max,
            carpet_area_sqm=vol_data["area_sqm"],
            builtup_area_sqm=data.builtup_area_sqm or vol_data["area_sqm"],
            volume_cu_m=vol_data["volume_cu_m"],
            is_clash_free=len(candidate_clashes) == 0,
            is_multi_floor=data.is_multi_floor,
            floor_span=data.floor_span,
            spatial_metadata=data.spatial_metadata or {},
            status=data.status
        )
        db.add(unit)
        db.commit()
        db.refresh(unit)
        logger.info(f"Created VerticalUnit id={unit.id}, 3D ULPIN={unit.ulpin_3d}, volume={unit.volume_cu_m} m3")
        return unit

    @staticmethod
    def get_unit(db: Session, unit_id: str) -> VerticalUnit:
        unit = db.get(VerticalUnit, unit_id)
        if not unit:
            raise EntityNotFoundException("VerticalUnit", unit_id)
        return unit

    @staticmethod
    def get_unit_by_ulpin_3d(db: Session, ulpin_3d: str) -> VerticalUnit:
        unit = db.execute(select(VerticalUnit).where(VerticalUnit.ulpin_3d == ulpin_3d)).scalar_one_or_none()
        if not unit:
            raise EntityNotFoundException("VerticalUnit", ulpin_3d)
        return unit

    @staticmethod
    def list_units(
        db: Session,
        floor_id: Optional[str] = None,
        building_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[VerticalUnit], int]:
        stmt = select(VerticalUnit)
        count_stmt = select(func.count(VerticalUnit.id))

        if floor_id:
            stmt = stmt.where(VerticalUnit.floor_id == floor_id)
            count_stmt = count_stmt.where(VerticalUnit.floor_id == floor_id)
        elif building_id:
            stmt = stmt.join(FloorLevel, VerticalUnit.floor_id == FloorLevel.id).where(FloorLevel.building_id == building_id)
            count_stmt = count_stmt.join(FloorLevel, VerticalUnit.floor_id == FloorLevel.id).where(FloorLevel.building_id == building_id)

        total = db.scalar(count_stmt) or 0
        items = db.execute(stmt.offset(skip).limit(limit)).scalars().all()
        return list(items), total

    @staticmethod
    def update_unit(db: Session, unit_id: str, data: UnitUpdate) -> VerticalUnit:
        unit = CadastreService.get_unit(db, unit_id)
        update_data = data.model_dump(exclude_unset=True)

        needs_recalc = False
        if "footprint_geojson" in update_data and update_data["footprint_geojson"]:
            unit.footprint_geojson = update_data["footprint_geojson"]
            needs_recalc = True
        if "z_min" in update_data:
            unit.z_min = update_data["z_min"]
            needs_recalc = True
        if "z_max" in update_data:
            unit.z_max = update_data["z_max"]
            needs_recalc = True

        if needs_recalc:
            vol_data = compute_volumetric_bounds(unit.footprint_geojson, unit.z_min, unit.z_max)
            unit.carpet_area_sqm = vol_data["area_sqm"]
            unit.volume_cu_m = vol_data["volume_cu_m"]

        for key, value in update_data.items():
            if key not in ("footprint_geojson", "z_min", "z_max"):
                setattr(unit, key, value)

        db.commit()
        db.refresh(unit)
        return unit

    @staticmethod
    def delete_unit(db: Session, unit_id: str) -> None:
        unit = CadastreService.get_unit(db, unit_id)
        db.delete(unit)
        db.commit()

    # -------------------------------------------------------------
    # 3D SPATIAL VALIDATION & 3D EXPORT
    # -------------------------------------------------------------
    @staticmethod
    def check_building_clashes(db: Session, building_id: str) -> Dict[str, Any]:
        building = CadastreService.get_building(db, building_id)
        units = db.execute(
            select(VerticalUnit)
            .join(FloorLevel, VerticalUnit.floor_id == FloorLevel.id)
            .where(FloorLevel.building_id == building.id)
        ).scalars().all()

        unit_dicts = [
            {
                "id": str(u.id),
                "ulpin_3d": u.ulpin_3d,
                "unit_number": u.unit_number,
                "footprint_geojson": u.footprint_geojson,
                "z_min": u.z_min,
                "z_max": u.z_max
            }
            for u in units
        ]

        clashes = detect_3d_clashes(unit_dicts)
        return {
            "building_id": building_id,
            "total_units_checked": len(units),
            "has_clashes": len(clashes) > 0,
            "clash_count": len(clashes),
            "clashes": clashes
        }

    @staticmethod
    def get_building_3d_geojson(db: Session, building_id: str) -> Dict[str, Any]:
        """Builds a 3D GeoJSON FeatureCollection ready for web visualizers."""
        building = CadastreService.get_building(db, building_id)
        units = db.execute(
            select(VerticalUnit)
            .join(FloorLevel, VerticalUnit.floor_id == FloorLevel.id)
            .where(FloorLevel.building_id == building.id)
        ).scalars().all()

        features = [build_3d_geojson_feature(u) for u in units]
        return {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "building_id": building.id,
                "building_name": building.building_name,
                "building_code": building.building_code,
                "parcel_id": building.parcel_id,
                "total_units": len(units)
            }
        }

    # -------------------------------------------------------------
    # 3D CADASTRAL ENGINE EXTENSIONS
    # -------------------------------------------------------------
    @staticmethod
    def validate_building_floor_strata(db: Session, building_id: str) -> Dict[str, Any]:
        """Validates vertical floor consistency, ground elevation rules, and non-overlapping strata."""
        building = CadastreService.get_building(db, building_id)
        floors = db.execute(
            select(FloorLevel).where(FloorLevel.building_id == building.id).order_by(FloorLevel.level_number)
        ).scalars().all()

        floor_dicts = [
            {
                "id": str(f.id),
                "level_number": f.level_number,
                "level_code": f.level_code,
                "level_type": f.level_type,
                "z_min": f.z_min,
                "z_max": f.z_max
            }
            for f in floors
        ]
        report = FloorEngine.validate_building_floors(
            building_id=building.id,
            ground_elevation_m=building.ground_elevation_m,
            total_height_m=building.total_height_m,
            floors=floor_dicts
        )
        return report.to_dict()

    @staticmethod
    def validate_unit_relationships(
        db: Session, unit_id: str, allow_multi_floor: bool = True
    ) -> Dict[str, Any]:
        """Evaluates hierarchical containment for a unit across Floor, Building, and Parcel."""
        unit = CadastreService.get_unit(db, unit_id)
        floor = unit.floor
        building = floor.building
        parcel = building.parcel

        floor_check = CadastralRelationshipEngine.check_floor_contains_unit(
            floor, unit, allow_multi_floor=allow_multi_floor
        )
        bld_check = CadastralRelationshipEngine.check_building_contains_unit(building, unit)
        pcl_check = CadastralRelationshipEngine.check_parcel_contains_unit(parcel, unit)

        all_valid = floor_check.is_valid and bld_check.is_valid and pcl_check.is_valid

        return {
            "unit_id": unit.id,
            "ulpin_3d": unit.ulpin_3d,
            "all_valid": all_valid,
            "floor_contains_unit": floor_check.model_dump(),
            "building_contains_unit": bld_check.model_dump(),
            "parcel_contains_unit": pcl_check.model_dump()
        }

    @staticmethod
    def get_parcel_digital_twin(db: Session, parcel_id: str):
        """Assembles the complete 3D Cadastral Digital Twin for a parcel."""
        return DigitalTwinService.assemble_digital_twin(db, parcel_id)

    @staticmethod
    def get_parcel_digital_twin_3d_geojson(db: Session, parcel_id: str) -> Dict[str, Any]:
        """Serializes the parcel's digital twin into a multi-layered 3D GeoJSON FeatureCollection."""
        dt = DigitalTwinService.assemble_digital_twin(db, parcel_id)
        return CadastralGeoJSONSerializer.serialize_digital_twin_3d(dt)

    @staticmethod
    def query_units_spatial(
        db: Session,
        parcel_id: Optional[str] = None,
        building_id: Optional[str] = None,
        floor_id: Optional[str] = None,
        unit_type: Optional[str] = None,
        elevation_z: Optional[float] = None,
        vertical_classification: Optional[str] = None,
        has_clashes: Optional[bool] = None,
        bbox_3d: Optional[List[float]] = None,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[VerticalUnit], int]:
        """
        Executes advanced 3D spatial queries across vertical units:
        Filters by parcel, building, floor, elevation Z, classification, clashes, or 3D bounding box.
        """
        stmt = select(VerticalUnit).join(FloorLevel, VerticalUnit.floor_id == FloorLevel.id)
        stmt = stmt.join(Building, FloorLevel.building_id == Building.id)

        if parcel_id:
            stmt = stmt.where(Building.parcel_id == parcel_id)
        if building_id:
            stmt = stmt.where(Building.id == building_id)
        if floor_id:
            stmt = stmt.where(FloorLevel.id == floor_id)
        if unit_type:
            stmt = stmt.where(VerticalUnit.unit_type == unit_type.upper())
        if has_clashes is not None:
            stmt = stmt.where(VerticalUnit.is_clash_free == (not has_clashes))
        if elevation_z is not None:
            stmt = stmt.where(VerticalUnit.z_min <= elevation_z, VerticalUnit.z_max >= elevation_z)

        # Retrieve candidates for Python-level geometric/vertical refinement
        units = db.execute(stmt).scalars().all()
        filtered = []

        for u in units:
            bld = u.floor.building
            # Vertical classification filter
            if vertical_classification:
                v_class = classify_vertical_position(u.z_min, u.z_max, bld.ground_elevation_m)
                if v_class.value != vertical_classification.upper():
                    continue

            # 3D bounding box filter [min_lon, min_lat, min_z, max_lon, max_lat, max_z]
            if bbox_3d and len(bbox_3d) == 6:
                min_lon, min_lat, min_z, max_lon, max_lat, max_z = bbox_3d
                prism = PrismVolume(
                    footprint_geojson=u.footprint_geojson,
                    z_min=u.z_min,
                    z_max=u.z_max,
                    ground_elevation_m=bld.ground_elevation_m
                )
                if not prism.intersects_bbox_3d(min_lon, min_lat, min_z, max_lon, max_lat, max_z):
                    continue

            filtered.append(u)

        total = len(filtered)
        paginated = filtered[skip : skip + limit]
        return paginated, total
