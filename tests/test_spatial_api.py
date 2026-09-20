from fastapi.testclient import TestClient
from tests.test_units_api import setup_cadastral_stack


def test_spatial_endpoints(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson,
    sample_unit_geojson
):
    bld_id, f1_id, f2_id = setup_cadastral_stack(client, sample_parcel_geojson, sample_building_geojson)

    # Register one unit on Floor 1
    u1_res = client.post("/api/v1/units/", json={
        "floor_id": f1_id,
        "unit_number": "Flat 101",
        "unit_code": "U101",
        "z_min": 560.0,
        "z_max": 563.0,
        "footprint_geojson": sample_unit_geojson
    })
    assert u1_res.status_code == 201
    ulpin_3d = u1_res.json()["data"]["ulpin_3d"]

    # 1. Test 3D Clash Check API
    clash_res = client.get(f"/api/v1/spatial/clashes/building/{bld_id}")
    assert clash_res.status_code == 200
    clash_data = clash_res.json()["data"]
    assert clash_data["total_units_checked"] == 1
    assert clash_data["has_clashes"] is False
    assert clash_data["clash_count"] == 0

    # 2. Test 3D GeoJSON FeatureCollection Export API
    geojson_res = client.get(f"/api/v1/spatial/geojson3d/building/{bld_id}")
    assert geojson_res.status_code == 200
    geojson_data = geojson_res.json()["data"]
    assert geojson_data["type"] == "FeatureCollection"
    assert len(geojson_data["features"]) == 1
    feat = geojson_data["features"][0]
    assert feat["type"] == "Feature"
    assert feat["properties"]["ulpin_3d"] == ulpin_3d
    assert feat["properties"]["volume_cu_m"] > 0

    # 3. Test 3D ULPIN Validation API
    val_res = client.post("/api/v1/spatial/validate-ulpin-3d", json={"ulpin_3d": ulpin_3d})
    assert val_res.status_code == 200
    val_data = val_res.json()["data"]
    assert val_data["valid"] is True
    assert val_data["unit_code"] == "U101"
