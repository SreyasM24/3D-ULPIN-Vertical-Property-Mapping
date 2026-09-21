# SIH 26011: Live Demonstration Runbook

## 1. Quick Start / One-Command Verification

To execute the authoritative 5-scenario demonstration directly through the end-to-end Python pipeline:

```bash
# From repository root
python scripts/sih_final_demonstration.py
```

### Expected Output Summary:
```text
================================================================================
SIH 26011: 3D ULPIN & VERTICAL PROPERTY MAPPING
AUTHORITATIVE 5-SCENARIO JUDGE DEMONSTRATION
================================================================================

SCENARIO 1: INDIAN PUNE PARCEL (REAL 2D FOOTPRINT + REJECTED OUT-OF-COVERAGE LIDAR)
Execution Time: ~1.23s
Status: COMPLETED (100%)
LiDAR Coverage Evaluation: OUT_OF_COVERAGE (Bypassed out-of-bounds artifact)
Vertical Units Created: 16 (8 floors x 2 units)
Boundary Validation: PASS (0 violations)

SCENARIO 2: PALAKKAD CORRIDOR (REAL OBSERVED LIDAR POINT CLOUD)
Execution Time: ~1.17s
Status: COMPLETED (100%)
Ground Elevation (Class 2): 102.50m | Roof Surface (Z95): 120.71m
Derived Building Height: 18.21m (Derived Uncertainty: +/-1.57m)
AI Regressor Status: NOT_USED_OBSERVED_EVIDENCE (Authoritative bypass)
Vertical Units: 14 stratified units with sub-millimeter volume conservation

SCENARIO 3: MULTI-SOURCE EVIDENCE CONFLICT (SURVEY 30m vs LIDAR 18.21m)
Execution Time: ~1.20s
Evidence Conflict Detected: True (Severity: HIGH)
Review Required Flag: True
Discrepancy: 11.79m (Statistical 2-sigma Tolerance: 3.15m)
Cadastral Truth Policy: DOCUMENTED_PRIORITY_WITH_REVIEW_FLAG (No silent consensus)

SCENARIO 4: AI FALLBACK (NO OBSERVED SENSOR DATA)
Execution Time: ~0.56s
AI Status: ADVISORY_ESTIMATE (Confidence: High)
Vertical Units: 8 units generated with advisory flag in provenance

SCENARIO 5: SPACE-NET 1 ONNX UNET BUILDING EXTRACTION
Execution Time: ~0.92s
Detector Status: ACTIVE (Backend: ONNX_RUNTIME)
Weights SHA256: 6840feac1ff15945540b839401877ba1eee0460e0b4f80b7d501eaa299c85d1f
Test IoU: 0.5001

Total Pipeline Benchmark: ~5.08s across all 5 scenarios.
ALL 5 AUTHORITATIVE SCENARIOS VERIFIED SUCCESSFULLY WITH ZERO FABRICATION.
```

---

## 2. Running the Full Test & Verification Suite

### 2.1 Backend Regression Suite (Pytest)
```bash
python -m pytest -q
```
**Expected Result**: `187 passed in ~38s`.

### 2.2 Adversarial Geospatial Suite
```bash
python -m pytest tests/test_adversarial_geospatial.py -q
```
**Expected Result**: `26 passed in ~2.2s` (Covers edge cases A through Z).

### 2.3 Frontend Cadastral Flow Tests
```bash
cd frontend
npx tsx src/lib/cadastralFlow.test.ts
```
**Expected Result**: `12/12 passed in ~0.5s`.

### 2.4 Frontend TypeScript & Production Build
```bash
cd frontend
npx tsc --noEmit
npm run build
```
**Expected Result**: `0 errors`, production bundle generated cleanly.

---

## 3. Starting the Full Interactive Web Application

### Step 1: Start the FastAPI Backend
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Documentation: `http://localhost:8000/docs`
- Health Probe: `http://localhost:8000/health`
- ML Capabilities: `http://localhost:8000/api/v1/ml/capabilities`

### Step 2: Start the React Frontend
```bash
cd frontend
npm run dev
```
- Web Application URL: `http://localhost:5173`

---

## 4. SIH Judge Live UI Walkthrough Script

### Flow A: Statutory Indian Parcel (Pune, Maharashtra)
1. Open `http://localhost:5173`.
2. In the Parcel Form, select **"Demo Pune Parcel (DEMO-26011-001)"**.
3. Observe real Pune coordinate centroid ($18.5204^\circ\text{N}, 73.8567^\circ\text{E}$, EPSG:4326).
4. Select input evidence: `sample_elevation_raster.tif` (or leave default).
5. Click **"Process 3D ULPIN Parcel"**.
6. Note the async stage progression indicator.
7. Result: 3D interactive viewer extrudes the building with 16 stratified units across 8 floors, ISO-checksummed 3D ULPINs, and 0 topological overlap violations.

### Flow B: Evidence Conflict & Provenance Inspection
1. Select a parcel and upload contradictory total station survey vs point cloud returns.
2. In the **3D Viewer**, select any vertical unit.
3. Open the **Provenance & Audit Panel** on the right.
4. Highlight the **Conflict Detection Banner** (`HIGH` severity, `review_required = True`).
5. Highlight the **Multi-Source Evidence Evaluation Card**, demonstrating that both sources are preserved with calculated uncertainty ($\pm 0.1\text{m}$ and $\pm 1.57\text{m}$) and that the system refused to average them.
