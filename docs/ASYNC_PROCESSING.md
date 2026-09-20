# Asynchronous Survey Ingestion & End-to-End Cadastral Processing Orchestration

## 1. Architectural Overview

The **Asynchronous Ingestion and Processing Orchestration Subsystem** enables large survey datasets, remote sensing models (LiDAR, DEM/DSM rasters, drone photogrammetry), and multi-story cadastral land parcels to enter the system without blocking HTTP request threads.

### Strict Non-Blocking Contract
Every resource-intensive ingestion and processing operation returns immediately with **HTTP 202 Accepted** along with a unique `job_id`, initial state (`QUEUED`), and an explicit `tracking_url` (`/api/v1/jobs/{job_id}`).

```
CLIENT (Web App / Mobile App / Survey Station)
        │
        ├─ POST /api/v1/jobs/ingestion or /process-parcel ─────────► [ API v1 Gateway ]
        │                                                                   │
        ◄─ HTTP 202 Accepted (job_id, status=QUEUED, tracking_url) ────────┤ (Immediate non-blocking return)
        │                                                                   │
        │                                                                   ▼
        │                                                           [ JobManager ] ──► Writes ProcessingJob (DB)
        │                                                                   │
        │                                                           [ JobExecutor ]
        │                                                                   │
        │                                                                   ▼
        │                                                   [ Background Worker Task ]
        │                                                                   │
        │                                                     [ Cadastral Processing Orchestrator ]
        │                                                                   │
        │  GET /api/v1/jobs/{job_id}                                        ├── 1. INSPECTION (15%)
        ├─────────────────────────────────────────────────────────────────► ├── 2. PREPROCESSING (30%)
        ◄─ HTTP 200 OK (status=RUNNING, progress=65%, events)               ├── 3. ML FEATURE EXTRACTION (45%)
        │                                                                   ├── 4. 3D CADASTRAL CONSTRUCTION (65%)
        │                                                                   ├── 5. 3D ULPIN GENERATION (75%)
        │                                                                   ├── 6. DETERMINISTIC VALIDATION (85%)
        │                                                                   ├── 7. DIGITAL TWIN REGISTRATION (95%)
        │                                                                   └── 8. COMPLETED (100%)
        │
        ├─ GET /api/v1/jobs/{job_id}/result ──────────────────────────────► [ Job Result Payload ]
        ◄─ HTTP 200 OK (Created ULPINs, Quality Score, Grade, Digital Twin)
```

---

## 2. Zero-Dependency Local Setup & Distributed Scaling Roadmap

### Default Zero-Dependency Engine
- **FastAPI `BackgroundTasks` + SQLite / PostgreSQL**: Out of the box, no Redis or Celery server is required to test or run the complete orchestration pipeline.
- **Transactional DB Session Isolation**: The `JobExecutor` dispatches tasks in a separate isolated database session (`SessionLocal()`), preventing database lockups, race conditions, or connection leaks across threads.

### Production Distributed Queue Ready
The orchestration subsystem is abstracted via `JobExecutor` and `ProcessingJob` database persistence:
- All job states, progression logs, error traces, and result references are persisted to the database via SQLAlchemy (`processing_jobs` table).
- Jobs survive backend process restarts and can be polled across multi-worker setups.
- Celery / Redis / AWS SQS / Google Cloud Tasks can be plugged into `JobExecutor.dispatch()` without modifying business logic, domain models, or REST API contracts.

---

## 3. Job State Machine & Stage Progression

### Top-Level Job Statuses (`JobStatus`)
1. `QUEUED`: Job registered and enqueued for worker execution.
2. `RUNNING`: Worker commenced execution and is advancing through processing stages.
3. `COMPLETED`: Processing completed successfully (progress = 100.0%).
4. `FAILED`: Job encountered an unhandled error or validation block; error message and traceback are recorded.
5. `CANCELLED`: Job aborted prior to completion.

### Stage Progression (`JobStage`)

| Stage | Progress % | Description | Subsystem Involved |
| :--- | :---: | :--- | :--- |
| `QUEUED` | 0% | Job acknowledged and queued. | `JobManager` |
| `INSPECTION` | 15% - 20% | Input inspection, CRS verification, boundary validation, security check against path traversal. | `GeometryNormalizationService` |
| `PREPROCESSING` | 30% - 50% | Coordinate projection to local dynamic UTM, footprint resolution, dataset adapter execution. | `project_geometry`, Ingestion Adapters |
| `FEATURE_EXTRACTION` | 45% | Multi-strategy height estimation, floor count resolution, strata decomposition, confidence calibration. | `FeatureExtractionPipeline`, `HeightEstimatorModel` |
| `CADASTRAL_CONSTRUCTION` | 65% - 70% | Deterministic instantiation of `LandParcel`, `Building`, `FloorLevel` strata, and non-overlapping `VerticalUnit` polygons. | `CadastreService`, `FloorEngine` |
| `ULPIN_GENERATION` | 75% | Cryptographic / geocoded derivation of 3D ULPIN identifiers for all vertical property units. | `generate_3d_ulpin` |
| `VALIDATION` | 85% - 90% | Audit against 24 deterministic cadastral rules, 3D clash detection, quality scoring (0-100), and quality grading. | `CadastralValidationService` |
| `DIGITAL_TWIN_UPDATE` | 95% | Assembly of full property digital twin linking Parcel -> Building -> Floor -> Unit -> RoR. | `DigitalTwinService` |
| `COMPLETED` | 100% | Final result reference persisted; entities ready for query and 3D visualization. | `JobManager.mark_completed` |

