# SIH 26011 — Real Building Height Intelligence Data Audit Report

**Date**: 2026-09-20  
**Subsystem**: ML Feature Extraction / Height Intelligence  
**Status**: Real Matched Cadastral Footprints + Airborne LiDAR Height Dataset Acquired & Audited  

---

## 1. Executive Summary Table

| Dataset | Region | Buildings | Usable Heights | Median Height | P95 Height | Source | License |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **3DBAG (AHN4 LiDAR + Cadastre)** | Delft, South Holland (Contiguous Urban BBOX) | **1500** | **1220** | **8.32 m** | **12.66 m** | TU Delft 3D Geoinformation / Netherlands Kadaster | CC0 1.0 Universal (Public Domain) |

---

## 2. Acquisition & Provenance Details

- **Dataset Name**: 3D Basisregistratie Adressen en Gebouwen (3DBAG, v2025.09)
- **Primary Host**: `https://data.3dbag.nl/api/BAG3D/wfs`
- **Geographic Coverage**: Delft, Netherlands (Bounding Box: Lon `[4.350, 4.380]`, Lat `[52.000, 52.020]`)
- **Native CRS**: EPSG:28992 (Amersfoort / RD New) projected to WGS84 (EPSG:4326) with metric cartographic features in UTM Zone 31N (EPSG:32631)
- **Footprint Source**: Official municipal cadastral building registry (BAG)
- **Elevation Source**: Actueel Hoogtebestand Nederland (AHN4) nationwide airborne LiDAR survey
  - Mean Point Cloud Density: **30.0+ pts/m²**
  - Vertical Surface Model: Level-of-Detail 1.2 extruded planar roof models with 50th, 70th, and maximum percentile roof elevations
  - Terrain Reference: Ground elevation `b3_h_maaiveld` (meters above Amsterdam Ordnance Datum / NAP)
- **Download Footprint**: 1.62 MB total (0.05% of 3,000 MB download budget)

---

## 3. Data Validation & Rejection Breakdown

Every candidate building was filtered through an 8-point physical and geometric validation gate:

1. **Footprint Geometry Validity**: Validated via Shapely topology. Auto-repaired non-simple rings and isolated single-polygon footprints.
2. **Elevation Overlap**: Guaranteed spatial intersection between cadastral polygon and AHN LiDAR point cloud.
3. **LiDAR Sufficiency**: Required point density $\ge 3.0\text{ pts/m}^2$ and NoData fraction $\le 25\%$.
4. **Terrain Reference**: Verified presence of continuous ground datum `b3_h_maaiveld`.
5. **Physical Plausibility**: Enforced height limits $2.0\text{m} \le h \le 120.0\text{m}$.
6. **NoData Handling**: Features lacking measured LiDAR elevation or with excessive occlusion were rejected.
7. **Metric Integrity**: Projected coordinates converted to UTM Zone 31N for metric area, perimeter, compactness, and aspect ratio.
8. **Units**: Metric meters throughout (AMSL elevations, relative heights, square-meter footprints).

### Rejection Accounting:
- **Total Candidate Buildings**: 1500
- **Genuinely Usable Height Samples**: **1220** (81.3% acceptance)
- **Rejected Records**: 280 (18.7%)

**Rejection Reasons Breakdown**:
- `zero_or_tiny_area` (< 10 m²): 250
- `missing_terrain_elev`: 0
- `missing_roof_elev`: 0
- `implausible_height` (< 2m or > 120m): 0
- `high_nodata_fraction` (> 25%): 30
- `insufficient_point_density` (< 3 pts/m²): 0
- `invalid_geometry`: 0
- `not_polygon`: 0

---

## 4. Observed Height Distribution Statistics

| Statistic | Value (Meters) | Description |
| :--- | :--- | :--- |
| **Minimum Height** | **2.15 m** | Low single-story annex or outbuilding |
| **25th Percentile (P25)** | **6.38 m** | Standard 1-2 story residential building |
| **Median Height (P50)** | **8.32 m** | Typical 2-3 story European urban structure |
| **Mean Height** | **8.12 m** | Average height across all usable samples |
| **75th Percentile (P75)** | **9.57 m** | 3-4 story commercial/multi-unit building |
| **90th Percentile (P90)** | **11.37 m** | 4-6 story apartment or institutional block |
| **95th Percentile (P95)** | **12.66 m** | High-rise / university facility |
| **Maximum Height** | **28.23 m** | Tallest urban tower in the survey tile |
| **Standard Deviation** | **3.00 m** | Natural urban height variance |

---

## 5. Decision Gate Assessment

- **Requirement**: Threshold of **500+ genuinely usable samples** required to justify supervised machine learning.
- **Audited Count**: **1220 validated samples** produced.
- **Decision**: **GATE PASSED**. Proceeding to Phase B (Supervised Regression Model, ONNX Export, and HeightEstimator Integration).
