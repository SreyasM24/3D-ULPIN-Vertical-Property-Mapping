# SIH 26011: 3D ULPIN & Vertical Property Mapping System
## End-to-End Demonstration & Evaluation Workflow

> [!IMPORTANT]
> **DISCLAIMER: SYNTHETIC DEMO BENCHMARK**
> All geographic coordinates, parcel boundaries, survey numbers, building models, and ownership records utilized in this walkthrough are **synthetic demonstration benchmarks** created specifically for prototype evaluation and Smart India Hackathon (SIH 26011) judging. They do not represent real government land records or certified legal titles.

---

## 1. System Overview

The **3D ULPIN & Vertical Property Mapping System** extends India's 2D Bhu-Aadhaar cadastre into a volumetric, multi-dimensional cadastral framework.

### Core Capabilities Demonstrated
1. **2D Bhu-Aadhaar Base**: Ingests WGS84 GeoJSON polygons, projects into optimal UTM coordinate reference systems (CRS), computes geodesic areas, and derives deterministic 2D ULPINs.
2. **Volumetric Strata & 3D ULPIN**: Constructs physical structures, underground basements, ground levels, and upper strata with 3D prism volumes and deterministic 3D ULPIN identifiers.
3. **Multi-Floor & Common Area Support**: Accurately tracks standard units, multi-floor duplexes spanning multiple strata, and shared common spaces.
4. **Deterministic Cadastral Validation Engine**: Audits 100+ OGC topological and vertical rules, distinguishes private clash conflicts from shared easements, and scores cadastral data quality (Grades A to D).
5. **ML/AI-Assisted Remote Sensing Extraction**: Proposes building footprints, height estimates, and vertical floor counts without asserting legal authority.
6. **Asynchronous Processing Orchestrator**: Non-blocking survey ingestion with traceable stage progression, idempotency, and transactional rollback on failure.
7. **3D Digital Twin**: Generates unified volumetric summaries and 3D GeoJSON ready for Cesium, Three.js, and web GIS viewers.

---

## 2. Environment Setup & Launch

### Prerequisites
- Python 3.10+ (Verified on Python 3.13)
- SQLite3 (Included by default; compatible with PostgreSQL/PostGIS)

### Quick Start Commands
```powershell
# 1. Activate your virtual environment
.\venv\Scripts\activate   # Or conda activate <env>

# 2. Install dependencies (if not already installed)
pip install -r requirements.txt

# 3. Run the automated test suite (verifies 91 tests pass)
pytest -q

# 4. Generate the synthetic benchmark dataset
python scripts/generate_demo_dataset.py

# 5. Launch the backend API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI Swagger UI is available at: `http://localhost:8000/docs`

---

## 3. Step-by-Step Demonstration Script

### Step 1: Verify System Liveness & Readiness Probes
Confirm the backend service and database connectivity:

```bash
# Root Liveness Probe
curl -X GET http://localhost:8000/health

# Root Readiness Probe
curl -X GET http://localhost:8000/readiness

# System Capabilities Probe
curl -X GET http://localhost:8000/api/v1/capabilities
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "status": "ready",
    "database_connected": true,
    "app_name": "3D ULPIN & Vertical Property Mapping System",
    "version": "0.1.0"
  },
  "error": null
}
```

---

### Step 2: Trigger End-to-End Asynchronous Ingestion & Cadastral Processing
Submit a new raw parcel survey boundary for automatic ML feature extraction, strata derivation, 3D ULPIN allocation, validation, and digital twin generation:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/process-parcel \
  -H "Content-Type: application/json" \
  -d '{
    "state_code": "MH",
    "district_code": "PUN",
    "village_code": "54321",
    "survey_number": "SN-DEMO-2026-X1",
    "parcel_geojson": {
      "type": "Polygon",
      "coordinates": [[[73.856, 18.52], [73.857, 18.52], [73.857, 18.521], [73.856, 18.521], [73.856, 18.52]]]
    },
    "total_height_m": 18.0,
    "ground_elevation_m": 560.0,
    "floor_count": 4,
    "basement_count": 1,
    "units_per_floor": 2,
    "auto_generate_strata": true
  }'
