# 3D ULPIN & Vertical Property Mapping Engine: Architectural Specification

## 1. Executive Summary & Purpose
The **3D ULPIN & Vertical Property Mapping Engine** is an open-source, evidence-driven cadastral intelligence platform engineered for the **Smart India Hackathon (SIH) Problem Statement 26011**. It bridges raw spatial sensor evidence (ASPRS LAS/LAZ point clouds, GeoTIFF elevation models, vector GIS polygons, and satellite imagery) with statutory Indian land administration systems.

The platform deterministically constructs 3D stratified cadastral property units, enforces sub-millimeter topological integrity, generates statutory 3D Unique Land Parcel Identification Numbers (3D ULPIN) with ISO/IEC 7064 MOD 37-36 checksums, and provides an immutable provenance chain for legal defensibility.

---

## 2. Core Architectural Principles
1. **Zero Evidence Fabrication**: The system never manufactures precision or invents height values. All heights are classified into strict epistemological categories: `OBSERVED`, `AI_ESTIMATED`, `DETERMINISTIC`, `UNRESOLVED`, and `TEST_FIXTURE`.
2. **Strict Spatial & CRS Gating**: Sensor datasets are validated against spatial extents and Coordinate Reference Systems (EPSG:4326 WGS84, EPSG:32643 UTM 43N, etc.) before ingestion. Out-of-bounds artifacts are strictly rejected.
3. **Multi-Source Evidence Conflict Arbitration**: When multiple sources disagree beyond a statistically defensible threshold ($|\Delta H| > 2\sqrt{\sigma_A^2 + \sigma_B^2}$), the engine raises a high-severity `EVIDENCE_CONFLICT` alert and sets `review_required = True`. AI models are explicitly prohibited from silently arbitrating legal boundaries.
4. **Deterministic Cadastral Construction**: Vertical strata subdivision, floor elevations, unit extents, and ULPIN checksums are mathematically reproducible from boundary definitions.
5. **Separation of Legal & Advisory Layers**: AI models (SpaceNet UNet footprint detector and multi-layer height regressor) function solely in an advisory capacity, clearly flagged as `ADVISORY_ESTIMATE`, and are bypassed when authoritative sensor evidence exists.

---

## 3. High-Level System Architecture

```
                                    +-----------------------------------------+
                                    |         React + Vite + TypeScript       |
                                    |   (Three.js 3D Viewer, Provenance Panel,|
                                    |    Conflict Inspector, Temporal Audit)  |
                                    +--------------------+--------------------+
                                                         | REST API (HTTP)
                                                         v
                                    +-----------------------------------------+
                                    |            FastAPI API Layer            |
                                    |  (/jobs, /parcels, /validation, /ml)    |
                                    +--------------------+--------------------+
                                                         |
                                                         v
+---------------------------------------------------------------------------------------------------------------+
|                                             Job Orchestrator Engine                                           |
+---------------------------------------------------------------------------------------------------------------+
       |                                      |                                  |
       v                                      v                                  v
+-----------------------+      +-------------------------------+      +-------------------------------+
| Geospatial Inspection |      |  Evidence Fusion & Arbitration|      |    3D Cadastral Engine        |
| - LAS/LAZ Point Cloud | ---> |  - Priority Hierarchy Engine  | ---> |  - Vertical Strata Generator  |
| - GeoTIFF DEM/DSM     |      |  - 2-Sigma Conflict Detector  |      |  - Footprint Inset & Extrusion|
| - CRS Transformer     |      |  - AI Bypass Controller       |      |  - Floor/Unit Volume Allocator|
+-----------------------+      +-------------------------------+      +-------------------------------+
                                                                                     |
       +-----------------------------------------------------------------------------+
       v
+-------------------------------+      +-------------------------------+      +-------------------------------+
|    3D ULPIN Generator         |      |    3D Validation Engine       |      |    Digital Twin & Provenance  |
| - Bounding Box Hash           | ---> |  - Boundary Containment       | ---> |  - 3D Digital Twin Registry   |
| - Floor & Unit Formatter      |      |  - Floor Overlap & Vol. Ratio |      |  - Complete Audit Trail       |
| - ISO/IEC 7064 Checksum       |      |  - Surface Boundary Checks    |      |  - GeoJSON / CityJSON Export  |
+-------------------------------+      +-------------------------------+      +-------------------------------+
```

---

## 4. Pipeline Stages & Subsystems

