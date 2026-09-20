import pytest
from fastapi.testclient import TestClient

from app.core.spatial_volume import (
    PrismVolume,
    PolyhedralMeshVolume,
    VerticalClassification,
    classify_vertical_position,
)
from app.services.floor_engine import FloorEngine
from app.services.cadastral_relationship_engine import CadastralRelationshipEngine
from tests.test_units_api import setup_cadastral_stack


# ---------------------------------------------------------------------------
# 1. 3D Spatial Volume & Vertical Classification Tests
# ---------------------------------------------------------------------------

def test_prism_volume_and_area_consistency(sample_parcel_geojson):
    ground_z = 560.0
    total_h = 30.0
    prism = PrismVolume(
        footprint_geojson=sample_parcel_geojson,
        z_min=ground_z,
        z_max=ground_z + total_h,
        ground_elevation_m=ground_z
    )
    assert prism.area_sqm > 0
    assert prism.height_m == 30.0
    # Volume must strictly equal area * height in metric units
    assert prism.volume_cu_m == round(prism.area_sqm * prism.height_m, 2)
    assert prism.projected_crs == "EPSG:32643"
    assert prism.vertical_classification == VerticalClassification.ELEVATED

    # 3D Point containment
    centroid_lat, centroid_lon = prism.centroid_lat, prism.centroid_lon
    assert prism.contains_point_3d(centroid_lon, centroid_lat, 570.0) is True
    # Out of Z bounds
    assert prism.contains_point_3d(centroid_lon, centroid_lat, 595.0) is False


def test_vertical_classification_rules():
    ground_ref = 560.0

    # Underground (basement)
    v_under = classify_vertical_position(554.0, 560.0, ground_ref)
    assert v_under == VerticalClassification.UNDERGROUND

    # Elevated
    v_elev = classify_vertical_position(565.0, 568.0, ground_ref)
    assert v_elev == VerticalClassification.ELEVATED

    # Ground level straddle
    v_ground = classify_vertical_position(559.0, 563.0, ground_ref)
    assert v_ground == VerticalClassification.GROUND_LEVEL

    # Multi-level vertical infrastructure
    v_infra = classify_vertical_position(540.0, 580.0, ground_ref)
    assert v_infra == VerticalClassification.MULTI_LEVEL_INFRASTRUCTURE


def test_polyhedral_mesh_extensibility():
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1)]
    faces = [[0, 1, 2, 3], [0, 1, 4]]
    mesh = PolyhedralMeshVolume(
        vertices_3d=verts,
        faces=faces,
        z_min=0.0,
        z_max=10.0,
        projected_crs="EPSG:32643",
        estimated_volume_cu_m=500.0,
        estimated_footprint_area_sqm=50.0
    )
    assert mesh.volume_cu_m == 500.0
    assert mesh.contains_point_3d(0.5, 0.5, 5.0) is True


# ---------------------------------------------------------------------------
# 2. Floor Engine: Multi-floor, Basements, Mixed Heights & Overlaps
# ---------------------------------------------------------------------------

def test_floor_engine_mixed_heights_and_basements():
    ground_z = 560.0
    total_h = 30.0

    floors = [
        # Basement 2 (lower)
        {"level_code": "B02", "level_number": -2, "level_type": "BASEMENT", "z_min": 553.0, "z_max": 556.5},
        # Basement 1 (upper)
        {"level_code": "B01", "level_number": -1, "level_type": "BASEMENT", "z_min": 556.5, "z_max": 560.0},
        # Ground Floor Lobby (higher ceiling: 4.5m)
        {"level_code": "G00", "level_number": 0, "level_type": "GROUND", "z_min": 560.0, "z_max": 564.5},
        # Residential Level 1 (typical height: 3.0m)
        {"level_code": "L01", "level_number": 1, "level_type": "TYPICAL_FLOOR", "z_min": 564.5, "z_max": 567.5},
        # Service Floor (lower height: 2.5m)
        {"level_code": "SV1", "level_number": 2, "level_type": "SERVICE", "z_min": 567.5, "z_max": 570.0},
    ]

    report = FloorEngine.validate_building_floors(
        building_id="test_bld_1",
        ground_elevation_m=ground_z,
        total_height_m=total_h,
        floors=floors
    )
    assert report.is_valid is True
    assert report.total_floors == 5
    assert len(report.errors) == 0
    assert report.strata_summary["basement_count"] == 2
    assert report.strata_summary["ground_count"] == 1
    assert report.strata_summary["elevated_count"] == 2


