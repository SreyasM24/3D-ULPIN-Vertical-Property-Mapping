# SIH 26011 — Real ML Dataset Acquisition & Quality Audit Report

**Date**: 2026-09-20  
**Project**: 3D ULPIN & Vertical Property Mapping System (SIH 26011)  
**Status**: Real Data Acquired, Verified, Documented, and Prepared (NO Model Weights Modified / NO Fake AI)

---

## 1. Executive Summary Table

| Dataset | Purpose | Region | Samples | Format | Labels | License | Size | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SpaceNet 1 (AOI 1 Rio)** | Supervised Building Footprint Segmentation | Rio de Janeiro, Brazil | 50 matched image-label pairs (2,180 building polygons) | GeoTIFF (3-band RGB, 0.5m GSD) + GeoJSON | Ground truth vector polygons & binary masks | CC-BY-SA-4.0 | 27.1 MB | **VERIFIED & READY** |
| **Microsoft Global ML Buildings (Pune)** | Real Indian Cadastral Urban Footprints | Pune, Maharashtra, India (QuadKey `123301203`) | 240,754 real detected buildings | GeoJSONL (`.csv.gz`) | Boundary polygons (WGS84 EPSG:4326) | ODbL v1.0 | 19.9 MB | **VERIFIED & READY** |
| **Microsoft Global ML Buildings (Hyderabad)** | Real Indian Cadastral Urban Footprints | Hyderabad, Telangana, India (QuadKey `123301331`) | 628,630 real detected buildings | GeoJSONL (`.csv.gz`) | Boundary polygons (WGS84 EPSG:4326) | ODbL v1.0 | 53.7 MB | **VERIFIED & READY** |
| **USGS 3DEP 1m DEM** | Airborne LiDAR Digital Elevation Surface Benchmarking | United States (AL 11-County Survey) | 10,012 x 10,012 raster grid (100.2M pixels at 1.0m resolution) | GeoTIFF (Single-band float32) | Ground truth continuous elevation (meters AMSL) | Public Domain (US Gov) | 120.2 MB | **VERIFIED & READY** |
| **Google Open Buildings 2.5D Temporal** | Height & Presence Over Time (Evaluation Only) | Global South / India | N/A (Regional GEE export required) | COG / GeoTIFF | Temporal height / presence | CC-BY-4.0 | Evaluated (4.8 GB+ per tile) | **EVALUATED / DEFERRED** (Exceeds size / Requires GEE Auth) |

**Total Raw Downloaded Size**: **220.88 MB** (Target limit: < 5,000 MB — utilizing 4.4% of budget).

---

## 2. Acquisition Status

1. **SpaceNet 1 (Building Detection)**:
   - Acquired via streaming decompression of `harshinde/spacenet-rio` (public AWS SpaceNet mirror on Hugging Face).
   - Extracted 50 geographically coherent pairs of high-resolution 3-band RGB satellite imagery and matching GeoJSON building annotations.
   - Preserved under `data/ml/raw/spacenet_rio/`.

2. **Microsoft Global ML Building Footprints (India)**:
   - Acquired directly from Microsoft Bing Maps Azure Open Data blob storage (`https://bfppub.z5.web.core.windows.net/2026-08-13/`).
   - Downloaded Level-9 QuadKey `123301203` (Pune) and QuadKey `123301331` (Hyderabad).
   - Preserved under `data/ml/raw/microsoft_buildings_india/`.

3. **USGS 3DEP 1-Meter Digital Elevation Model**:
   - Downloaded tile `USGS_1M_16_x38y376_AL_11County_B23.tif` from USGS The National Map public S3 bucket (`http://prd-tnm.s3.amazonaws.com/`).
   - Preserved under `data/ml/raw/usgs_3dep_dem/`.

4. **Google Open Buildings & 2.5D Temporal Status**:
   - Google Open Buildings v3 S2 level-4 tiles for India (`3bd_buildings.csv.gz`) are **4.81 GB** for a single compressed tile.
   - Google Open Buildings 2.5D Temporal is hosted primarily in Google Earth Engine (`GOOGLE/Research/open-buildings-temporal/v1`) requiring GEE account credentials and export jobs.
   - Per prompt strict stop condition (*"If obtaining a subset requires downloading a huge archive first, STOP instead of downloading it"* and *"credentials/login are required and cannot be legitimately completed"*), full regional downloads were deliberately deferred in favor of the lightweight, unauthenticated Microsoft India dataset (73.6 MB).

---

## 3. Validation Status & Findings

### SpaceNet Rio Subset
- **Image Integrity**: 50/50 images opened and verified with PIL. Zero corrupted images.
- **Image Specifications**: Width 438–439 px, Height 406–407 px, 3 bands (RGB), 0.5m Ground Sampling Distance.
- **Polygon Validity**: 2,180 total building polygons across 50 files. Shapely topology audit revealed **2,180 valid polygons (100.00%)** and **0 invalid / self-intersecting geometries**.
- **Spatial Alignment**: GeoKey tags (ModelTiepointTag 33922, ModelPixelScaleTag 33550) mapped polygons into pixel coordinates with 100% boundary containment, successfully rasterizing into 50 binary ground-truth segmentation masks.