### 4.1 Geospatial Evidence Ingestion (`app/services/spatial/`)
- **Point Cloud Engine (`point_cloud_service.py`)**: Uses `laspy` to inspect ASPRS LAS/LAZ headers, point records, and CRS metadata. Implements spatial bounding box containment checks, ASPRS Class 2 (Ground) extraction, and robust 95th percentile ($Z_{95}$) roof surface extraction to eliminate multipath/antenna noise.
- **Elevation Raster Engine (`elevation_service.py`)**: Uses `rasterio` and `pyproj` to parse GeoTIFF digital elevation models, checking pixel resolution, CRS validity, and spatial overlap.
- **Uncertainty Quantification**: Calculates derived vertical uncertainty from point density ($n / \text{area}$) and sensor precision, ensuring zero hardcoded false precision.

### 4.2 Multi-Source Evidence Fusion (`app/ml/fusion/`)
- **Priority Hierarchy**:
  1. Statutory Land Survey (`SURVEY_ACCURATE`, $\sigma = \pm 0.10\text{m}$)
  2. Observed LiDAR Point Cloud (`LIDAR_OBSERVED`, $\sigma = \pm 0.15\text{m} - \pm 1.57\text{m}$)
  3. DSM/DTM Elevation Difference (`ELEVATION_RASTER_OBSERVED`, $\sigma = \pm 0.50\text{m}$)
  4. Drone Photogrammetry (`PHOTOGRAMMETRY`, $\sigma = \pm 0.35\text{m}$)
  5. Building Architectural CAD/BIM (`CAD_BIM_EXTRACTED`, $\sigma = \pm 0.25\text{m}$)
  6. AI Inferential Height (`AI_ESTIMATED`, $\sigma = \pm 2.50\text{m}$)
  7. Deterministic Default (`DETERMINISTIC_FALLBACK`, $\sigma = \pm 3.00\text{m}$)
- **Conflict Arbitration**: Computes difference $\Delta H = |H_A - H_B|$ and composite standard deviation $\sigma_{AB} = \sqrt{\sigma_A^2 + \sigma_B^2}$. If $\Delta H > 2 \sigma_{AB}$, logs structured `EvidenceConflictRecord`, alerts the cadastral officer, and preserves both raw observations in the digital twin.

### 4.3 Cadastral Construction & 3D ULPIN (`app/services/cadastral/` & `app/services/ulpin/`)
- **Vertical Strata Engine**: Extrudes 2D building footprints across ground elevation, basements ($B01, B02\dots$), ground level ($G00$), and upper floors ($L01, L02\dots$).
- **Unit Subdivision**: Computes horizontal subdivision corridors and units ($UG0001, UL0101\dots$), assigning true 3D PolyhedralSurface boundaries.
- **3D ULPIN Structure**: Format `<14-char Base ULPIN>-<Floor Code>-<Unit Code>-<2-char Checksum>`. Example: `2B4B1E9AC6711J-L07-UL0701-YS`. Uses statutory ISO/IEC 7064 MOD 37-36 check character calculation.

### 4.4 3D Cadastral Validation Engine (`app/services/validation/`)
- Enforces statutory validation gates:
  - **Boundary Containment**: All unit geometries must reside 100% within the statutory parcel footprint.
  - **Floor Overlap**: Zero volume intersection between adjacent floor levels ($\text{IoU} = 0.000$).
  - **Volume Conservation**: The sum of unit volumes plus common areas strictly matches the total building prism volume.
  - **Surface Closure**: All 3D PolyhedralSurface shells must be watertight manifolds.

### 4.5 Digital Twin & Temporal Audit Registry (`app/services/digital_twin_service.py`)
- Maintains versioned snapshots of parcels, buildings, floors, and vertical units.
- Serializes digital twins to standard formats: GeoJSON 3D FeatureCollection, CityJSON LoD2, and CSV register of rights.
- Provides differential temporal comparison to inspect changes over time (height additions, floor subdivision, boundary re-surveys).

---

## 5. Security, Performance & Scalability
- **Runtime Performance**: End-to-end processing pipeline executes in $< 1.25\text{s}$ per complex multi-unit building parcel.
- **Async Execution**: Long-running jobs run through an asynchronous job queue with state transitions (`QUEUED`, `INSPECTION`, `PREPROCESSING`, `FEATURE_EXTRACTION`, `CADASTRAL_CONSTRUCTION`, `ULPIN_GENERATION`, `VALIDATION`, `DIGITAL_TWIN_UPDATE`, `COMPLETED`).
- **Auditability**: Cryptographic SHA-256 hashes attached to input evidence, ML model weights, and 3D ULPIN registers.
