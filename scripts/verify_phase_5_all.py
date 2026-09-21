"""
SIH 26011 — Complete Phase 5 All-Scenario Verification Script.
Executes:
1. Scenario A: Valid LiDAR (DEMO-LIDAR-43N)
2. Scenario B: Out-of-Coverage LiDAR (Pune DEMO-26011-001)
3. Scenario C: AI Fallback (No survey/LiDAR)
4. Scenario D: Evidence Conflict (30m Survey vs 18.21m LiDAR)
5. Scenario E: Dynamic Cadastral Input (Config 1 vs Config 2 dynamic parameter variations)
"""

import sys
import time
import json
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

results = {}

# -------------------------------------------------------------
# SCENARIO A: VALID LiDAR (Palakkad DEMO-LIDAR-43N)
# -------------------------------------------------------------
print("=" * 70)
print("SCENARIO A: VALID LiDAR (DEMO-LIDAR-43N + sample_pointcloud.las)")
print("=" * 70)
r_a = client.post("/api/v1/jobs/process-parcel", json={
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
})
assert r_a.status_code == 202, f"Expected 202, got {r_a.status_code}: {r_a.text}"
dt_a = client.get(f"/api/v1/parcels/{p_lidar.id}/digital-twin").json()["data"]
u_a = dt_a["parcel"]["buildings"][0]["floors"][0]["units"][0]
prov_a = u_a["ml_provenance"]
assert prov_a["selected_evidence"] == "POINT_CLOUD", f"Expected POINT_CLOUD, got {prov_a['selected_evidence']}"
assert prov_a["coverage"] == "VALID", f"Expected VALID, got {prov_a['coverage']}"
assert prov_a["ai_model"] == "NOT_USED_OBSERVED_EVIDENCE", f"Expected AI bypassed, got {prov_a['ai_model']}"
assert prov_a["observed_height_m"] == 18.21, f"Expected 18.21m, got {prov_a['observed_height_m']}"
assert prov_a["uncertainty_m"] == 1.57, f"Expected 1.57m, got {prov_a['uncertainty_m']}"
print(f"PASS Scenario A: Height={prov_a['observed_height_m']}m, Uncertainty=+/-{prov_a['uncertainty_m']}m, Coverage={prov_a['coverage']}, AI={prov_a['ai_model']}")
results["scenario_a"] = "PASS"

# -------------------------------------------------------------
# SCENARIO B: OUT-OF-COVERAGE LiDAR (Pune DEMO-26011-001)
# -------------------------------------------------------------
print("\n" + "=" * 70)
print("SCENARIO B: OUT-OF-COVERAGE LiDAR (Pune DEMO-26011-001 + sample_pointcloud.las)")
print("=" * 70)
r_b = client.post("/api/v1/jobs/process-parcel", json={
    "parcel_id": str(p_pune.id),
    "total_height_m": 18.0,
    "ground_elevation_m": 560.0,
    "floor_count": 5,
    "units_per_floor": 2,
    "auto_generate_strata": True,
    "source_evidence": {
        "source_type": "POINT_CLOUD",
        "source_reference": "sample_pointcloud.las"
    }
})
assert r_b.status_code == 202
dt_b = client.get(f"/api/v1/parcels/{p_pune.id}/digital-twin").json()["data"]
u_b = dt_b["parcel"]["buildings"][0]["floors"][0]["units"][0]
prov_b = u_b["ml_provenance"]
candidates_b = prov_b.get("multi_source_evidence", [])
pc_cand = next((c for c in candidates_b if c["source_type"] == "POINT_CLOUD"), None)
ai_cand = next((c for c in candidates_b if c["source_type"] == "AI_REGRESSION"), None)