---

## 4. Idempotency & Safe Concurrency

To prevent race conditions, duplicate entity creation, and wasteful processing:
- When submitting `POST /api/v1/jobs/ingestion`, the engine checks if an active (`QUEUED` or `RUNNING`) job already exists for the identical source filename. If found, the existing active job is returned without spawning duplicate background workers.
- When submitting `POST /api/v1/jobs/process-parcel`, the engine checks for existing active jobs for the specified parcel ID.
- Unit 2D polygons are automatically partitioned using orthogonal geometric slicing to guarantee zero volumetric clashes between units on the same floor level.

---

## 5. REST API Reference

### 1. Submit Survey Ingestion Job
- **Endpoint**: `POST /api/v1/jobs/ingestion`
- **Status Code**: `202 Accepted`
- **Request Body**:
  ```json
  {
    "source_type": "GEOJSON",
    "source_filename": "Haveli_Survey_Block_A.geojson",
    "source_crs": "EPSG:4326",
    "dataset_payload": {
      "type": "FeatureCollection",
      "features": [...]
    },
    "metadata": {
      "surveyor": "District Land Records Office"
    }
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "data": {
      "job_id": "b8e49a5a-b439-4f05-a929-0bf3be00019a",
      "job_type": "SURVEY_INGESTION",
      "status": "QUEUED",
      "current_stage": "QUEUED",
      "progress_percent": 0.0,
      "tracking_url": "/api/v1/jobs/b8e49a5a-b439-4f05-a929-0bf3be00019a"
    },
    "message": "Survey ingestion job queued successfully."
  }
  ```

### 2. Submit End-to-End Parcel Processing Job
- **Endpoint**: `POST /api/v1/jobs/process-parcel` (or alias `POST /api/v1/process/parcel`)
- **Status Code**: `202 Accepted`
- **Request Body**:
  ```json
  {
    "state_code": 27,
    "district_code": "PUN",
    "survey_number": "SN-411001-ORCH",
    "parcel_geojson": {
      "type": "Polygon",
      "coordinates": [[[73.856, 18.52], [73.857, 18.52], [73.857, 18.521], [73.856, 18.521], [73.856, 18.52]]]
    },
    "total_height_m": 18.5,
    "ground_elevation_m": 560.0,
    "floor_count": 5,
    "basement_count": 1,
    "units_per_floor": 2,
    "auto_generate_strata": true
  }
  ```
- **Response**: Returns HTTP 202 Accepted with job ID and tracking URL.

### 3. Check Job Status & Progress
- **Endpoint**: `GET /api/v1/jobs/{job_id}`
- **Response**:
  ```json
  {
    "success": true,
    "data": {
      "job_id": "b8e49a5a-b439-4f05-a929-0bf3be00019a",
      "job_type": "END_TO_END_PARCEL_PROCESS",
      "status": "RUNNING",
      "current_stage": "CADASTRAL_CONSTRUCTION",
      "progress_percent": 65.0,
      "entity_type": "PARCEL",
      "entity_id": "b27c53d3-4dd9-43f4-a81f-c63a19cc87e5",
      "stage_details": {
        "events": [
          {"stage": "QUEUED", "progress": 0.0},
          {"stage": "INSPECTION", "progress": 15.0},
          {"stage": "PREPROCESSING", "progress": 30.0},
          {"stage": "FEATURE_EXTRACTION", "progress": 45.0},
          {"stage": "CADASTRAL_CONSTRUCTION", "progress": 65.0}
        ]
      }
    }
  }
  ```

### 4. Cancel a Running or Queued Job
- **Endpoint**: `POST /api/v1/jobs/{job_id}/cancel?reason=OperatorAborted`
- **Response**: Returns updated job with `status = "CANCELLED"`.

### 5. Retrieve Final Results
- **Endpoint**: `GET /api/v1/jobs/{job_id}/result`
- **Response**:
  ```json
  {
    "success": true,
    "data": {
      "job_id": "b8e49a5a-b439-4f05-a929-0bf3be00019a",
      "status": "COMPLETED",
      "job_type": "END_TO_END_PARCEL_PROCESS",
      "entity_type": "PARCEL",
      "entity_id": "b27c53d3-4dd9-43f4-a81f-c63a19cc87e5",
      "quality_score": 95.0,
      "quality_grade": "HIGH_CONFIDENCE",
      "is_valid": true,
      "created_entities": {
        "parcel_id": "b27c53d3-4dd9-43f4-a81f-c63a19cc87e5",
        "parcel_ulpin": "643C09C1D5CFDG",
        "building_code": "BLD-B8E49A",
        "floors_count": 5,
        "units_count": 10,
        "unit_ulpins": [
          "643C09C1D5CFDG-G00-UG0001-CN",
          "643C09C1D5CFDG-G00-UG0002-AQ",
          "643C09C1D5CFDG-L01-UL0101-MQ",
          "643C09C1D5CFDG-L01-UL0102-KT"
        ]
      },
      "validation_summary": {
        "validation_run_id": "9cbfe123-...",
        "quality_score": 95.0,
        "quality_grade": "HIGH_CONFIDENCE",
        "is_valid": true
      },
      "digital_twin_url": "/api/v1/spatial/digital-twin/b27c53d3-4dd9-43f4-a81f-c63a19cc87e5"
    }
  }
  ```

### 6. List and Filter Jobs
- **Endpoint**: `GET /api/v1/jobs?status=COMPLETED&limit=20&offset=0`
- **Response**: Paginated list of jobs with total counts.
