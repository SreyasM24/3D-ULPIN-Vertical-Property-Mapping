# SIH 26011 — Real-World ML Dataset Foundation

## 1. Overview & Objective

This repository contains the real-world dataset foundation for the **3D ULPIN & Vertical Property Mapping System (SIH 26011)** ML pipeline.

### Core Principle
- **No Fabricated Data**: All data assets in this folder are derived from verified official public sources.
- **No Untrained AI Claims**: The system currently operates on deterministic rule-based cadastral logic. These datasets provide the empirical grounding required for training and evaluating future deep learning models (Building Detection, Strata Decomposition, and Elevation/Height Extraction).
- **Strict Size Bounds**: The entire downloaded raw dataset is **220.9 MB**, well below the 5 GB budget limit.

---

## 2. Dataset Sources & Metadata

| Dataset | Provider / Source | Region / Coverage | Format | Size | License | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SpaceNet 1 (AOI 1 Rio)** | SpaceNet / DigitalGlobe / AWS Open Data | Rio de Janeiro, Brazil | GeoTIFF (3-band RGB, 0.5m GSD) + GeoJSON | 27.1 MB | CC-BY-SA-4.0 | Supervised building footprint segmentation (image $\to$ polygon mask) |
| **Microsoft Global ML Buildings (Pune)** | Microsoft Bing Maps Open Buildings / Azure | Pune, Maharashtra, India (QuadKey `123301203`) | GeoJSON Lines (`.geojsonl.gz`) | 19.9 MB | ODbL v1.0 | Real cadastral building boundaries in urban India for base parcel attribution |
| **Microsoft Global ML Buildings (Hyderabad)** | Microsoft Bing Maps Open Buildings / Azure | Hyderabad, Telangana, India (QuadKey `123301331`) | GeoJSON Lines (`.geojsonl.gz`) | 53.7 MB | ODbL v1.0 | Real cadastral building boundaries in urban India for 3D ULPIN spatial indexing |
| **USGS 3DEP 1-Meter DEM** | USGS The National Map / AWS Public S3 | United States (AL 11-County LiDAR Survey) | GeoTIFF (Single-band float32, 1m GSD) | 120.2 MB | Public Domain (US Gov) | Ground truth terrain elevation & raster preprocessor benchmarking |

---

## 3. Detailed Dataset Specifications

### A. SpaceNet 1 Building Detection (AOI 1 Rio)
- **Source URL**: `https://huggingface.co/datasets/harshinde/spacenet-rio` (Mirror of `s3://spacenet-dataset/AOI_1_Rio/`)
- **License**: Creative Commons Attribution-ShareAlike 4.0 International (CC-BY-SA-4.0)
- **Geographic Coverage**: Latitude `[-22.992, -22.838]`, Longitude `[-43.743, -43.488]`
- **CRS**: EPSG:4326 (WGS 84)
- **Extracted Subset**: 50 matched pairs of 3-band RGB GeoTIFFs (~439 x 406 pixels at 0.5m resolution) and verified GeoJSON polygons (2,180 total building polygons, 100% valid geometry).
- **Processed Derivative**: Binary segmentation masks (PNG) rendered at pixel-level accuracy with paired index in `data/ml/processed/building_segmentation/pairs_index.json`.

### B. Microsoft Global ML Building Footprints — India
- **Source URL**: `https://bfppub.z5.web.core.windows.net/2026-08-13/global-buildings.geojsonl/`
- **Official Repository**: `https://github.com/microsoft/GlobalMLBuildingFootprints`
- **License**: Open Data Commons Open Database License (ODbL) v1.0
- **Geographic Coverage**:
  - **Pune QuadKey `123301203`**: 240,754 building polygons across Lat `[17.980, 18.646]`, Lon `[73.827, 74.530]`.
  - **Hyderabad QuadKey `123301331`**: 628,630 building polygons across Lat `[17.310, 17.980]`, Lon `[78.076, 78.742]`.
- **CRS**: EPSG:4326 (WGS 84)
- **Processed Derivative**: Clean GeoJSON FeatureCollections of 1,000 real buildings each in `data/ml/processed/cadastral_footprints_india/` with centroid, area, perimeter, and bounding box metrics.

### C. USGS 3DEP 1-Meter Digital Elevation Model (DEM)
- **Source URL**: `http://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/AL_11County_B23/TIFF/USGS_1M_16_x38y376_AL_11County_B23.tif`
- **License**: Public Domain (U.S. Government Work, CC0 equivalent)
- **CRS**: EPSG:6345 (NAD83 2011 UTM Zone 16N)
- **Dimensions**: 10,012 x 10,012 pixels at 1.0m spatial resolution.
- **Elevation Range**: 83.87 m to 183.41 m AMSL (Mean: 107.74 m, Std: 19.83 m).
- **Processed Derivative**: 512 x 512 terrain elevation patch (`usgs_3dep_dem_patch_512x512.tif` and `.npy`) with metadata.

---

## 4. What Each Dataset Can and Cannot Be Used For

### SpaceNet 1
- **Can Be Used For**:
  - Training and validating 2D instance / semantic segmentation models (Mask R-CNN, U-Net, SAM fine-tuning).
  - Benchmarking boundary extraction algorithms against official satellite imagery.
- **Cannot Be Used For**:
  - 3D height estimation (SpaceNet 1 does not contain height or LIDAR attributes).
  - Indian cadastral ownership or boundary validation (imagery is located in Rio de Janeiro).

### Microsoft Global ML Building Footprints (India)
- **Can Be Used For**:
  - Real Indian urban cadastral envelope evaluation.
  - Stress testing 3D ULPIN spatial indexing algorithms on hundreds of thousands of real parcel/building polygons.
  - Spatial overlap, containment, and clash detection validation.
