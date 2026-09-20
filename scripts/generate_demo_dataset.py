"""
Synthetic Demo Dataset Generator for SIH 26011:
3D ULPIN & Vertical Property Mapping System.

DISCLAIMER:
SYNTHETIC DEMO DATA - NOT REAL GOVERNMENT DATA.
All geometries, coordinates, survey numbers, and ownership records generated
by this script are purely artificial benchmarks designed for prototype testing,
hackathon demonstrations, and frontend integration.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import SessionLocal, init_db
from app.models.parcel import LandParcel
from app.models.building import Building
from app.models.floor import FloorLevel
from app.models.unit import VerticalUnit
from app.models.ownership import OwnershipRecord
from app.schemas.parcel import ParcelCreate, GeoJSONPolygon
from app.schemas.building import BuildingCreate
from app.schemas.floor import FloorCreate
from app.schemas.unit import UnitCreate
from app.services.cadastre_service import CadastreService
from app.services.cadastral_validator import CadastralValidationService
from app.services.digital_twin_service import DigitalTwinService
from app.core.logging import logger


DEMO_PARCEL_GEOJSON = {
    "type": "Polygon",
    "coordinates": [
        [
            [73.85600, 18.52000],
            [73.85700, 18.52000],
            [73.85700, 18.52100],
            [73.85600, 18.52100],
            [73.85600, 18.52000]
        ]
    ]
}

DEMO_BUILDING_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [
        [
            [73.85620, 18.52020],
            [73.85680, 18.52020],
            [73.85680, 18.52080],
            [73.85620, 18.52080],
            [73.85620, 18.52020]
        ]
    ]
}

# Subdivided footprints for units (West wing and East wing)
UNIT_WEST_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [
        [
            [73.85620, 18.52020],
            [73.85650, 18.52020],
            [73.85650, 18.52080],
            [73.85620, 18.52080],
            [73.85620, 18.52020]
        ]
    ]
}

UNIT_EAST_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [
        [
            [73.85650, 18.52020],
            [73.85680, 18.52020],
            [73.85680, 18.52080],
            [73.85650, 18.52080],
            [73.85650, 18.52020]
        ]
    ]
}


def generate_demo_dataset():
    """Generates an end-to-end 3D cadastral hierarchy for demo and evaluation."""
    print("=" * 70)
    print("  SIH 26011: 3D ULPIN & VERTICAL PROPERTY MAPPING DEMO DATASET GENERATOR")
    print("  NOTICE: SYNTHETIC DEMO DATA - NOT REAL GOVERNMENT DATA")
    print("=" * 70)

    init_db()
    db = SessionLocal()

    try:
        # 1. Clean existing demo records if any
        existing_parcel = db.query(LandParcel).filter(LandParcel.survey_number == "DEMO-26011-001").first()
        if existing_parcel:
            print(f"[*] Removing existing demo parcel {existing_parcel.ulpin}...")
            db.delete(existing_parcel)
            db.commit()

        # 2. Create 2D Land Parcel
        print("[1/6] Registering 2D Land Parcel (Bhu-Aadhaar base)...")
        p_in = ParcelCreate(
            state_code="MH",
            district_code="PUN",
            village_code="54321",
            survey_number="DEMO-26011-001",
            subdivision_number="1A",
            base_elevation_m=560.0,
            geometry_geojson=GeoJSONPolygon(**DEMO_PARCEL_GEOJSON),
            spatial_metadata={"source": "SYNTHETIC DEMO SURVEY", "dataset_type": "SYNTHETIC_BENCHMARK"}
        )
        parcel = CadastreService.create_parcel(db, p_in)
        print(f"      Parcel Created: ID={parcel.id}")
        print(f"      2D ULPIN:       {parcel.ulpin}")
        print(f"      Geodetic Area:  {parcel.area_sqm:.2f} m2")

        # 3. Create 3D Building
        print("\n[2/6] Constructing 3D Building Structure...")
        b_in = BuildingCreate(
            parcel_id=parcel.id,
            building_name="Pragati Heights (Demo Benchmark)",
            building_code="BLD-DEMO-01",
            structure_type="MIXED_USE",
            floors_above_ground=4,
            basement_floors=1,
            total_height_m=18.0,
            ground_elevation_m=560.0,
            footprint_geojson=GeoJSONPolygon(**DEMO_BUILDING_FOOTPRINT)
        )
        building = CadastreService.create_building(db, b_in)
        print(f"      Building Created: ID={building.id}, Code={building.building_code}")
        print(f"      Elevation: Base={building.ground_elevation_m}m, Height={building.total_height_m}m")

        # 4. Create Floor Levels (Basement B1, Ground G, Upper F1, F2, F3)
        print("\n[3/6] Defining Vertical Strata Floor Levels...")
        floor_configs = [
            {"num": -1, "code": "B1", "type": "BASEMENT", "z_min": 556.5, "z_max": 560.0},
            {"num": 0,  "code": "G",  "type": "GROUND",   "z_min": 560.0, "z_max": 563.5},
            {"num": 1,  "code": "F1", "type": "TYPICAL",  "z_min": 563.5, "z_max": 567.0},
            {"num": 2,  "code": "F2", "type": "TYPICAL",  "z_min": 567.0, "z_max": 570.5},
            {"num": 3,  "code": "F3", "type": "TYPICAL",  "z_min": 570.5, "z_max": 574.0},
        ]
        floors = {}
        for fc in floor_configs:
            fl_in = FloorCreate(
                building_id=building.id,
                level_number=fc["num"],
                level_code=fc["code"],
                level_type=fc["type"],
                z_min=fc["z_min"],
                z_max=fc["z_max"],
                footprint_geojson=GeoJSONPolygon(**DEMO_BUILDING_FOOTPRINT)
            )
            fl_orm = CadastreService.create_floor(db, fl_in)
            floors[fc["code"]] = fl_orm
            print(f"      Floor {fl_orm.level_code:2s}: z=[{fl_orm.z_min:.1f}m -> {fl_orm.z_max:.1f}m] (ID={fl_orm.id})")

        # 5. Create Vertical Units (Standard, Multi-Floor Duplex, and Shared Common Area)
        print("\n[4/6] Instantiating 3D Property Units with 3D ULPINs...")
        units_spec = [
            # Basement: Parking / Service
            {"floor": "B1", "num": "B1-01", "type": "PARKING", "geom": DEMO_BUILDING_FOOTPRINT, "z_min": 556.5, "z_max": 560.0, "multi": False},
            # Ground: Commercial Retail West & East
            {"floor": "G",  "num": "G-01",  "type": "COMMERCIAL", "geom": UNIT_WEST_FOOTPRINT, "z_min": 560.0, "z_max": 563.5, "multi": False},
            {"floor": "G",  "num": "G-02",  "type": "COMMERCIAL", "geom": UNIT_EAST_FOOTPRINT, "z_min": 560.0, "z_max": 563.5, "multi": False},
            # Floor 1: Residential West & Common Lobby/Service East
            {"floor": "F1", "num": "F1-101", "type": "APARTMENT", "geom": UNIT_WEST_FOOTPRINT, "z_min": 563.5, "z_max": 567.0, "multi": False},
            {"floor": "F1", "num": "F1-COMM", "type": "COMMON_AREA", "geom": UNIT_EAST_FOOTPRINT, "z_min": 563.5, "z_max": 567.0, "multi": False},
            # Floor 2 & 3: Multi-Floor Penthouse/Duplex (West wing spanning F2+F3) and Regular Unit East on F2
            {"floor": "F2", "num": "F2-202", "type": "APARTMENT", "geom": UNIT_EAST_FOOTPRINT, "z_min": 567.0, "z_max": 570.5, "multi": False},
            {"floor": "F2", "num": "DUPLEX-01", "type": "APARTMENT", "geom": UNIT_WEST_FOOTPRINT, "z_min": 567.0, "z_max": 574.0, "multi": True},
            # Floor 3: East Terrace Unit
            {"floor": "F3", "num": "F3-302", "type": "TERRACE", "geom": UNIT_EAST_FOOTPRINT, "z_min": 570.5, "z_max": 574.0, "multi": False},
        ]

        created_units = []
        for us in units_spec:
            fl_obj = floors[us["floor"]]
            u_in = UnitCreate(
                floor_id=fl_obj.id,
                unit_number=us["num"],
                unit_code=f"U-{us['num']}",
                unit_type=us["type"],
                z_min=us["z_min"],
                z_max=us["z_max"],
                is_multi_floor=us["multi"],
                floor_span=[floors["F2"].id, floors["F3"].id] if us["multi"] else None,
                footprint_geojson=GeoJSONPolygon(**us["geom"])
            )
            unit_orm = CadastreService.create_unit(db, u_in, enforce_clash_free=True)
            created_units.append(unit_orm)
            print(f"      Unit {unit_orm.unit_number:10s} [{unit_orm.unit_type:11s}]: 3D ULPIN = {unit_orm.ulpin_3d} | Vol = {unit_orm.volume_cu_m:.1f} m3")

        # 6. Run Deterministic Cadastral Validation Engine
        print("\n[5/6] Executing Deterministic Cadastral Validation Audit...")
        v_report = CadastralValidationService.validate_parcel_hierarchy(db=db, parcel_id=parcel.id, persist=True)
        q_score = v_report.quality_score.total_score if hasattr(v_report.quality_score, "total_score") else float(v_report.quality_score)
        q_grade = v_report.quality_score.grade.value if hasattr(v_report.quality_score, "grade") else "HIGH_CONFIDENCE"
        print(f"      Validation Status: {'PASS' if v_report.is_valid else 'FAIL'}")
        print(f"      Cadastral Quality: {q_score:.1f}/100.0 (Grade {q_grade})")
        print(f"      Total Checks:     {v_report.total_rules_executed} rules evaluated ({v_report.total_rules_passed} passed, {v_report.total_rules_failed} failed)")
        print(f"      Issues Found:     {len(v_report.issues)} issues")
        for iss in v_report.issues:
            print(f"        - [{iss.severity.value}] {iss.rule_id}: {iss.explanation}")

        # 7. Assemble 3D Digital Twin
        print("\n[6/6] Assembling 3D Volumetric Digital Twin...")
        dt = DigitalTwinService.assemble_digital_twin(db=db, parcel_id=parcel.id)
        print(f"      Digital Twin Total Units:    {dt.summary.total_units}")
        print(f"      Total Volumetric Space:      {dt.summary.total_volume_cu_m:.2f} m3")
        print(f"      Total Carpet Area:           {dt.summary.total_carpet_area_sqm:.2f} m2")

        # 8. Export JSON dump for frontend testing
        export_file = PROJECT_ROOT / "docs" / "demo_dataset_export.json"
        export_file.parent.mkdir(parents=True, exist_ok=True)
        export_payload = {
            "disclaimer": "SYNTHETIC DEMO DATA - NOT REAL GOVERNMENT DATA",
            "parcel": {
                "id": parcel.id,
                "ulpin_2d": parcel.ulpin,
                "state_code": parcel.state_code,
                "district_code": parcel.district_code,
                "survey_number": parcel.survey_number,
                "area_sqm": parcel.area_sqm,
                "centroid": [parcel.centroid_lon, parcel.centroid_lat]
            },
            "building": {
                "id": building.id,
                "building_code": building.building_code,
                "building_name": building.building_name,
                "height_m": building.total_height_m,
                "ground_elevation_m": building.ground_elevation_m,
                "floors_count": len(floors),
                "units_count": len(created_units)
            },
            "floors": [
                {"code": f.level_code, "z_min": f.z_min, "z_max": f.z_max, "level_number": f.level_number}
                for f in floors.values()
            ],
            "units": [
                {
                    "unit_number": u.unit_number,
                    "ulpin_3d": u.ulpin_3d,
                    "unit_type": u.unit_type,
                    "z_min": u.z_min,
                    "z_max": u.z_max,
                    "volume_cu_m": u.volume_cu_m,
                    "is_multi_floor": u.is_multi_floor
                }
                for u in created_units
            ],
            "validation": {
                "run_id": v_report.validation_run_id,
                "is_valid": v_report.is_valid,
                "quality_score": q_score,
                "quality_grade": q_grade
            },
            "digital_twin_summary": {
                "total_units": dt.summary.total_units,
                "total_volume_cu_m": dt.summary.total_volume_cu_m,
                "total_carpet_area_sqm": dt.summary.total_carpet_area_sqm
            }
        }
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2)

        print(f"\n[+] Demo dataset exported to: {export_file}")
        print("=" * 70)
        print("  DEMO DATASET GENERATION COMPLETED SUCCESSFULLY")
        print("=" * 70)
        return export_payload

    finally:
        db.close()


if __name__ == "__main__":
    generate_demo_dataset()