assert pc_cand is not None, "POINT_CLOUD candidate missing"
assert pc_cand["coverage"] == "REJECTED_OUT_OF_BOUNDS", f"Expected REJECTED_OUT_OF_BOUNDS, got {pc_cand['coverage']}"
assert pc_cand.get("height_m") is None, f"Expected None height, got {pc_cand.get('height_m')}"
assert ai_cand is not None, "AI_REGRESSION candidate missing"
assert ai_cand.get("height_m") != 18.0, f"AI must NOT inherit 18.0m survey! Got {ai_cand.get('height_m')}"
assert prov_b["selected_evidence"] == "EXPLICIT_SURVEY_METADATA", f"Expected EXPLICIT_SURVEY_METADATA, got {prov_b['selected_evidence']}"
print(f"PASS Scenario B: LiDAR Rejected={pc_cand['coverage']}, Fallback={prov_b['selected_evidence']}, AI Candidate Height={ai_cand.get('height_m')}m (unc: +/-{ai_cand.get('uncertainty_m')}m)")
results["scenario_b"] = "PASS"

# -------------------------------------------------------------
# SCENARIO C: AI FALLBACK (No survey, no LiDAR, no DSM)
# -------------------------------------------------------------
print("\n" + "=" * 70)
print("SCENARIO C: AI FALLBACK (No physical sensor data)")
print("=" * 70)
r_c = client.post("/api/v1/jobs/process-parcel", json={
    "parcel_id": str(p_pune.id),
    "floor_count": 4,
    "units_per_floor": 2,
    "auto_generate_strata": True,
    # No total_height_m, no LiDAR, no DSM
})
assert r_c.status_code == 202
dt_c = client.get(f"/api/v1/parcels/{p_pune.id}/digital-twin").json()["data"]
u_c = dt_c["parcel"]["buildings"][0]["floors"][0]["units"][0]
prov_c = u_c["ml_provenance"]
assert prov_c["selected_evidence"] == "AI_REGRESSION", f"Expected AI_REGRESSION, got {prov_c['selected_evidence']}"
assert prov_c["ai_status"] == "ADVISORY_ESTIMATE", f"Expected ADVISORY_ESTIMATE, got {prov_c['ai_status']}"
assert prov_c["uncertainty_m"] == 2.323 or prov_c["uncertainty_m"] == 2.32, f"Expected 2.32m unc, got {prov_c['uncertainty_m']}"
print(f"PASS Scenario C: Selected={prov_c['selected_evidence']}, Status={prov_c['ai_status']}, Model={prov_c['ai_model']}, Uncertainty=+/-{prov_c['uncertainty_m']}m")
results["scenario_c"] = "PASS"

# -------------------------------------------------------------
# SCENARIO D: EVIDENCE CONFLICT (Survey 30m vs LiDAR 18.21m)
# -------------------------------------------------------------
print("\n" + "=" * 70)
print("SCENARIO D: EVIDENCE CONFLICT (30.0m Survey vs 18.21m LiDAR)")
print("=" * 70)
r_d = client.post("/api/v1/jobs/process-parcel", json={
    "parcel_id": str(p_lidar.id),
    "total_height_m": 30.0,
    "floor_count": 8,
    "units_per_floor": 2,
    "auto_generate_strata": True,
    "source_evidence": {
        "source_type": "POINT_CLOUD",
        "source_reference": "sample_pointcloud.las"
    }
})
assert r_d.status_code == 202
dt_d = client.get(f"/api/v1/parcels/{p_lidar.id}/digital-twin").json()["data"]
u_d = dt_d["parcel"]["buildings"][0]["floors"][0]["units"][0]
prov_d = u_d["ml_provenance"]
conflict_d = prov_d.get("conflict_details", {})
assert prov_d["conflict_detected"] is True, "Conflict must be detected"
assert prov_d["conflict_severity"] == "HIGH", f"Expected HIGH severity, got {prov_d['conflict_severity']}"
assert prov_d["requires_review"] is True, "requires_review must be True"
assert conflict_d["value_a_m"] == 30.0, f"Expected 30.0m, got {conflict_d['value_a_m']}"
assert conflict_d["value_b_m"] == 18.21, f"Expected 18.21m, got {conflict_d['value_b_m']}"
assert conflict_d["difference_m"] == 11.79, f"Expected 11.79m delta, got {conflict_d['difference_m']}"
print(f"PASS Scenario D: Conflict={prov_d['conflict_detected']}, Delta={conflict_d['difference_m']}m, ReviewRequired={prov_d['requires_review']}, Policy={conflict_d.get('cadastral_policy_applied')}")
results["scenario_d"] = "PASS"