- **Cannot Be Used For**:
  - Direct computer vision training without satellite imagery (only vector polygons are provided).
  - Direct height estimation for these tiles (the `height` attribute is unpopulated / `-1.0` in these specific quadkeys).

### USGS 3DEP 1-Meter DEM
- **Can Be Used For**:
  - Validating `RasterPreprocessor` elevation parsing, coordinate sampling, and slope calculation.
  - Simulating terrain datum baseline corrections ($Z_{\text{ground}}$).
- **Cannot Be Used For**:
  - Indian legal cadastral heights (geographically located in North America).
  - Building footprint extraction without paired aerial imagery.

---

## 5. Dataset Limitations

1. **Height Attribution Gap**: Microsoft building footprints for Pune/Hyderabad do not include estimated height. SpaceNet 1 does not include height. Real building height in India requires either registered survey architectural drawings (e.g. municipal floor plans) or paired DSM - DTM differences.
2. **Google Open Buildings 2.5D Temporal Evaluation**:
   - Google Open Buildings v3 compressed S2 tiles for India (`3bd_buildings.csv.gz`) are **4.8 GB each** for a single tile, exceeding safe atomic download thresholds.
   - Google Open Buildings 2.5D Temporal is hosted via Google Earth Engine (`GOOGLE/Research/open-buildings-temporal/v1`) which requires active GEE account credentials and export pipelines rather than direct unauthenticated HTTP streaming.
   - Therefore, Microsoft India Footprints (73.6 MB) + SpaceNet (27.1 MB) + USGS DEM (120.2 MB) was selected as the optimal unauthenticated reproducible set.

---

## 6. Directory Structure

```
data/ml/
├── manifests\
│   ├── dataset_manifest.json          # Machine-readable SHA256, paths, licenses, metadata
│   ├── dataset_manifest.csv           # Tabular manifest representation
│   └── spacenet_pairs_manifest.json   # 50 per-pair SpaceNet image-to-mask mappings
├── raw\
│   ├── spacenet_rio\
│   │   ├── images\                    # 50 3-band GeoTIFF satellite tiles
│   │   └── geojson\                   # 50 corresponding building polygon GeoJSONs
│   ├── microsoft_buildings_india\
│   │   ├── ms_buildings_india_pune_123301203.geojsonl.gz      # 240,754 Pune buildings
│   │   └── ms_buildings_india_hyderabad_123301331.geojsonl.gz # 628,630 Hyderabad buildings
│   └── usgs_3dep_dem\
│       └── USGS_1M_16_x38y376_AL_11County_B23.tif             # 10,012x10,012 1m LiDAR DEM
├── processed\
│   ├── building_segmentation\
│   │   ├── images\                    # 50 PNG RGB images
│   │   ├── masks\                     # 50 PNG binary ground truth building masks
│   │   ├── geojson\                   # 50 GeoJSON building boundary files
│   │   └── pairs_index.json           # Paired index with building count & pixel coverage
│   ├── cadastral_footprints_india\
│   │   ├── pune_buildings_sample_1000.geojson       # 1,000 Pune building polygons
│   │   └── hyderabad_buildings_sample_1000.geojson  # 1,000 Hyderabad building polygons
│   └── elevation_profiles\
│       ├── usgs_3dep_dem_patch_512x512.tif          # 512x512 GeoTIFF elevation patch
│       ├── usgs_3dep_dem_patch_512x512.npy          # NumPy float32 elevation array
│       └── patch_metadata.json                      # Min/Max/Mean elevation statistics
├── samples\
│   ├── sample_image.png               # Exemplar satellite image (SpaceNet)
│   ├── sample_mask.png                # Exemplar ground truth building mask
│   ├── sample_footprint.geojson       # Exemplar vector building footprint
│   ├── sample_cadastral_pune_building.json        # Real Pune building GeoJSON feature
│   ├── sample_cadastral_hyderabad_building.json   # Real Hyderabad building GeoJSON feature
│   └── sample_elevation_profile.json  # Terrain elevation patch metadata
└── README.md
```

---

## 7. Reproducibility Information

All assets can be reproduced identically by running the extraction scripts located in `<brain>/scratch/`:
1. `python download_spacenet.py`: Streams and matches 50 SpaceNet image and GeoJSON pairs from Hugging Face public endpoint without authentication.
2. `python download_ms_buildings.py`: Downloads Pune and Hyderabad quadkey GeoJSONL tiles directly from Microsoft Azure Open Data Blob storage.
3. `python download_usgs.py`: Downloads the 1m DEM GeoTIFF from the USGS The National Map AWS public S3 repository.
4. `python prepare_samples.py`: Generates the paired binary masks, processed GeoJSON samples, and elevation patches.
5. `python generate_manifests.py`: Verifies SHA256 hashes and generates `dataset_manifest.json` and `dataset_manifest.csv`.

---

## 8. Why This Subset is Sufficient for the Next ML Stage

1. **Building Segmentation**: The 50 SpaceNet image-mask pairs contain 2,180 verified building polygons across diverse urban density conditions, providing sufficient validation and fine-tuning data for an initial U-Net / SegNet prototype.
2. **Indian Urban Cadastre**: The 869,384 real building footprints across Pune and Hyderabad provide comprehensive real-world spatial geometries for testing 3D ULPIN generation, spatial containment, and legal boundary checks.
3. **Terrain Modeling**: The 1m USGS DEM provides high-precision continuous elevation gradients to test the elevation parsing and NoData handling logic of `RasterPreprocessor`.
