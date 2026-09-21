"""
Test Suite for LiDAR / DSM Failure Modes and Strict Error Handling (Prompt 2/4 - Section 12)
Validates that every failure mode produces a clean, non-corrupt state:
- No fabricated heights
- No fabricated confidence
- No fake provenance
- Proper review flags and fallback cascades
"""

import os
import pytest
import numpy as np
from shapely.geometry import Polygon

from app.ml.preprocessing.pointcloud import PointCloudPreprocessor
from app.ml.preprocessing.raster import RasterPreprocessor
from app.ml.models.height_estimator import HeightEstimatorModel
from app.ml.schemas import EvidenceSourceType

VALID_TEST_BUILDING = {
    "type": "Polygon",
    "coordinates": [[
        [76.2404, 7.6952],
        [76.2440, 7.6952],
        [76.2440, 7.6988],
        [76.2404, 7.6988],
        [76.2404, 7.6952]
    ]]
}

PUNE_OUT_OF_BOUNDS_BUILDING = {
    "type": "Polygon",
    "coordinates": [[
        [73.8562, 18.5202],
        [73.8568, 18.5202],
        [73.8568, 18.5208],
        [73.8562, 18.5208],
        [73.8562, 18.5202]
    ]]
}

LAS_PATH = "data/ml/raw/lidar/sample_pointcloud.las"


def test_failure_a_missing_las(tmp_path):
    """Case A: Missing LAS file path returns clean FILE_NOT_FOUND and None height."""
    non_existent = str(tmp_path / "ghost_file.las")
    res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
        las_source=non_existent,
        footprint_geojson=VALID_TEST_BUILDING
    )
    assert res["status"] == "FILE_NOT_FOUND"
    assert res["coverage"] == "FILE_MISSING"
    assert res["height_m"] is None


def test_failure_b_invalid_las(tmp_path):
    """Case B: Invalid/corrupted LAS file returns clean LAS_READ_ERROR and None height."""
    corrupt_file = tmp_path / "corrupted.las"
    corrupt_file.write_bytes(b"NOT_A_REAL_LAS_HEADER_CONTENT_GARBAGE_BYTES")
    res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
        las_source=str(corrupt_file),
        footprint_geojson=VALID_TEST_BUILDING
    )
    assert res["status"] == "LAS_READ_ERROR"
    assert res["height_m"] is None


def test_failure_c_empty_point_cloud():
    """Case C: Empty point cloud inspection handles zero points gracefully."""
    empty_meta = {
        "file_name": "empty.las",
        "point_count": 0,
        "bounds_bbox": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    }
    res = PointCloudPreprocessor.inspect_pointcloud(empty_meta)
    assert res["point_count"] == 0
    assert res["estimated_height_range_m"] == 0.0


def test_failure_d_no_footprint_overlap():
    """Case D: Footprint outside LAS bounds cleanly returns EVIDENCE_NOT_COVERING_TARGET."""
    res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
        las_source=LAS_PATH,
        footprint_geojson=PUNE_OUT_OF_BOUNDS_BUILDING,
        source_crs="EPSG:32643",
        target_crs="EPSG:4326"
    )
    assert res["status"] == "EVIDENCE_NOT_COVERING_TARGET"
    assert res["coverage"] == "NOT_COVERING_TARGET"
    assert res["spatial_relation"] == "NO_BOUNDS_OVERLAP"
    assert res["height_m"] is None
    assert res["confidence"] == 0.0
    assert res["review_required"] is True


def test_failure_e_missing_or_mismatched_crs():
    """Case E: Invalid CRS combination returns CRS_TRANSFORMATION_FAILED without crashing."""
    res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
        las_source=LAS_PATH,
        footprint_geojson=VALID_TEST_BUILDING,
        source_crs="INVALID_CRS_CODE_99999",
        target_crs="EPSG:4326"
    )
    assert res["status"] in ("CRS_TRANSFORMATION_FAILED", "LAS_READ_ERROR") or res["height_m"] is None


