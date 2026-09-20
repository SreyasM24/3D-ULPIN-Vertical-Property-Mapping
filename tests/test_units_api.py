from fastapi.testclient import TestClient


def setup_cadastral_stack(client: TestClient, sample_parcel_geojson, sample_building_geojson):
    # Parcel
    p_res = client.post("/api/v1/parcels/", json={
        "state_code": "MH",
        "district_code": "PUN",
        "village_code": "411001",
        "survey_number": "100/1",
        "geometry_geojson": sample_parcel_geojson,
    })
    parcel_id = p_res.json()["data"]["id"]

    # Building
    b_res = client.post("/api/v1/buildings/", json={
        "parcel_id": parcel_id,
        "building_name": "Royal Residency",
        "building_code": "ROYAL-R",
        "structure_type": "RESIDENTIAL",
        "floors_above_ground": 10,
        "total_height_m": 35.0,
        "footprint_geojson": sample_building_geojson
    })
    building_id = b_res.json()["data"]["id"]

    # Floor 1 (560m to 563m)
    f1_res = client.post("/api/v1/floors/", json={
        "building_id": building_id,
        "level_number": 1,
        "level_code": "L01",
        "z_min": 560.0,
        "z_max": 563.0
    })
    floor1_id = f1_res.json()["data"]["id"]

    # Floor 2 (563m to 566m)
    f2_res = client.post("/api/v1/floors/", json={
        "building_id": building_id,
        "level_number": 2,
        "level_code": "L02",
        "z_min": 563.0,
        "z_max": 566.0
    })
    floor2_id = f2_res.json()["data"]["id"]

    return building_id, floor1_id, floor2_id


def test_vertical_unit_creation_and_clash_prevention(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson,
    sample_unit_geojson
):
    bld_id, f1_id, f2_id = setup_cadastral_stack(client, sample_parcel_geojson, sample_building_geojson)

    # 1. Create Unit 101 on Floor 1
    u101_res = client.post("/api/v1/units/", json={
        "floor_id": f1_id,
        "unit_number": "Flat 101",
        "unit_code": "U101",
        "unit_type": "APARTMENT",
        "z_min": 560.0,
        "z_max": 563.0,
        "footprint_geojson": sample_unit_geojson
    })
    assert u101_res.status_code == 201
    u101 = u101_res.json()["data"]
    assert u101["carpet_area_sqm"] > 0
    assert u101["volume_cu_m"] > 0
    assert "L01-U101" in u101["ulpin_3d"]
    assert u101["is_clash_free"] is True

    # 2. Try creating colliding unit on same floor with overlapping geometry
    clash_res = client.post("/api/v1/units/", json={
        "floor_id": f1_id,
        "unit_number": "Flat 101-DUPLICATE",
        "unit_code": "U101B",
        "unit_type": "APARTMENT",
        "z_min": 560.0,
        "z_max": 563.0,
        "footprint_geojson": sample_unit_geojson
    })
    assert clash_res.status_code == 422
    assert clash_res.json()["error"]["code"] == "SPATIAL_CLASH_DETECTED"

    # 3. Create Unit 201 on Floor 2 (stacked vertically directly above 101) -> MUST SUCCEED
    u201_res = client.post("/api/v1/units/", json={
        "floor_id": f2_id,
        "unit_number": "Flat 201",
        "unit_code": "U201",
        "unit_type": "APARTMENT",
        "z_min": 563.0,
        "z_max": 566.0,
        "footprint_geojson": sample_unit_geojson
    })
    assert u201_res.status_code == 201
    u201 = u201_res.json()["data"]
    assert "L02-U201" in u201["ulpin_3d"]

    # 4. Read unit by 3D ULPIN
    ulpin_res = client.get(f"/api/v1/units/ulpin/{u101['ulpin_3d']}")
    assert ulpin_res.status_code == 200
    assert ulpin_res.json()["data"]["id"] == u101["id"]
