"""
SIH 26011 — Final Sensor Input Consistency Test Matrix
Tests all 9 user-facing source options end-to-end through FastAPI:
1. DRONE_PHOTOGRAMMETRY
2. POINT_CLOUD
3. DSM_DTM
4. CAD_FLOOR_PLAN
5. BUILDING_METADATA
6. EXPLICIT_FLOOR_COUNT
7. OBSERVED_HEIGHT_DECOMPOSITION
8. AI_HEIGHT_DECOMPOSITION
9. DETERMINISTIC_BASELINE
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.models.parcel import LandParcel

client = TestClient(app)
db = SessionLocal()

p_lidar = db.query(LandParcel).filter(LandParcel.survey_number == "DEMO-LIDAR-43N").first()
p_pune = db.query(LandParcel).filter(LandParcel.survey_number == "DEMO-26011-001").first()

assert p_lidar is not None, "DEMO-LIDAR-43N parcel not found"
assert p_pune is not None, "DEMO-26011-001 parcel not found"

print("=" * 80)
print("SIH 26011 — 9 SENSOR SOURCE OPTIONS END-TO-END VERIFICATION MATRIX")
print("=" * 80)

test_cases = [
    {
        "num": 1,
        "source_type": "DRONE_PHOTOGRAMMETRY",
        "reference": "demo_26011_drone_survey.geojson",
        "parcel": p_pune,
        "payload_extra": {
            "total_height_m": 15.0,
            "floor_count": 4,
            "ground_elevation_m": 560.0
        },
        "expected_source": "DRONE_PHOTOGRAMMETRY",
        "expected_ref": "demo_26011_drone_survey.geojson"
    },
    {
        "num": 2,
        "source_type": "POINT_CLOUD",
        "reference": "sample_pointcloud.las",
        "parcel": p_lidar,
        "payload_extra": {
            "units_per_floor": 2,
            "auto_generate_strata": True
        },
        "expected_source": "POINT_CLOUD",
        "expected_ref": "sample_pointcloud.las"
    },
    {
        "num": 3,
        "source_type": "DSM_DTM",
        "reference": "usgs_3dep_dem_patch_512x512.tif",
        "parcel": p_pune,
        "payload_extra": {
            "floor_count": 3
        },
        "expected_not_ref_substr": ".las",
        "description": "Bare-earth DEM raster classified as terrain-only; falls back cleanly without .las leakage"
    },
    {
        "num": 4,
        "source_type": "CAD_FLOOR_PLAN",
        "reference": "architectural_floor_plan_rev2.dxf",
        "parcel": p_pune,
        "payload_extra": {
            "total_height_m": 16.5,
            "floor_count": 4
        },
        "expected_source": "CAD_FLOOR_PLAN",
        "expected_ref": "architectural_floor_plan_rev2.dxf"
    },
    {
        "num": 5,
        "source_type": "BUILDING_METADATA",
        "reference": "registered_cadastral_survey",
        "parcel": p_pune,
        "payload_extra": {
            "total_height_m": 21.0,
            "floor_count": 6
        },
        "expected_source": "BUILDING_METADATA",
        "expected_ref": "registered_cadastral_survey"
    },
    {
        "num": 6,
        "source_type": "EXPLICIT_FLOOR_COUNT",
        "reference": "surveyor_storey_declaration.record",
        "parcel": p_pune,
        "payload_extra": {
            "floor_count": 5
        },
        "expected_source": "EXPLICIT_FLOOR_COUNT",
        "expected_ref": "surveyor_storey_declaration.record"
    },
    {
        "num": 7,
        "source_type": "OBSERVED_HEIGHT_DECOMPOSITION",
        "reference": "total_station_height_telemetry.obs",
        "parcel": p_pune,
        "payload_extra": {
            "total_height_m": 12.8,
            "floor_count": 3
        },
        "expected_source": "OBSERVED_HEIGHT_DECOMPOSITION",
        "expected_ref": "total_station_height_telemetry.obs"
    },
    {
        "num": 8,
        "source_type": "AI_HEIGHT_DECOMPOSITION",
        "reference": "models/height_estimator.onnx",
        "parcel": p_pune,
        "payload_extra": {},
        "expected_source": "AI_REGRESSION",
        "expected_ref": "models/height_estimator.onnx"
    },
    {
        "num": 9,
        "source_type": "DETERMINISTIC_BASELINE",
        "reference": "cadastral_parametric_rules",
        "parcel": p_pune,
        "payload_extra": {
            "floor_count": 3
        },
        "expected_source_in": ["DETERMINISTIC_BASELINE", "DETERMINISTIC_CASCADE"],
        "expected_ref": "cadastral_parametric_rules"
    }
]

pass_count = 0
for tc in test_cases:
    num = tc["num"]
    st = tc["source_type"]
    ref = tc["reference"]
    parcel = tc["parcel"]
    extra = tc["payload_extra"]

    payload = {
        "parcel_id": str(parcel.id),
        "survey_number": parcel.survey_number,
        "state_code": 27 if str(parcel.state_code) == "MH" else (int(parcel.state_code) if str(parcel.state_code).isdigit() else 27),
        "district_code": str(parcel.district_code),
        "village_code": str(parcel.village_code),
        "source_evidence": {
            "source_type": st,
            "source_reference": ref
        },
        **extra
    }

    r = client.post("/api/v1/jobs/process-parcel", json=payload)
    assert r.status_code == 202, f"TC{num} failed with status {r.status_code}: {r.text}"

    # Fetch Digital Twin
    dt = client.get(f"/api/v1/parcels/{parcel.id}/digital-twin").json()["data"]
    units = dt["parcel"]["buildings"][0]["floors"][0]["units"]
    assert len(units) > 0, f"TC{num} produced 0 units"
    prov = units[0]["ml_provenance"]

    # Verify no .las leakage when not POINT_CLOUD
    if st != "POINT_CLOUD":
        assert not str(prov.get("source_reference", "")).endswith((".las", ".laz")), (
            f"TC{num} leaked .las into non-LiDAR reference: {prov.get('source_reference')}"
        )

    if "expected_source" in tc:
        assert prov["selected_evidence"] == tc["expected_source"], (
            f"TC{num} expected {tc['expected_source']}, got {prov['selected_evidence']}"
        )
    if "expected_source_in" in tc:
        assert prov["selected_evidence"] in tc["expected_source_in"], (
            f"TC{num} expected one of {tc['expected_source_in']}, got {prov['selected_evidence']}"
        )
    if "expected_ref" in tc:
        assert prov["source_reference"] == tc["expected_ref"], (
            f"TC{num} expected ref {tc['expected_ref']}, got {prov['source_reference']}"
        )

    print(f"PASS TC {num}/9: Source={st:<30} -> Provenance={prov['selected_evidence']:<25} Ref={prov['source_reference']}")
    pass_count += 1

print("=" * 80)
print(f"ALL {pass_count}/9 SENSOR SOURCE OPTIONS PASSED VERIFICATION.")
print("=" * 80)
