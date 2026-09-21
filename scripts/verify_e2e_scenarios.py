"""
Live E2E Verification Script for SIH 26011 Prompt 2/4
Runs all 3 real scenarios against FastAPI:
1. Real LAS E2E Job (Covering Footprint)
2. Out-of-Coverage Job (Pune Parcel + Out-of-bounds LAS)
3. Real DEM Raster Job (USGS 3DEP DEM)
"""

import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app
from app.models.parcel import LandParcel
from app.db.session import SessionLocal

client = TestClient(app)
db = SessionLocal()

p_lidar = db.query(LandParcel).filter(LandParcel.survey_number == "DEMO-LIDAR-43N").first()
p_pune = db.query(LandParcel).filter(LandParcel.survey_number == "DEMO-26011-001").first()

print(f"LIDAR Parcel ID: {p_lidar.id}, Pune Parcel ID: {p_pune.id}")

# -------------------------------------------------------------
# TEST 1: REAL LAS E2E (Covering Footprint)
# -------------------------------------------------------------
print("\n==================== 1. REAL LAS E2E TEST ====================")
t0 = time.perf_counter()
req_payload_1 = {
    "parcel_id": str(p_lidar.id),
    "survey_number": "DEMO-LIDAR-43N",
    "state_code": 32,
    "district_code": "PKD",
    "village_code": "678001",
    "units_per_floor": 2,
    "auto_generate_strata": True,
    "source_evidence": {
        "source_type": "POINT_CLOUD",
        "source_reference": "sample_pointcloud.las"
    }
}
r1 = client.post("/api/v1/jobs/process-parcel", json=req_payload_1)
job1_id = r1.json()["data"]["job_id"]
print("Job 1 ID:", job1_id)

for _ in range(30):
    jr = client.get(f"/api/v1/jobs/{job1_id}")
    j_status = jr.json()["data"]["status"]
    if j_status in ("COMPLETED", "FAILED"):
        break
    time.sleep(0.1)

t1 = time.perf_counter()
print(f"Job 1 Status: {j_status} in {t1 - t0:.3f}s")

def extract_units_from_dt(dt_dict):
    units = []
    bldgs = dt_dict.get("buildings") or dt_dict.get("parcel", {}).get("buildings", [])
    for b in bldgs:
        for f in b.get("floors", []):
            units.extend(f.get("units", []))
    return units

# Fetch Digital Twin
dt1_r = client.get(f"/api/v1/parcels/{p_lidar.id}/digital-twin")
dt1 = dt1_r.json()["data"]
print("Digital Twin Total Units:", dt1["summary"]["total_units"])
print("Digital Twin Total Volume:", dt1["summary"]["total_volume_cu_m"])
bldgs = dt1.get("buildings") or dt1.get("parcel", {}).get("buildings", [])
if bldgs:
    print("Digital Twin Building Height:", bldgs[0]["total_height_m"])
units1 = extract_units_from_dt(dt1)
if units1:
    sample_unit1 = units1[0]
    print("Sample Unit ULPIN:", sample_unit1["ulpin_3d"])
    print("Sample Unit Provenance:\n", json.dumps(sample_unit1.get("ml_provenance"), indent=2))

# -------------------------------------------------------------
# TEST 2: OUT-OF-COVERAGE TEST (Pune Demo Parcel + LAS)
# -------------------------------------------------------------
print("\n==================== 2. OUT-OF-COVERAGE TEST ====================")
t0 = time.perf_counter()
req_payload_2 = {
    "parcel_id": str(p_pune.id),
    "survey_number": "DEMO-26011-001",
    "state_code": 27,
    "district_code": "PUN",
    "village_code": "54321",
    "units_per_floor": 2,
    "auto_generate_strata": True,
    "source_evidence": {
        "source_type": "POINT_CLOUD",
        "source_reference": "sample_pointcloud.las"
    }
}
r2 = client.post("/api/v1/jobs/process-parcel", json=req_payload_2)
job2_id = r2.json()["data"]["job_id"]
print("Job 2 ID:", job2_id)

for _ in range(30):
    jr = client.get(f"/api/v1/jobs/{job2_id}")
    j_status = jr.json()["data"]["status"]
    if j_status in ("COMPLETED", "FAILED"):
        break
    time.sleep(0.1)

t1 = time.perf_counter()
print(f"Job 2 Status: {j_status} in {t1 - t0:.3f}s")

dt2_r = client.get(f"/api/v1/parcels/{p_pune.id}/digital-twin")
dt2 = dt2_r.json()["data"]
units2 = extract_units_from_dt(dt2)
if units2:
    sample_unit2 = units2[0]
    print("Sample Unit Provenance (Pune Out-of-Coverage):\n", json.dumps(sample_unit2.get("ml_provenance"), indent=2))

# -------------------------------------------------------------
# TEST 3: REAL DEM RASTER TEST
# -------------------------------------------------------------
print("\n==================== 3. REAL DEM RASTER TEST ====================")
t0 = time.perf_counter()
req_payload_3 = {
    "parcel_id": str(p_pune.id),
    "survey_number": "DEMO-26011-001",
    "state_code": 27,
    "district_code": "PUN",
    "village_code": "54321",
    "units_per_floor": 2,
    "auto_generate_strata": True,
    "source_evidence": {
        "source_type": "DSM_DTM",
        "source_reference": "usgs_3dep_dem_patch_512x512.npy"
    }
}
r3 = client.post("/api/v1/jobs/process-parcel", json=req_payload_3)
job3_id = r3.json()["data"]["job_id"]
print("Job 3 ID:", job3_id)

for _ in range(30):
    jr = client.get(f"/api/v1/jobs/{job3_id}")
    j_status = jr.json()["data"]["status"]
    if j_status in ("COMPLETED", "FAILED"):
        break
    time.sleep(0.1)

t1 = time.perf_counter()
print(f"Job 3 Status: {j_status} in {t1 - t0:.3f}s")
dt3_r = client.get(f"/api/v1/parcels/{p_pune.id}/digital-twin")
dt3 = dt3_r.json()["data"]
units3 = extract_units_from_dt(dt3)
if units3:
    sample_unit3 = units3[0]
    print("Sample Unit Provenance (DEM Raster):\n", json.dumps(sample_unit3.get("ml_provenance"), indent=2))

# -------------------------------------------------------------
# 4. VALIDATION REPORTS FOR ALL RUNS
# -------------------------------------------------------------
print("\n==================== 4. VALIDATION REPORTS ====================")
val1_res = client.post(f"/api/v1/validation/parcel/{p_lidar.id}?persist=false").json()["data"]
qs1 = val1_res["quality_score"]["total_score"]
print(f"LiDAR Parcel Validation: Score={qs1:.1f}, Valid={val1_res['is_valid']}, Rules={val1_res['total_rules_executed']}")

val2_res = client.post(f"/api/v1/validation/parcel/{p_pune.id}?persist=false").json()["data"]
qs2 = val2_res["quality_score"]["total_score"]
print(f"Pune Parcel Validation: Score={qs2:.1f}, Valid={val2_res['is_valid']}, Rules={val2_res['total_rules_executed']}")
db.close()