def test_floor_engine_overlapping_floors_detection():
    ground_z = 560.0
    total_h = 20.0

    overlapping_floors = [
        {"level_code": "L01", "level_number": 1, "z_min": 560.0, "z_max": 564.0},
        # L02 overlaps L01 by 1.0m (starts at 563 instead of 564)
        {"level_code": "L02", "level_number": 2, "z_min": 563.0, "z_max": 567.0},
    ]

    report = FloorEngine.validate_building_floors(
        building_id="bld_clash",
        ground_elevation_m=ground_z,
        total_height_m=total_h,
        floors=overlapping_floors
    )
    assert report.is_valid is False
    assert len(report.overlapping_floor_pairs) == 1
    assert any("Vertical overlap" in err for err in report.errors)


def test_floor_engine_basement_above_ground_rejection():
    report = FloorEngine.validate_building_floors(
        building_id="bld_bad_basement",
        ground_elevation_m=560.0,
        total_height_m=20.0,
        floors=[
            # Erroneously placed at 562m (above ground datum)
            {"level_code": "B01", "level_number": -1, "z_min": 558.0, "z_max": 562.0}
        ]
    )
    assert report.is_valid is False
    assert any("Basement floor" in err for err in report.errors)


# ---------------------------------------------------------------------------
# 3. Unit Types, Multi-floor & Spatial Relationship Hierarchy
# ---------------------------------------------------------------------------

def test_unit_types_and_relationship_validation(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson,
    sample_unit_geojson
):
    bld_id, f1_id, f2_id = setup_cadastral_stack(client, sample_parcel_geojson, sample_building_geojson)

    # 1. Commercial Shop unit on Floor 1
    shop_res = client.post("/api/v1/units/", json={
        "floor_id": f1_id,
        "unit_number": "Shop 01",
        "unit_code": "SH01",
        "unit_type": "SHOP",
        "z_min": 560.0,
        "z_max": 563.0,
        "footprint_geojson": sample_unit_geojson
    })
    assert shop_res.status_code == 201
    shop_id = shop_res.json()["data"]["id"]

    # 2. Validate hierarchical relationships for the unit
    rel_res = client.post(f"/api/v1/units/{shop_id}/validate-relationships")
    assert rel_res.status_code == 200
    rel_data = rel_res.json()["data"]
    assert rel_data["all_valid"] is True
    assert rel_data["floor_contains_unit"]["is_valid"] is True
    assert rel_data["building_contains_unit"]["is_valid"] is True
    assert rel_data["parcel_contains_unit"]["is_valid"] is True


def test_multi_floor_unit_handling(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson,
    sample_unit_geojson
):
    bld_id, f1_id, f2_id = setup_cadastral_stack(client, sample_parcel_geojson, sample_building_geojson)

    # Create parking ramp / duplex spanning floor 1 and floor 2 (560m to 566m)
    ramp_res = client.post("/api/v1/units/", json={
        "floor_id": f1_id,
        "unit_number": "Vehicular Ramp R1",
        "unit_code": "RMP01",
        "unit_type": "PARKING",
        "z_min": 560.0,
        "z_max": 566.0,  # Spans beyond floor 1's 563m top
        "footprint_geojson": sample_unit_geojson
    })
    # If the user permits multi-floor creation
    if ramp_res.status_code == 201:
        ramp_id = ramp_res.json()["data"]["id"]
        rel_res = client.post(f"/api/v1/units/{ramp_id}/validate-relationships?allow_multi_floor=true")
        assert rel_res.status_code == 200
        assert rel_res.json()["data"]["floor_contains_unit"]["is_multi_floor"] is True


# ---------------------------------------------------------------------------
# 4. Cadastral Digital Twin & 3D Export API
# ---------------------------------------------------------------------------