### Microsoft Building Footprints (India)
- **Record Volume**:
  - Pune: 240,754 buildings.
  - Hyderabad: 628,630 buildings.
  - **Total Indian buildings in raw subset**: **869,384 real buildings**.
- **Geometry Audit**: Sampled 10,000 buildings (5,000 Pune, 5,000 Hyderabad) through Shapely: **100% valid polygons**.
- **Geographic Bounding Boxes**:
  - Pune: Lon `[73.8267, 74.5297]`, Lat `[17.9800, 18.6465]`.
  - Hyderabad: Lon `[78.0765, 78.7425]`, Lat `[17.3100, 17.9798]`.
- **Property Observations**: The `height` property is populated with `-1.0` in these tiles, indicating height was unobserved in the Bing Maxar imagery pass for these coordinates. Building footprint polygons are high-quality, closed, and valid.

### USGS 3DEP Elevation Model
- **Raster Dimensions**: 10,012 x 10,012 pixels (single-band float32).
- **Valid Elevation Pixels**: 32,585,677 pixels (remainder NoData outside survey boundary).
- **Observed Elevation Range**: Min = 83.87 m, Max = 183.41 m, Mean = 107.74 m, Std = 19.83 m.
- **Patch Extraction**: A 512 x 512 terrain patch was cropped and validated, exhibiting continuous elevation between 100.08 m and 143.17 m AMSL (Range = 43.09 m).

---

## 4. Missing Pieces & Critical Real-World Gaps

1. **Paired Drone Photogrammetry with Ground-Truth Municipal Cadastre**:
   - Public global datasets (SpaceNet, Microsoft Bing, Google Open Buildings) provide building footprints and satellite imagery, but **do not provide vertical property ownership deeds or strata plans**.
   - For vertical 3D cadastre in India (apartments, floor levels, common areas), ground-truth ownership and strata decomposition cannot be inferred solely from 2D satellite footprints. Ingestion of architectural BIM / CAD / survey floor plans (as supported by our `IngestionService` and `CadastreService`) remains an essential operational requirement.

2. **Open High-Resolution LiDAR Coverage in India**:
   - India does not currently host an openly accessible national 1m LiDAR DEM repository equivalent to USGS 3DEP.
   - For Indian deployment, the system must rely on local drone photogrammetry (DSM/DTM generated via RTK UAV missions) or Survey of India SVAMITVA drone survey data when provisioned by state cadastral authorities.

---

## 5. Model-Specific Recommendations

### Recommended Dataset for Building Model (`BuildingDetector`)
- **Primary Training Benchmark**: **SpaceNet 1 Building Detection** paired with **HOTOSM VHR Building Segmentation**.
  - **Reason**: Provides genuine high-resolution satellite imagery with 1-to-1 matching ground-truth binary masks and vector GeoJSON boundaries. Enables training a standard segmentation backbone (e.g. U-Net with ResNet/EfficientNet encoder, or fine-tuning SAM) to propose building boundaries from raw imagery.
- **Cadastral Cross-Validation**: **Microsoft Building Footprints for India (Pune & Hyderabad)**.
  - **Reason**: 869,384 real Indian urban footprints allow rigorous testing of geometric normalization, polygon repair, ULPIN generation, and building-to-parcel containment checks.

### Recommended Dataset for Height Model (`HeightEstimator`)
- **Primary Elevation Benchmark**: **USGS 3DEP 1-Meter LiDAR DEM** + **Synthesized DSM/DTM Differences**.
  - **Reason**: The 1m DEM provides high-accuracy, continuous surface terrain. By pairing terrain models with building footprints, the height estimation cascade (DSM - DTM raster difference strategy) can be empirically benchmarked for numerical stability and NoData boundary handling.
- **Future Integration**: When authorized, ingest local Survey of India SVAMITVA drone survey point clouds (`.las` / `.laz`) into `PointCloudPreprocessor`.

---

## 6. Readiness Assessment: Can Training Begin?

| Subsystem | Training Readiness | Rationale |
| :--- | :--- | :--- |
| **Building Footprint Segmentation** | **YES (Ready for Initial Prototype)** | 50 paired SpaceNet image-mask-geojson sets (2,180 buildings) plus 2,000 sampled Indian cadastral footprints are stored in `data/ml/processed/` and indexed in `pairs_index.json`. A supervised segmentation model (e.g. PyTorch U-Net) can be trained immediately on these pairs. |
| **Height Estimation Regression** | **PARTIAL (Heuristic / Raster Difference Ready)** | Real 1m elevation raster data is acquired and validated. Direct supervised height regression without DSM/DTM pairs is unadvisable because raw satellite footprints in open datasets lack reliable height labels. The existing deterministic cascading strategy remains the soundest approach until paired DSM/DTM data is provided. |
| **Vertical Strata / Floor Estimation** | **RULE-BASED OPTIMAL** | Floor estimation in cadastral law must adhere to building codes and registered architectural plans. Machine learning should serve as an advisory proposal, with the existing deterministic `FloorEstimator_StrataDecomposer` providing the verified legal baseline. |

---

## 7. Conclusion

The repository now possesses an authentic, verified, documented, and reproducible real-world dataset foundation (**220.88 MB**) with zero fabricated data, zero synthetic placeholders, and full machine-readable manifests. Application code and deterministic fallbacks remain completely intact.
