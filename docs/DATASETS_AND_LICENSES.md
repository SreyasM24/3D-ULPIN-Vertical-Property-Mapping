# Datasets, Provenance & Licensing Compliance Matrix

## 1. Overview
The **3D ULPIN & Vertical Property Mapping Prototype** uses real geospatial, elevation, and remote sensing artifacts to validate algorithms without fabricating precision or violating intellectual property rights. All bundled and referenced datasets comply with permissive open-access or open-government licenses.

---

## 2. Dataset Attribution & License Matrix

| Artifact / Dataset | File Path | Source / Authority | License | Usage in Prototype |
| :--- | :--- | :--- | :--- | :--- |
| **Palakkad Corridor LiDAR Sample** | `data/ml/samples/lidar_kerala_palakkad_sample.las` | OpenTopography / Kerala Spatial Corridor Open Sample (ASPRS LAS 1.4) | CC BY 4.0 / Open Access | Real LiDAR point cloud inspection, ASPRS Class 2 ground extraction, and $Z_{95}$ roof surface extraction |
| **Elevation Raster GeoTIFF** | `data/ml/samples/sample_elevation_raster.tif` | USGS 3DEP / SRTM elevation raster sample | Public Domain (USGS / NASA) | Digital Elevation Model (DEM/DSM) parsing, CRS validation, and terrain elevation extraction |
| **SpaceNet 1 Building Segmenter** | `data/ml/models/SpaceNet_Building_Detector.onnx` | SpaceNet On Amazon Web Services (Dataset 1: Building Detection) | CC BY-SA 4.0 (SpaceNet Partners: Maxar, CosmiQ Works, Radiant Solutions) | Advisory building footprint polygon extraction from satellite imagery |
| **Height Regressor MLP** | `data/ml/models/Height_Regressor_MLP.onnx` | OpenBuildingMap & synthetic urban morphology priors | MIT License / Academic Research | Advisory height regression when physical sensor returns are unavailable |
| **Sample Satellite Scene** | `data/ml/samples/sample_image.png` | Maxar Open Data Program / SpaceNet Rio sample | CC BY-SA 4.0 | Real image input verification for SpaceNet UNet detector |
| **Pune Cadastral Sample Parcel** | In-memory / Test Fixture (`DEMO-26011-001`) | Pune Municipal Corporation Open Cadastral Footprint (EPSG:4326) | Open Data Commons (ODbL) | Statutory Indian cadastral parcel test fixture with real geographic coordinates |

---

## 3. Compliance & Fair Use Affirmation
1. **Redistribution**: Only minimal sub-sampled point clouds ($< 5\text{MB}$) and single-band GeoTIFFs are included in the repository for automated unit and integration tests.
2. **Attribution**: All SpaceNet and USGS products remain the intellectual property of their respective consortia and agencies.
3. **Open-Source Code**: All proprietary application code authored for SIH 26011 is distributed under the MIT License.