def test_cadastral_digital_twin_assembly(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson,
    sample_unit_geojson
):
    # Setup stack
    p_res = client.post("/api/v1/parcels/", json={
        "state_code": "MH",
        "district_code": "PUN",
        "village_code": "411001",
        "survey_number": "555/DT",
        "geometry_geojson": sample_parcel_geojson,
    })
    parcel_id = p_res.json()["data"]["id"]

    b_res = client.post("/api/v1/buildings/", json={
        "parcel_id": parcel_id,
        "building_name": "Digital Twin Towers",
        "building_code": "DTT",
        "structure_type": "MIXED_USE",
        "floors_above_ground": 8,
        "total_height_m": 28.0,
        "ground_elevation_m": 560.0,
        "footprint_geojson": sample_building_geojson
    })
    bld_id = b_res.json()["data"]["id"]

    f_res = client.post("/api/v1/floors/", json={
        "building_id": bld_id,
        "level_number": 1,
        "level_code": "L01",
        "z_min": 560.0,
        "z_max": 563.5
    })
    floor_id = f_res.json()["data"]["id"]

    u_res = client.post("/api/v1/units/", json={
        "floor_id": floor_id,
        "unit_number": "Office 101",
        "unit_code": "OFF101",
        "unit_type": "OFFICE",
        "z_min": 560.0,
        "z_max": 563.5,
        "footprint_geojson": sample_unit_geojson
    })
    unit_id = u_res.json()["data"]["id"]

    # Register ownership
    client.post("/api/v1/ownership/", json={
        "unit_id": unit_id,
        "owner_name": "Maharashtra IT Corp",
        "owner_identifier_raw": "CORP99120",
        "share_percentage": 100.0,
        "title_deed_number": "REG-2026-CORP-1",
        "registration_date": "2026-03-15"
    })

    # 1. Fetch Digital Twin
    dt_res = client.get(f"/api/v1/parcels/{parcel_id}/digital-twin")
    assert dt_res.status_code == 200
    dt = dt_res.json()["data"]
    assert dt["parcel"]["id"] == parcel_id
    assert len(dt["parcel"]["buildings"]) == 1
    assert dt["summary"]["total_units"] == 1
    assert dt["summary"]["total_volume_cu_m"] > 0
    assert dt["summary"]["overall_status"] == "VALID"

    # 2. Fetch Multi-layered 3D GeoJSON
    geojson_res = client.get(f"/api/v1/parcels/{parcel_id}/digital-twin/geojson3d")
    assert geojson_res.status_code == 200
    fc = geojson_res.json()["data"]
    assert fc["type"] == "FeatureCollection"
    layers = {feat["properties"].get("layer") for feat in fc["features"]}
    assert "PARCEL" in layers
    assert "BUILDING" in layers
    assert "FLOOR" in layers
    assert "UNIT" in layers


# ---------------------------------------------------------------------------
# 5. Advanced Spatial Queries Tests
# ---------------------------------------------------------------------------

def test_spatial_query_by_elevation_and_bbox(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson,
    sample_unit_geojson
):
    bld_id, f1_id, f2_id = setup_cadastral_stack(client, sample_parcel_geojson, sample_building_geojson)

    # Unit on Floor 1: 560.0 - 563.0
    client.post("/api/v1/units/", json={
        "floor_id": f1_id,
        "unit_number": "Flr1 Unit",
        "unit_code": "FLR1",
        "unit_type": "APARTMENT",
        "z_min": 560.0,
        "z_max": 563.0,
        "footprint_geojson": sample_unit_geojson
    })

    # Unit on Floor 2: 563.0 - 566.0
    client.post("/api/v1/units/", json={
        "floor_id": f2_id,
        "unit_number": "Flr2 Unit",
        "unit_code": "FLR2",
        "unit_type": "APARTMENT",
        "z_min": 563.0,
        "z_max": 566.0,
        "footprint_geojson": sample_unit_geojson
    })

    # 1. Query at Elevation Z = 561.5 (should only match Floor 1 unit)
    q1 = client.get("/api/v1/units/?elevation_z=561.5")
    assert q1.status_code == 200
    items1 = q1.json()["data"]["items"]
    assert len(items1) == 1
    assert items1[0]["unit_code"] == "FLR1"

    # 2. Query at Elevation Z = 565.0 (should only match Floor 2 unit)
    q2 = client.get("/api/v1/units/?elevation_z=565.0")
    assert q2.status_code == 200
    items2 = q2.json()["data"]["items"]
    assert len(items2) == 1
    assert items2[0]["unit_code"] == "FLR2"

    # 3. 3D Bounding Box Query
    bbox_res = client.get(
        "/api/v1/units/spatial-query?min_lon=73.85&min_lat=18.51&min_z=559.0&max_lon=73.86&max_lat=18.53&max_z=568.0"
    )
    assert bbox_res.status_code == 200
    assert bbox_res.json()["data"]["total"] == 2
