# ML/AI-Assisted 3D Feature Extraction Engine

## 1. Executive Summary & Strict Architectural Boundary

> [!IMPORTANT]
> **Cadastral Boundary Rule**:
> AI and machine learning models in this system **PROPOSE, DETECT, ESTIMATE, or EXTRACT** features with associated confidence and uncertainty ($\pm\text{meters}$).
> AI/ML **NEVER** makes authoritative decisions regarding legal ownership, title validity, cadastral boundary definition, or property conflict declaration.
>
> All candidate features pass through the **Deterministic 3D Cadastral & Validation Engine** before being admitted into authoritative digital twin records or generating 3D ULPINs.

```
RAW SURVEY / REMOTE-SENSING DATA
        ↓
SOURCE INSPECTION (LiDAR, DEM/DSM, Imagery, CAD)
        ↓
PREPROCESSING (Point-Cloud & Raster Statistics)
        ↓
FEATURE EXTRACTION & ESTIMATION (Height, Footprint, Strata)
        ↓
CONFIDENCE & UNCERTAINTY CALIBRATION (HIGH, MEDIUM, LOW, UNKNOWN)
        ↓
PROPOSED 3D FEATURES (Candidate FloorLevel & VerticalUnit)
        ↓
EXISTING DETERMINISTIC 3D CADASTRAL ENGINE (PrismVolume, Containment)
        ↓
EXISTING DETERMINISTIC VALIDATION ENGINE (24 Cadastral Rules)
        ↓
3D ULPIN / CADASTRAL DIGITAL TWIN
```

---

## 2. Architecture & Subsystem Layout

