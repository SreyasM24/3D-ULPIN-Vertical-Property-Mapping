from fastapi.testclient import TestClient


def test_create_and_read_parcel(client: TestClient, sample_parcel_geojson):
    payload = {
        "state_code": "MH",
        "district_code": "PUN",
        "village_code": "411001",
        "survey_number": "204/1A",
        "base_elevation_m": 560.0,
        "geometry_geojson": sample_parcel_geojson,
        "spatial_metadata": {"source": "DRONE_SURVEY", "crs": "EPSG:4326"}
    }
    response = client.post("/api/v1/parcels/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    parcel = data["data"]
    assert parcel["survey_number"] == "204/1A"
    assert len(parcel["ulpin"]) == 14
    assert parcel["area_sqm"] > 0
    assert parcel["centroid_lat"] > 0

    parcel_id = parcel["id"]
    ulpin = parcel["ulpin"]

    # Read by ID
    get_res = client.get(f"/api/v1/parcels/{parcel_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == parcel_id

    # Read by ULPIN
    ulpin_res = client.get(f"/api/v1/parcels/ulpin/{ulpin}")
    assert ulpin_res.status_code == 200
    assert ulpin_res.json()["data"]["ulpin"] == ulpin

    # List
    list_res = client.get("/api/v1/parcels/?page=1&page_size=10")
    assert list_res.status_code == 200
    assert list_res.json()["data"]["total"] >= 1

    # Update
    update_res = client.put(f"/api/v1/parcels/{parcel_id}", json={"survey_number": "204/1A-REV"})
    assert update_res.status_code == 200
    assert update_res.json()["data"]["survey_number"] == "204/1A-REV"

    # Test Digital Twin endpoint returns summary with anomalies_detected
    dt_res = client.get(f"/api/v1/parcels/{parcel_id}/digital-twin")
    assert dt_res.status_code == 200
    dt_data = dt_res.json()["data"]
    assert "summary" in dt_data
    assert "anomalies_detected" in dt_data["summary"]
    assert isinstance(dt_data["summary"]["anomalies_detected"], list)

    # Delete
    del_res = client.delete(f"/api/v1/parcels/{parcel_id}")
    assert del_res.status_code == 200
    assert del_res.json()["data"]["deleted"] is True

    # Confirm deleted
    not_found_res = client.get(f"/api/v1/parcels/{parcel_id}")
    assert not_found_res.status_code == 404


def test_create_parcel_invalid_polygon(client: TestClient):
    payload = {
        "state_code": "MH",
        "district_code": "PUN",
        "village_code": "411001",
        "survey_number": "205",
        "geometry_geojson": {
            "type": "Polygon",
            "coordinates": [[[73.0, 18.0], [73.1, 18.0]]]  # less than 4 points
        }
    }
    response = client.post("/api/v1/parcels/", json=payload)
    assert response.status_code == 422
    assert response.json()["success"] is False
