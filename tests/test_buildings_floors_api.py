from fastapi.testclient import TestClient


def create_test_parcel(client: TestClient, sample_parcel_geojson) -> str:
    res = client.post("/api/v1/parcels/", json={
        "state_code": "MH",
        "district_code": "PUN",
        "village_code": "411001",
        "survey_number": "50/1",
        "geometry_geojson": sample_parcel_geojson,
    })
    return res.json()["data"]["id"]


def test_building_and_floor_lifecycle(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson
):
    parcel_id = create_test_parcel(client, sample_parcel_geojson)

    # 1. Create Building
    bld_payload = {
        "parcel_id": parcel_id,
        "building_name": "Galaxy Heights Tower A",
        "building_code": "GLX-A",
        "structure_type": "RESIDENTIAL",
        "floors_above_ground": 14,
        "basement_floors": 2,
        "total_height_m": 48.0,
        "ground_elevation_m": 560.0,
        "footprint_geojson": sample_building_geojson
    }
    bld_res = client.post("/api/v1/buildings/", json=bld_payload)
    assert bld_res.status_code == 201
    bld_data = bld_res.json()["data"]
    bld_id = bld_data["id"]
    assert bld_data["building_code"] == "GLX-A"

    # 2. Create Floor Levels
    floor_payload = {
        "building_id": bld_id,
        "level_number": 1,
        "level_code": "L01",
        "level_type": "TYPICAL_FLOOR",
        "z_min": 563.0,
        "z_max": 566.0
    }
    floor_res = client.post("/api/v1/floors/", json=floor_payload)
    assert floor_res.status_code == 201
    floor_data = floor_res.json()["data"]
    floor_id = floor_data["id"]
    assert floor_data["floor_height_m"] == 3.0
    assert floor_data["level_code"] == "L01"

    # 3. List Floors
    list_res = client.get(f"/api/v1/floors/?building_id={bld_id}")
    assert list_res.status_code == 200
    assert list_res.json()["data"]["total"] == 1


def test_building_containment_violation(client: TestClient, sample_parcel_geojson):
    parcel_id = create_test_parcel(client, sample_parcel_geojson)

    # Footprint outside parcel boundary
    outside_footprint = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8600, 18.5300],
                [73.8610, 18.5300],
                [73.8610, 18.5310],
                [73.8600, 18.5310],
                [73.8600, 18.5300]
            ]
        ]
    }
    res = client.post("/api/v1/buildings/", json={
        "parcel_id": parcel_id,
        "building_name": "Illegal Out-of-bounds Tower",
        "building_code": "ILLEGAL-1",
        "total_height_m": 20.0,
        "footprint_geojson": outside_footprint
    })
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "SPATIAL_CONTAINMENT_VIOLATION"
