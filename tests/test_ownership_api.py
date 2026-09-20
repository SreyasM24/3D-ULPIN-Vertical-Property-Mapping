from fastapi.testclient import TestClient
from tests.test_units_api import setup_cadastral_stack


def test_ownership_registration_and_share_limits(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson,
    sample_unit_geojson
):
    bld_id, f1_id, _ = setup_cadastral_stack(client, sample_parcel_geojson, sample_building_geojson)

    # Create Unit
    u_res = client.post("/api/v1/units/", json={
        "floor_id": f1_id,
        "unit_number": "Flat 101",
        "unit_code": "U101",
        "z_min": 560.0,
        "z_max": 563.0,
        "footprint_geojson": sample_unit_geojson
    })
    unit_id = u_res.json()["data"]["id"]

    # 1. Register 60% Joint Owner 1
    own1_payload = {
        "unit_id": unit_id,
        "owner_name": "Aarav Sharma",
        "owner_identifier_raw": "542389104512",  # Aadhaar / PAN
        "share_percentage": 60.0,
        "ownership_type": "JOINT",
        "title_deed_number": "REG-2026-MH-9912",
        "registration_date": "2026-03-20"
    }
    own1_res = client.post("/api/v1/ownership/", json=own1_payload)
    assert own1_res.status_code == 201
    own1_data = own1_res.json()["data"]
    assert own1_data["owner_name"] == "Aarav Sharma"
    # Ensure raw ID is NOT stored or returned directly
    assert own1_data["owner_identifier_hash"] != "542389104512"
    assert len(own1_data["owner_identifier_hash"]) == 64  # SHA-256

    # 2. Try registering 50% Owner 2 (Total would be 110% -> must fail)
    own2_excess_payload = {
        "unit_id": unit_id,
        "owner_name": "Pooja Sharma",
        "owner_identifier_raw": "987654321012",
        "share_percentage": 50.0,
        "ownership_type": "JOINT",
        "title_deed_number": "REG-2026-MH-9912",
        "registration_date": "2026-03-20"
    }
    excess_res = client.post("/api/v1/ownership/", json=own2_excess_payload)
    assert excess_res.status_code == 400
    assert "exceeds 100%" in excess_res.json()["error"]["message"]

    # 3. Register valid 40% Owner 2 (Total = 100% -> must succeed)
    own2_valid_payload = {
        "unit_id": unit_id,
        "owner_name": "Pooja Sharma",
        "owner_identifier_raw": "987654321012",
        "share_percentage": 40.0,
        "ownership_type": "JOINT",
        "title_deed_number": "REG-2026-MH-9912",
        "registration_date": "2026-03-20"
    }
    own2_res = client.post("/api/v1/ownership/", json=own2_valid_payload)
    assert own2_res.status_code == 201

    # 4. List records for the unit
    list_res = client.get(f"/api/v1/ownership/?unit_id={unit_id}")
    assert list_res.status_code == 200
    assert list_res.json()["data"]["total"] == 2