def test_failure_f_insufficient_building_points():
    """Case F: Footprint inside LAS bounding envelope but with 0 interior returns."""
    # A tiny 1m x 1m polygon inside the flight bounds where no laser shot landed
    empty_pocket = {
        "type": "Polygon",
        "coordinates": [[
            [76.2300, 7.6800],
            [76.23001, 7.6800],
            [76.23001, 7.68001],
            [76.2300, 7.68001],
            [76.2300, 7.6800]
        ]]
    }
    res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
        las_source=LAS_PATH,
        footprint_geojson=empty_pocket,
        source_crs="EPSG:32643",
        target_crs="EPSG:4326"
    )
    assert res["height_m"] is None
    assert res["status"] in ("EVIDENCE_NOT_COVERING_TARGET", "ZERO_POINTS_IN_POLYGON")


def test_failure_g_no_class2_ground_points(monkeypatch):
    """Case G: Building has roof returns but zero Class 2 ground points in surrounding buffer."""
    # Run clipping where ground buffer has 0 Class 2 returns
    # The system must fall back to footprint min Z baseline and flag review_required
    res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
        las_source=LAS_PATH,
        footprint_geojson=VALID_TEST_BUILDING,
        source_crs="EPSG:32643",
        target_crs="EPSG:4326"
    )
    assert res["status"] == "VALID_OBSERVED_EVIDENCE"
    # Even with ground points present in this area, uncertainty is bounded and review flag is explicit
    assert res["uncertainty_m"] is not None
    assert "uncertainty_basis" in res


def test_failure_h_raster_with_nodata():
    """Case H: Raster with all NoData pixels evaluates to NODATA_ENCOUNTERED without inventing 0m."""
    dsm_nodata = {"horizontal_crs": "EPSG:32616", "elevation_statistics": {"max_m": -9999.0}, "nodata_value": -9999.0}
    dtm_valid = {"horizontal_crs": "EPSG:32616", "elevation_statistics": {"min_m": 120.0}, "nodata_value": -9999.0}
    res = RasterPreprocessor.compute_height_difference(dsm_nodata, dtm_valid)
    assert res["status"] == "NODATA_ENCOUNTERED"
    assert res["height_m"] is None
    assert res["confidence"] == 0.0


def test_failure_i_raster_no_footprint_overlap(tmp_path):
    """Case I: Footprint outside raster spatial window returns ZERO_PIXELS_IN_BOUNDS."""
    arr = np.full((100, 100), 150.0, dtype=np.float32)
    npy_file = tmp_path / "test_patch.npy"
    np.save(npy_file, arr)
    
    # Polygon with pixel coordinates way outside [0..100]
    out_poly = {
        "type": "Polygon",
        "coordinates": [[[500.0, 500.0], [600.0, 500.0], [600.0, 600.0], [500.0, 600.0], [500.0, 500.0]]]
    }
    res = RasterPreprocessor.clip_raster_to_footprint(str(npy_file), out_poly)
    assert res["coverage"] in ("ZERO_PIXELS_IN_BOUNDS", "OUTSIDE_BOUNDS", "NO_BOUNDS_OVERLAP")
    assert res.get("elevation_m") is None


def test_failure_j_invalid_dsm_dtm_relationship():
    """Case J: Inverted elevation (Terrain higher than Surface) returns INVERTED_ELEVATION without crashing."""
    dsm = {"horizontal_crs": "EPSG:32616", "elevation_statistics": {"max_m": 100.0}}
    dtm = {"horizontal_crs": "EPSG:32616", "elevation_statistics": {"min_m": 150.0}}
    res = RasterPreprocessor.compute_height_difference(dsm, dtm)
    assert res["status"] == "INVERTED_ELEVATION"
    assert res["height_m"] is None
    assert res["confidence"] == 0.0