```

**Immediate 202 Accepted Response**:
```json
{
  "success": true,
  "data": {
    "job_id": "c1f79b04-a12b-4ec9-9238-7dfd3198a002",
    "job_type": "END_TO_END_PARCEL_PROCESS",
    "status": "QUEUED",
    "current_stage": "QUEUED",
    "progress_percent": 0.0,
    "created_at": "2026-09-19T14:30:00Z"
  }
}
```

---

### Step 3: Monitor Asynchronous Job Progression
Poll the job endpoint every 1–2 seconds to observe lifecycle transitions:
`QUEUED` → `INSPECTION` → `PREPROCESSING` → `FEATURE_EXTRACTION` → `CADASTRAL_CONSTRUCTION` → `ULPIN_GENERATION` → `VALIDATION` → `DIGITAL_TWIN_UPDATE` → `COMPLETED`

```bash
curl -X GET http://localhost:8000/api/v1/jobs/c1f79b04-a12b-4ec9-9238-7dfd3198a002
```

**Completed State Payload**:
```json
{
  "success": true,
  "data": {
    "job_id": "c1f79b04-a12b-4ec9-9238-7dfd3198a002",
    "status": "COMPLETED",
    "current_stage": "COMPLETED",
    "progress_percent": 100.0,
    "result_reference": {
      "parcel_id": "...",
      "parcel_ulpin": "B34C81ADC86A6J",
      "building_code": "BLD-C1F79B",
      "floors_count": 5,
      "units_count": 10,
      "unit_ulpins": [
        "B34C81ADC86A6J-B1-UB101-9D",
        "B34C81ADC86A6J-G-UG01-CG",
        "..."
      ],
      "quality_score": 92.0,
      "quality_grade": "HIGH_CONFIDENCE",
      "is_valid": true,
      "ml_confidence": 0.95
    }
  }
}
```

---

### Step 4: Inspect 3D Vertical Property Units & Volumetric Bounds
Retrieve the generated 3D property units on a building:

```bash
curl -X GET "http://localhost:8000/api/v1/units/?building_id=<BUILDING_ID>"
```

Key attributes to inspect:
- `ulpin_3d`: Format `<2D-ULPIN>-<LEVEL_CODE>-<UNIT_CODE>-<CHECKSUM>`
- `volume_cu_m`: Metric volume in cubic meters ($m^3$) computed via projected prism bounds.
- `carpet_area_sqm`: Internal footprint area in square meters ($m^2$).
- `z_min` and `z_max`: Precise altitude range above Mean Sea Level (MSL).
- `is_multi_floor`: Flag indicating vertical units spanning multiple levels (e.g. duplexes).

---

### Step 5: Inspect Deterministic Cadastral Validation & Quality Score
Execute an audit on the parcel hierarchy:

```bash
curl -X GET "http://localhost:8000/api/v1/validation/parcel/<PARCEL_ID>"
```

**Quality Score Breakdown & Explanations**:
- **Geometry Validity (25/25)**: Polygon ring closure, no self-intersections, no slivers.
- **CRS & Projection (15/15)**: WGS84 range validation, optimal UTM zone projection.
- **Hierarchy Containment (20/20)**: Parcel contains Building; Floor conforms to Building; Units conform to Floor.
- **Vertical Strata Consistency (15/15)**: Monotonic elevation ordering ($B1 < G < F1 < F2$), height ceiling matching.
- **3D Clash Freedom (15/15)**: Zero unauthorized volumetric overlap between private units.
- **Provenance Completeness (10/10)**: Timestamps, survey numbers, 3D ULPIN derivation.
- **Overall Grade**: `HIGH_CONFIDENCE` (Grade A: 90–100 pts).

---

### Step 6: Retrieve Complete 3D Digital Twin
Retrieve the assembled 3D digital twin with GeoJSON 3D features:

```bash
curl -X GET "http://localhost:8000/api/v1/spatial/digital-twin/<PARCEL_ID>"
```

This returns:
- **Summary**: `total_units`, `total_volume_cu_m`, `total_carpet_area_sqm`.
- **Bounding Box**: 3D spatial extents `[min_lon, min_lat, min_z, max_lon, max_lat, max_z]`.
- **Features**: Complete 3D GeoJSON feature collection consumable by CesiumJS, MapLibre GL, deck.gl, or Three.js.
