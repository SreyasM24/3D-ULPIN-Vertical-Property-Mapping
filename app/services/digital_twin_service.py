"""
Cadastral Digital Twin Assembly Service.

Assembles the complete hierarchical spatial and legal state of a property:
Parcel -> Buildings -> Floors -> Units -> Ownership -> Validation Status
"""

from typing import Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.parcel import LandParcel
from app.models.building import Building
from app.models.floor import FloorLevel
from app.models.unit import VerticalUnit
from app.models.ownership import OwnershipRecord
from app.schemas.digital_twin import (
    CadastralDigitalTwin,
    DigitalTwinParcel,
    DigitalTwinBuilding,
    DigitalTwinFloor,
    DigitalTwinUnit,
    DigitalTwinSummary,
)
from app.schemas.ownership import OwnershipRead
from app.core.exceptions import EntityNotFoundException
from app.core.spatial_volume import classify_vertical_position, PrismVolume
from app.services.floor_engine import FloorEngine


class DigitalTwinService:
    @staticmethod
    def assemble_digital_twin(db: Session, parcel_id: str) -> CadastralDigitalTwin:
        parcel = db.get(LandParcel, parcel_id)
        if not parcel:
            raise EntityNotFoundException("LandParcel", parcel_id)

        buildings_orm = db.execute(
            select(Building).where(Building.parcel_id == parcel.id).order_by(Building.building_code)
        ).scalars().all()

        dt_buildings: List[DigitalTwinBuilding] = []
        total_units_count = 0
        total_volume_cu_m = 0.0
        total_carpet_area_sqm = 0.0
        total_floors_count = 0
        clashes_count = 0
        vertical_breakdown = {
            "UNDERGROUND": 0,
            "GROUND_LEVEL": 0,
            "ELEVATED": 0,
            "MULTI_LEVEL_INFRASTRUCTURE": 0
        }

        for b in buildings_orm:
            # 1. Building volume & metrics
            bld_prism = FloorEngine.compute_building_volume(
                footprint_geojson=b.footprint_geojson,
                ground_elevation_m=b.ground_elevation_m,
                total_height_m=b.total_height_m,
                basement_depth_m=b.basement_floors * 3.5
            )
            bld_footprint_area = bld_prism.area_sqm
            bld_volume = bld_prism.volume_cu_m

            # 2. Floors
            floors_orm = db.execute(
                select(FloorLevel).where(FloorLevel.building_id == b.id).order_by(FloorLevel.level_number)
            ).scalars().all()
            total_floors_count += len(floors_orm)

            dt_floors: List[DigitalTwinFloor] = []
            for fl in floors_orm:
                # 3. Units
                units_orm = db.execute(
                    select(VerticalUnit).where(VerticalUnit.floor_id == fl.id).order_by(VerticalUnit.unit_number)
                ).scalars().all()
                total_units_count += len(units_orm)

                dt_units: List[DigitalTwinUnit] = []
                for u in units_orm:
                    v_class = classify_vertical_position(u.z_min, u.z_max, b.ground_elevation_m)
                    vertical_breakdown[v_class.value] = vertical_breakdown.get(v_class.value, 0) + 1

                    total_volume_cu_m += u.volume_cu_m
                    total_carpet_area_sqm += u.carpet_area_sqm
                    if not u.is_clash_free:
                        clashes_count += 1

                    # Ownership records
                    ownerships = db.execute(
                        select(OwnershipRecord).where(OwnershipRecord.unit_id == u.id)
                    ).scalars().all()

                    u_meta = u.spatial_metadata or {}
                    u_conf = u_meta.get("confidence")
                    raw_source = str(u_meta.get("source") or "DETERMINISTIC_STRATA")
                    if "AI" in raw_source:
                        tier = "AI_INFERENCE"
                        method_desc = "AI Inferred Strata Decomposition"
                    elif "OBSERVED" in raw_source or "DRONE" in raw_source or "POINT_CLOUD" in raw_source:
                        tier = "OBSERVED"
                        method_desc = "Direct Sensor Telemetry Strata Extrusion"
                    else:
                        tier = "DETERMINISTIC"
                        method_desc = "Parametric Cadastral Strata Decomposition"

                    unit_prov = {
                        "id": f"prov-{u.id}",
                        "target_id": str(u.id),
                        "vertical_classification": v_class.value,
                        "source": raw_source,
                        "source_type": raw_source,
                        "method": method_desc,
                        "model": "CadastralEngine3D",
                        "model_version": "2.1.0",
                        "data_stage": u_meta.get("stage") or "VALIDATED",
                        "evidence_tier": tier,
                        "is_multi_floor": u.is_multi_floor,
                        "floor_span": u.floor_span or [fl.level_code],
                        "confidence": u_conf if isinstance(u_conf, (int, float)) else (0.85 if u_conf == "HIGH" else (0.65 if u_conf == "MEDIUM" else 0.85)),
                        "confidence_level": "HIGH" if (u_conf == "HIGH" or (isinstance(u_conf, (int, float)) and u_conf >= 0.8)) else "MEDIUM",
                        "uncertainty_m": u_meta.get("uncertainty_m") if u_meta.get("uncertainty_m") is not None else 0.30,
                        "timestamp": u.created_at.isoformat() if u.created_at else datetime.now(timezone.utc).isoformat(),
                        "operator_or_system": "Autonomous Deterministic Pipeline",
                        "requires_review": False
                    }

                    dt_units.append(
                        DigitalTwinUnit(
                            id=str(u.id),
                            floor_id=str(u.floor_id),
                            unit_number=u.unit_number,
                            unit_code=u.unit_code,
                            unit_type=u.unit_type,
                            ulpin_3d=u.ulpin_3d,
                            ulpin_status=u.ulpin_status,
                            vertical_classification=v_class.value,
                            z_min=u.z_min,
                            z_max=u.z_max,
                            height_m=round(u.z_max - u.z_min, 3),
                            carpet_area_sqm=u.carpet_area_sqm,
                            volume_cu_m=u.volume_cu_m,
                            is_clash_free=u.is_clash_free,
                            status=u.status,
                            footprint_geojson=u.footprint_geojson,
                            confidence=u_conf if isinstance(u_conf, (int, float)) else (0.85 if u_conf == "HIGH" else (0.65 if u_conf == "MEDIUM" else None)),
                            ml_provenance=unit_prov,
                            ownership_records=[OwnershipRead.model_validate(o) for o in ownerships]
                        )
                    )

                dt_floors.append(
                    DigitalTwinFloor(
                        id=str(fl.id),
                        building_id=str(fl.building_id),
                        level_number=fl.level_number,
                        level_code=fl.level_code,
                        level_type=fl.level_type,
                        z_min=fl.z_min,
                        z_max=fl.z_max,
                        floor_height_m=fl.floor_height_m,
                        unit_count=len(dt_units),
                        units=dt_units
                    )
                )

            b_meta = b.spatial_metadata or {}
            b_conf = b_meta.get("confidence")
            dt_buildings.append(
                DigitalTwinBuilding(
                    id=str(b.id),
                    parcel_id=str(b.parcel_id),
                    building_name=b.building_name,
                    building_code=b.building_code,
                    structure_type=b.structure_type,
                    ground_elevation_m=b.ground_elevation_m,
                    total_height_m=b.total_height_m,
                    top_elevation_m=round(b.ground_elevation_m + b.total_height_m, 2),
                    footprint_area_sqm=bld_footprint_area,
                    volume_cu_m=bld_volume,
                    footprint_geojson=b.footprint_geojson,
                    confidence=b_conf if isinstance(b_conf, (int, float)) else 0.85,
                    ml_provenance={
                        "height_source": b_meta.get("height_source", "OBSERVED_SURVEY_METADATA"),
                        "height_method": b_meta.get("height_method", "EXPLICIT_METADATA"),
                        "floor_source": b_meta.get("floor_source", "DETERMINISTIC_BASELINE"),
                        "floor_method": b_meta.get("floor_method", "PARAMETRIC_STRATA_DECOMPOSITION"),
                        "confidence": b_meta.get("confidence"),
                        "uncertainty_m": b_meta.get("uncertainty_m"),
                        "requires_review": b_meta.get("requires_review", False),
                        "candidates": b_meta.get("candidates")
                    },
                    estimated_features=b_meta.get("estimated_features"),
                    floors=dt_floors
                )
            )

        overall_status = "VALID" if clashes_count == 0 else "HAS_CLASHES"

        # Check for cadastral anomalies using the existing deterministic detector
        from app.ml.models.anomaly_detector import CadastralMLAnomalyDetector
        max_height = max([b.total_height_m for b in dt_buildings], default=0.0)
        detector = CadastralMLAnomalyDetector()
        detected_anomalies = detector.predict({
            "total_height_m": max_height if max_height > 0 else None,
            "floor_count": total_floors_count if total_floors_count > 0 else None,
            "footprint_geojson": parcel.geometry_geojson
        })
        anomalies_list = [a.model_dump() for a in detected_anomalies]

        summary = DigitalTwinSummary(
            total_buildings=len(dt_buildings),
            total_floors=total_floors_count,
            total_units=total_units_count,
            total_volume_cu_m=round(total_volume_cu_m, 2),
            total_carpet_area_sqm=round(total_carpet_area_sqm, 2),
            vertical_breakdown=vertical_breakdown,
            clashes_detected=clashes_count,
            overall_status=overall_status,
            anomalies_detected=anomalies_list
        )

        dt_parcel = DigitalTwinParcel(
            id=str(parcel.id),
            ulpin=parcel.ulpin,
            state_code=parcel.state_code,
            district_code=parcel.district_code,
            village_code=parcel.village_code,
            survey_number=parcel.survey_number,
            area_sqm=parcel.area_sqm,
            centroid=[parcel.centroid_lon, parcel.centroid_lat],
            base_elevation_m=parcel.base_elevation_m,
            geometry_geojson=parcel.geometry_geojson,
            buildings=dt_buildings
        )

        return CadastralDigitalTwin(
            parcel=dt_parcel,
            summary=summary
        )