# -------------------------------------------------------------
# SCENARIO E: DYNAMIC CADASTRAL INPUT (Variation Tests)
# -------------------------------------------------------------
print("\n" + "=" * 70)
print("SCENARIO E: DYNAMIC CADASTRAL INPUT VARIATIONS")
print("=" * 70)

# Configuration 1: Low-rise, 3 above-ground floors, 0 basements, 1 unit/floor (Total: 3 floors, 3 units)
r_e1 = client.post("/api/v1/jobs/process-parcel", json={
    "parcel_id": str(p_pune.id),
    "total_height_m": 9.8,
    "ground_elevation_m": 560.0,
    "floor_count": 3,
    "basement_count": 0,
    "units_per_floor": 1,
    "auto_generate_strata": True,
})
assert r_e1.status_code == 202
dt_e1 = client.get(f"/api/v1/parcels/{p_pune.id}/digital-twin").json()["data"]
summary_e1 = dt_e1["summary"]
floors_e1 = dt_e1["parcel"]["buildings"][0]["floors"]
units_e1 = [u for f in floors_e1 for u in f["units"]]

print(f"Config 1 (3 floors, 0 basements, 1 unit/fl): Floors={len(floors_e1)}, Units={len(units_e1)}, Volume={summary_e1['total_volume_cu_m']}m3")
assert len(floors_e1) == 3, f"Expected 3 floors, got {len(floors_e1)}"
assert len(units_e1) == 3, f"Expected 3 units, got {len(units_e1)}"

# Configuration 2: Mid-rise, 6 above-ground floors, 2 basements, 3 units/floor (Total: 8 floors, 24 units)
r_e2 = client.post("/api/v1/jobs/process-parcel", json={
    "parcel_id": str(p_pune.id),
    "total_height_m": 24.8,
    "ground_elevation_m": 560.0,
    "floor_count": 6,
    "basement_count": 2,
    "units_per_floor": 3,
    "auto_generate_strata": True,
})
assert r_e2.status_code == 202
dt_e2 = client.get(f"/api/v1/parcels/{p_pune.id}/digital-twin").json()["data"]
summary_e2 = dt_e2["summary"]
floors_e2 = dt_e2["parcel"]["buildings"][0]["floors"]
units_e2 = [u for f in floors_e2 for u in f["units"]]

print(f"Config 2 (6 floors, 2 basements, 3 units/fl): Floors={len(floors_e2)}, Units={len(units_e2)}, Volume={summary_e2['total_volume_cu_m']}m3")
assert len(floors_e2) == 8, f"Expected 8 floors, got {len(floors_e2)}"
assert len(units_e2) == 24, f"Expected 24 units, got {len(units_e2)}"

# Verify Dynamic Scaling (Strictly Non-Hardcoded)
assert len(units_e2) != len(units_e1), "Unit counts must vary dynamically with input"
assert len(floors_e2) != len(floors_e1), "Floor counts must vary dynamically with input"
assert summary_e2["total_volume_cu_m"] > summary_e1["total_volume_cu_m"], "Volume must scale with height & floors"

# Verify distinct ULPINs for every single unit
ulpins_e2 = set(u["ulpin_3d"] for u in units_e2)
assert len(ulpins_e2) == 24, f"Expected 24 unique 3D ULPINs, got {len(ulpins_e2)}"

print(f"PASS Scenario E: Proven 100% dynamic scaling (3 units/3 floors -> 24 units/8 floors) with 24 distinct 3D ULPINs.")
results["scenario_e"] = "PASS"

print("\n" + "=" * 70)
print("ALL 5 SCENARIOS (A, B, C, D, E) PASSED WITH ZERO FABRICATION!")
print("=" * 70)