The ML subsystem is modularly organized under [`app/ml/`](file:///d:/sihps2/app/ml/):

```
app/ml/
    __init__.py
    schemas.py                     # Standard Pydantic V2 contracts (OBSERVED, ESTIMATED, DERIVED, VALIDATED)
    preprocessing/
        pointcloud.py              # LiDAR LAS/LAZ metadata inspection, density, ground/canopy separation
        raster.py                  # DEM/DTM/DSM metadata, elevation stats, DSM - DTM height calculation
        imagery.py                 # Drone UAV photogrammetry, GSD, camera & flight coverage
    features/
        building_features.py       # Cartesian metric area, perimeter, and volumetric extrusion
        height_features.py         # Multi-strategy height resolution orchestrator
        floor_features.py          # Strata decomposition into basement, ground, and upper tiers
        vertical_features.py       # Volumetric unit proposals reusing PrismVolume & FloorEngine
    models/
        base.py                    # BaseFeatureModel interface (load, predict, health, metadata)
        building_detector.py       # BuildingDetector (LOD1 footprint proposal / NOT_CONFIGURED fallback)
        height_estimator.py        # HeightEstimatorModel (cascading 5-tier strategy)
        floor_estimator.py         # FloorEstimatorModel (non-uniform strata decomposition)
        anomaly_detector.py        # CadastralMLAnomalyDetector (outlier & discrepancy flags)
    pipelines/
        feature_extraction.py      # FeatureExtractionPipeline (end-to-end extraction orchestrator)
        vertical_cadastre.py       # VerticalCadastreFeatureService (bridges estimates to candidate cadastre)
    confidence/
        calibration.py             # ConfidenceCalibrator (evidence-based confidence & uncertainty)
```

---

## 3. Data Stage Lifecycle

Every cadastral entity and extracted feature is stamped with its explicit processing stage:

| Data Stage | Description | Permitted Action |
| :--- | :--- | :--- |
| **`OBSERVED`** | Directly measured from physical sensors (e.g. raw survey points, registered municipal deed). | Trusted sensor baseline. |
| **`ESTIMATED`** | Inferred via ML model, heuristic cascade, or remote-sensing subtraction (e.g. DSM - DTM). | Carries explicit confidence and uncertainty ($\pm\text{m}$). |
| **`DERIVED`** | Geometrically calculated from estimates (e.g. $V = \text{Area}_{UTM} \times \text{Height}$). | Computed metrics ready for validation handoff. |
| **`VALIDATED`** | Formally tested and passed against all 24 deterministic topological validation rules. | Admitted into 3D Cadastral Digital Twin & 3D ULPIN. |

---

## 4. Multi-Strategy Height Estimation

The `HeightEstimatorModel` evaluates available evidence in strict deterministic priority order:

1. **`DSM_DTM` (Priority 1)**:
   - Evaluates $\text{Height} = \text{DSM} - \text{DTM}$ using `RasterPreprocessor`.
   - **Strict NoData Handling**: If DTM is missing or if pixels contain NoData (e.g. `-9999.0`), calculation aborts with `NODATA_ENCOUNTERED`. Missing elevations are **never silently converted to zero**.
   - Confidence: $0.90 - 0.94$; Uncertainty: $\pm 0.25 - 0.5\text{m}$.
2. **`POINT_CLOUD` (Priority 2)**:
   - Evaluates $Z_{max} - Z_{min}$ or classified ASPRS class 6 (Building) minus class 2 (Ground) from LiDAR.
   - Confidence: $0.85 - 0.92$; Uncertainty: $\pm 0.25 - 0.8\text{m}$.
3. **`BUILDING_METADATA` (Priority 3)**:
   - Uses explicit `total_height_m` from registered municipal/architectural records.
   - Confidence: $0.95$; Uncertainty: $\pm 0.1\text{m}$.
4. **`FLOOR_COUNT_FALLBACK` (Priority 4)**:
   - Inferred height from known floor count using configurable engineering defaults:
     $$\text{Height} = \text{DEFAULT\_GROUND\_FLOOR\_HEIGHT\_M}\ (3.8\text{m}) + (N - 1) \times \text{DEFAULT\_FLOOR\_HEIGHT\_M}\ (3.0\text{m})$$
   - Confidence: $0.55 - 0.65$; Uncertainty: $\pm 1.2 - 2.0\text{m}$.
5. **`UNKNOWN` (Priority 5)**:
   - If no sensor or architectural evidence exists, returns `height_m = None` and `status = "INSUFFICIENT_DATA"`.
   - **Height is never fabricated**.

---

## 5. Non-Uniform Floor Strata Decomposition

The `FloorEstimatorModel` supports complex, non-uniform building structures:
- **Basements** (`B01`, `B02`...): Extends downward below ground datum $Z \le Z_{ground}$ using `DEFAULT_BASEMENT_HEIGHT_M` ($3.5\text{m}$).
- **Ground Floor** (`G00`): Plinth and ground lobby tier using `DEFAULT_GROUND_FLOOR_HEIGHT_M` ($3.8\text{m}$).
- **Typical Upper Floors** (`L01`, `L02`...): Residential/commercial strata using `DEFAULT_FLOOR_HEIGHT_M` ($3.0\text{m}$).
- **Podium & Mechanical Tiers**: Supports explicit architectural height inputs without forcing uniform vertical spacing.

---

## 6. Confidence & Uncertainty Calibration

`ConfidenceCalibrator` provides technical confidence indicators based on sensor evidence:

| Evidence Source | Confidence Score | Level | Uncertainty ($\pm\text{m}$) | Rationale |
| :--- | :---: | :---: | :---: | :--- |
| `DSM_DTM` | $0.90 - 0.94$ | `HIGH` | $\pm 0.25 - 0.40$ | High-resolution elevation raster difference. |
| `POINT_CLOUD` | $0.88 - 0.92$ | `HIGH` | $\pm 0.25 - 0.50$ | Classified LiDAR return statistics. |
| `BUILDING_METADATA` | $0.95$ | `HIGH` | $\pm 0.10$ | Legally recorded survey/architectural metadata. |
| `CAD_FLOOR_PLAN` | $0.88$ | `HIGH` | $\pm 0.15$ | Georeferenced CAD/BIM drawing level schedules. |
| `DRONE_PHOTOGRAMMETRY`| $0.75 - 0.82$ | `MEDIUM` | $\pm 0.45 - 0.80$ | Dense photogrammetric point cloud / surface mesh. |
| `ASSUMPTION_FALLBACK` | $0.50 - 0.65$ | `LOW` | $\pm 1.50$ | Parametric multiplier based on floor count assumptions. |

> **Prototype Disclaimer**: Technical confidence scores represent engineering indicators and do not establish title certainty, legal verification, or government certification.

---

## 7. Model Lifecycle & Runtime Capabilities

All models implement the `BaseFeatureModel` contract:
- `load()`: Verifies model weights or confirms heuristic fallback readiness.
- `predict()`: Executes inference or deterministic fallback.
- `health()`: Exposes runtime status (`ACTIVE`, `NOT_CONFIGURED`, `DEGRADED`, `ERROR`).
- `metadata()`: Lists supported backends (ONNX, PyTorch, DeterministicFallback).

### Zero-Crash Runtime Capability Discovery (`GET /api/v1/ml/capabilities`)
The system dynamically checks for optional C-libraries and ML accelerators:
- `has_pdal`: Point Data Abstraction Library
- `has_open3d`: 3D computer vision mesh/point library
- `has_rasterio`: GDAL/GeoTIFF raster reader
- `has_laspy`: Pythonic LAS/LAZ reader
- `has_torch`: PyTorch deep learning framework
- `has_onnx`: ONNX Runtime accelerator

If an optional library is not installed, the application **does not crash**; it reports `NOT_CONFIGURED` or `DEGRADED` and routes through deterministic fallback paths.

---

## 8. REST API Catalog

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/ml/health` | Health probe and model status across all AI adapters |
| `GET` | `/api/v1/ml/capabilities` | Inspect runtime library accelerators (PDAL, Open3D, Rasterio, Torch, ONNX) |
| `GET` | `/api/v1/ml/models` | List all AI model adapters, versioning, and configuration status |
| `POST` | `/api/v1/ml/pointcloud/inspect` | Parse LiDAR metadata, bounds, point count, and estimate elevations |
| `POST` | `/api/v1/ml/raster/inspect` | Inspect raster metadata and compute building height via DSM - DTM |
| `POST` | `/api/v1/ml/building/extract` | Extract projected metric footprint, area ($m^2$), perimeter, and volume ($m^3$) |
| `POST` | `/api/v1/ml/building/height` | Multi-strategy height estimation (DSM_DTM $\to$ Point Cloud $\to$ Metadata $\to$ Fallback) |
| `POST` | `/api/v1/ml/building/floors` | Strata decomposition into basement, ground, and upper floors |
| `POST` | `/api/v1/ml/vertical/propose` | Propose candidate vertical units and execute deterministic floor validation |
| `POST` | `/api/v1/ml/anomalies` | Scan candidate building for height outliers, compression, and geometry discrepancies |
| `POST` | `/api/v1/ml/pipeline/extract-all` | Run end-to-end extraction pipeline from remote sensing inputs to validation handoff |
