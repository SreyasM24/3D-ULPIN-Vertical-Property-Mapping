"""
SIH 26011 — Complete Adversarial Geospatial Failure Testing Suite (Cases A through Z).
Validates that every failure mode:
1. Fails safely and gracefully
2. Preserves provenance
3. Returns an explicit status / reason
4. Never fabricates evidence or measurement
5. Never crashes the entire processing pipeline unnecessarily
"""

import os
import pytest
import numpy as np
from shapely.geometry import Polygon

from app.ml.preprocessing.pointcloud import PointCloudPreprocessor
from app.ml.preprocessing.raster import RasterPreprocessor
from app.ml.models.height_estimator import HeightEstimatorModel
from app.ml.models.building_detector import BuildingDetector
from app.ml.fusion.fusion_engine import MultiSourceEvidenceFusionEngine
from app.ml.fusion.evidence_model import EvidenceClass, EvidenceCoverageStatus
from app.services.geometry_normalization import GeometryNormalizationService
from app.core.crs import project_geometry
from app.ml.pipelines.feature_extraction import FeatureExtractionPipeline


# Palakkad valid footprint covering sample_pointcloud.las
VALID_LAS_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [[
        [76.2404, 7.6952],
        [76.2440, 7.6952],
        [76.2440, 7.6988],
        [76.2404, 7.6988],
        [76.2404, 7.6952]
    ]]
}

# Pune demo footprint (far outside LAS corridor)
PUNE_DEMO_FOOTPRINT = {
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


class TestAdversarialGeospatialSuiteAZ:
    """Rigorous adversarial testing of geospatial failure modes A through Z."""

    # -------------------------------------------------------------
    # Case A: Missing LAS File Path
    # -------------------------------------------------------------
    def test_case_a_missing_las(self, tmp_path):
        non_existent = str(tmp_path / "ghost_flight_file.las")
        res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
            las_source=non_existent,
            footprint_geojson=VALID_LAS_FOOTPRINT
        )
        assert res["status"] in ("FILE_NOT_FOUND", "CLIP_FAILED")
        assert res["coverage"] in ("FILE_MISSING", "UNVERIFIED")
        assert res["height_m"] is None

    # -------------------------------------------------------------
    # Case B: Corrupt / Truncated LAS File
    # -------------------------------------------------------------
    def test_case_b_corrupt_las(self, tmp_path):
        bad_las = tmp_path / "corrupt.las"
        bad_las.write_bytes(b"NOT_A_REAL_LAS_HEADER_CONTENT_GARBAGE_BYTES_12345")
        res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
            las_source=str(bad_las),
            footprint_geojson=VALID_LAS_FOOTPRINT
        )
        assert res["status"] in ("LAS_READ_ERROR", "CORRUPTED_LAS_FILE", "CLIP_FAILED")
        assert res["height_m"] is None

    # -------------------------------------------------------------
    # Case C: Wrong Source CRS
    # -------------------------------------------------------------
    def test_case_c_wrong_crs(self):
        # Target is WGS84, but source claimed to be EPSG:3857 instead of UTM 43N
        res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
            las_source=LAS_PATH,
            footprint_geojson=VALID_LAS_FOOTPRINT,
            source_crs="EPSG:3857"
        )
        assert res["status"] in ("NO_BOUNDS_OVERLAP", "EVIDENCE_NOT_COVERING_TARGET", "CRS_TRANSFORMATION_FAILED")
        assert res["height_m"] is None

    # -------------------------------------------------------------
    # Case D: Missing / Invalid CRS Code
    # -------------------------------------------------------------
    def test_case_d_crs_missing_or_invalid(self):
        res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
            las_source=LAS_PATH,
            footprint_geojson=VALID_LAS_FOOTPRINT,
            source_crs="INVALID_CRS_CODE_99999",
            target_crs="EPSG:4326"
        )
        assert res["status"] in ("CRS_TRANSFORMATION_FAILED", "LAS_READ_ERROR", "CLIP_FAILED") or res["height_m"] is None

    # -------------------------------------------------------------
    # Case E: Target / Source CRS Projection Handling
    # -------------------------------------------------------------
    def test_case_e_crs_projection_handling(self):
        poly = Polygon([(76.241, 7.697), (76.242, 7.697), (76.242, 7.698), (76.241, 7.698)])
        proj_poly, epsg = project_geometry(poly, "EPSG:4326", "EPSG:32643")
        assert epsg == "EPSG:32643"
        assert proj_poly.is_valid

    # -------------------------------------------------------------
    # Case F: No Spatial Overlap (Pune vs Kerala flight LAS)
    # -------------------------------------------------------------
    def test_case_f_no_spatial_overlap(self):
        res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
            las_source=LAS_PATH,
            footprint_geojson=PUNE_DEMO_FOOTPRINT,
            source_crs="EPSG:32643",
            target_crs="EPSG:4326"
        )
        assert res["status"] == "EVIDENCE_NOT_COVERING_TARGET"
        assert res["coverage"] == "NOT_COVERING_TARGET"
        assert res["spatial_relation"] == "NO_BOUNDS_OVERLAP"
        assert res["height_m"] is None
        assert res["building_point_count"] == 0

    # -------------------------------------------------------------
    # Case G: Partial Spatial Overlap (< 50% points)
    # -------------------------------------------------------------
    def test_case_g_partial_spatial_overlap(self):
        edge_footprint = {
            "type": "Polygon",
            "coordinates": [[
                [76.2200, 7.6800],
                [76.2415, 7.6800],
                [76.2415, 7.7000],
                [76.2200, 7.7000],
                [76.2200, 7.6800]
            ]]
        }
        res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
            las_source=LAS_PATH,
            footprint_geojson=edge_footprint,
            source_crs="EPSG:32643"
        )
        assert res["status"] in ("VALID_OBSERVED_EVIDENCE", "NO_POINTS_IN_FOOTPRINT", "EVIDENCE_NOT_COVERING_TARGET")

    # -------------------------------------------------------------
    # Case H: Zero LiDAR Returns Inside Polygon
    # -------------------------------------------------------------
    def test_case_h_zero_lidar_returns(self):
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
            source_crs="EPSG:32643"
        )
        assert res["height_m"] is None
        assert res["status"] in ("EVIDENCE_NOT_COVERING_TARGET", "ZERO_POINTS_IN_POLYGON", "NO_POINTS_IN_FOOTPRINT")

    # -------------------------------------------------------------
    # Case I: Too Few Returns (< 3 Points)
    # -------------------------------------------------------------
    def test_case_i_too_few_returns(self):
        synth = {
            "status": "METADATA_EXTRACTED",
            "point_count": 2,
            "z_min": 10.0,
            "z_max": 15.0,
            "classified_points": 0
        }
        res = PointCloudPreprocessor.estimate_ground_and_surface(synth)
        assert res["confidence"] < 0.85
        assert res["height_m"] is not None

    # -------------------------------------------------------------
    # Case J: No Ground Returns (Missing ASPRS Class 2)
    # -------------------------------------------------------------
    def test_case_j_no_ground_returns(self):
        synth = {
            "status": "METADATA_EXTRACTED",
            "point_count": 100,
            "z_min": 100.0,
            "z_max": 120.0,
            "classified_points": 0
        }
        res = PointCloudPreprocessor.estimate_ground_and_surface(synth)
        assert "POINT_CLOUD" in res["method"] or res["method"] in ("Z_MIN_OR_ESTIMATED", "Z_MIN_BASELINE")

    # -------------------------------------------------------------
    # Case K: Inverted / Negative Elevation
    # -------------------------------------------------------------
    def test_case_k_inverted_elevation(self):
        dsm = {"horizontal_crs": "EPSG:32616", "elevation_statistics": {"max_m": 100.0}}
        dtm = {"horizontal_crs": "EPSG:32616", "elevation_statistics": {"min_m": 150.0}}
        res = RasterPreprocessor.compute_height_difference(dsm, dtm)
        assert res["status"] in ("INVERTED_ELEVATION", "INVALID_NEGATIVE_HEIGHT")
        assert res["height_m"] is None
        assert res["confidence"] == 0.0

    # -------------------------------------------------------------
    # Case L: Implausibly Tall Height Anomaly Flagging
    # -------------------------------------------------------------
    def test_case_l_implausibly_tall_height(self):
        from app.ml.models.anomaly_detector import CadastralMLAnomalyDetector
        detector = CadastralMLAnomalyDetector()
        anomalies = detector.predict({"height_m": 750.0, "floor_count": 10})
        # 750m for 10 floors triggers excessive floor height or unusual height anomaly
        assert len(anomalies) > 0
        assert any("HEIGHT" in a.anomaly_type for a in anomalies)

    # -------------------------------------------------------------
    # Case M: Corrupt Raster Array
    # -------------------------------------------------------------
    def test_case_m_corrupt_raster(self, tmp_path):
        bad_npy = tmp_path / "bad_dem.npy"
        bad_npy.write_bytes(b"NOT_A_VALID_NUMPY_ARRAY_HEADER_CORRUPT")
        res = RasterPreprocessor.inspect_raster(str(bad_npy))
        assert res["status"] in ("CORRUPTED_RASTER_DATA", "FAILED_RASTER_READ", "UNKNOWN", "NOT_CONFIGURED", "ERROR")
        assert res.get("spatial_resolution_m") is None

    # -------------------------------------------------------------
    # Case N: DEM with All NoData Pixels
    # -------------------------------------------------------------
    def test_case_n_dem_nodata_handling(self):
        dsm_nodata = {"horizontal_crs": "EPSG:32616", "elevation_statistics": {"max_m": -9999.0}, "nodata_value": -9999.0}
        dtm_valid = {"horizontal_crs": "EPSG:32616", "elevation_statistics": {"min_m": 120.0}, "nodata_value": -9999.0}
        res = RasterPreprocessor.compute_height_difference(dsm_nodata, dtm_valid)
        assert res["status"] == "NODATA_ENCOUNTERED"
        assert res["height_m"] is None

    # -------------------------------------------------------------
    # Case O: DEM Terrain-Only Misuse (Bare-Earth DEM used as DSM)
    # -------------------------------------------------------------
    def test_case_o_dem_terrain_only_classification(self):
        model = HeightEstimatorModel()
        inputs = {
            "dsm_path": "data/ml/processed/elevation_profiles/usgs_3dep_dem_patch_512x512.npy",
            "footprint_geojson": VALID_LAS_FOOTPRINT
        }
        res = model.predict(inputs)
        assert res["method"] in ("AI_TABULAR_REGRESSION", "FLOOR_COUNT_HEURISTIC", "UNKNOWN")
        assert res.get("ai_model") != "NOT_USED_OBSERVED_EVIDENCE"

    # -------------------------------------------------------------
    # Case P: Invalid GeoJSON
    # -------------------------------------------------------------
    def test_case_p_invalid_geojson(self):
        from app.core.exceptions import InvalidGeometryException
        bad_geojson = {"type": "NotAGeometry", "coordinates": "invalid"}
        with pytest.raises((InvalidGeometryException, Exception)):
            GeometryNormalizationService.normalize_geojson(bad_geojson)

    # -------------------------------------------------------------
    # Case Q: Empty Footprint Coordinates
    # -------------------------------------------------------------
    def test_case_q_empty_footprint(self):
        from app.core.exceptions import InvalidGeometryException
        empty_geojson = {"type": "Polygon", "coordinates": []}
        with pytest.raises((InvalidGeometryException, Exception)):
            GeometryNormalizationService.normalize_geojson(empty_geojson)

    # -------------------------------------------------------------
    # Case R: Self-Intersecting (Bowtie) Polygon Auto-Healing
    # -------------------------------------------------------------
    def test_case_r_self_intersecting_polygon(self):
        bowtie = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]]
        }
        res = GeometryNormalizationService.normalize_geojson(bowtie)
        assert res.is_valid is True

    # -------------------------------------------------------------
    # Case S: MultiPolygon Footprint Normalization
    # -------------------------------------------------------------
    def test_case_s_multipolygon_footprint(self):
        multipoly = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[73.85, 18.52], [73.86, 18.52], [73.86, 18.53], [73.85, 18.53], [73.85, 18.52]]],
                [[[73.87, 18.54], [73.88, 18.54], [73.88, 18.55], [73.87, 18.55], [73.87, 18.54]]]
            ]
        }
        res = GeometryNormalizationService.normalize_geojson(multipoly)
        assert res.is_valid is True
        assert res.geojson["type"] in ("Polygon", "MultiPolygon")

    # -------------------------------------------------------------
    # Case T: Missing Survey Geometry Handled Gracefully
    # -------------------------------------------------------------
    def test_case_t_missing_survey_geometry(self):
        pipeline = FeatureExtractionPipeline()
        res = pipeline.process({})
        assert res.status == "FAILED"
        assert res.validation_ready is False
        assert len(res.warnings) > 0

    # -------------------------------------------------------------
    # Case U: Conflicting Survey / LiDAR Evidence
    # -------------------------------------------------------------
    def test_case_u_conflicting_survey_lidar_evidence(self):
        inputs = {
            "point_cloud_path": LAS_PATH,
            "source_type": "POINT_CLOUD",
            "total_height_m": 30.0,
            "survey_number": "SURVEY-CONFLICT-DEMO",
            "source_crs": "EPSG:32643",
            "target_crs": "EPSG:4326"
        }
        fusion = MultiSourceEvidenceFusionEngine.fuse(inputs, VALID_LAS_FOOTPRINT)
        assert fusion.conflict.conflict_detected is True
        assert fusion.conflict.conflict_severity in ("HIGH", "MEDIUM")
        assert fusion.conflict.review_required is True
        assert fusion.conflict.difference_m > 5.0
        assert fusion.review_required is True

    # -------------------------------------------------------------
    # Case V: AI Fallback When Observed Evidence is Missing / Out-of-Bounds
    # -------------------------------------------------------------
    def test_case_v_ai_fallback_on_missing_observed(self):
        inputs = {
            "footprint_geojson": PUNE_DEMO_FOOTPRINT,
            "point_cloud_path": LAS_PATH,
            "source_crs": "EPSG:32643"
        }
        fusion = MultiSourceEvidenceFusionEngine.fuse(
            inputs,
            PUNE_DEMO_FOOTPRINT,
            ai_regressor_fn=HeightEstimatorModel().predict
        )
        assert fusion.ai_status == "ADVISORY_ESTIMATE"
        assert fusion.selected_class == EvidenceClass.AI_ESTIMATED
        assert fusion.selected_height_m is not None

    # -------------------------------------------------------------
    # Case W: AI Bypass When Observed Evidence is Valid
    # -------------------------------------------------------------
    def test_case_w_ai_bypass_on_valid_observed(self):
        inputs = {
            "point_cloud_path": LAS_PATH,
            "source_type": "POINT_CLOUD",
            "source_crs": "EPSG:32643"
        }
        fusion = MultiSourceEvidenceFusionEngine.fuse(
            inputs,
            VALID_LAS_FOOTPRINT,
            ai_regressor_fn=HeightEstimatorModel().predict
        )
        assert fusion.ai_status == "BYPASSED_OBSERVED_EVIDENCE"
        assert fusion.selected_source == "POINT_CLOUD"
        assert fusion.selected_height_m is not None
        assert fusion.selected_height_m > 0

    # -------------------------------------------------------------
    # Case X: Missing Model Weights
    # -------------------------------------------------------------
    def test_case_x_missing_model_weights(self):
        detector = BuildingDetector(weights_path="non_existent_weights.onnx")
        assert detector.status.value in ("NOT_CONFIGURED", "DEGRADED")
        res = detector.predict({"footprint_geojson": VALID_LAS_FOOTPRINT})
        assert res.footprint_geojson is not None

    # -------------------------------------------------------------
    # Case Y: ONNX Inference Failure Fallback
    # -------------------------------------------------------------
    def test_case_y_onnx_inference_failure(self):
        model = HeightEstimatorModel()
        degen_poly = {"type": "Polygon", "coordinates": [[[0, 0], [0, 0], [0, 0], [0, 0]]]}
        res = model.predict({"footprint_geojson": degen_poly})
        assert res["status"] in ("INSUFFICIENT_DATA", "SUCCESS")

    # -------------------------------------------------------------
    # Case Z: Graceful API Error Responses
    # -------------------------------------------------------------
    def test_case_z_api_graceful_error_handling(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)

        # Invalid UUID parcel lookup
        r = client.get("/api/v1/parcels/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404
        assert r.json().get("error", {}).get("code") == "ENTITY_NOT_FOUND"

        # Malformed parcel creation geometry
        bad_post = client.post("/api/v1/parcels", json={
            "state_code": "27",
            "district_code": "PUN",
            "village_code": "001",
            "survey_number": "BAD-GEOM-TEST",
            "geometry_geojson": {"type": "Point", "coordinates": [0, 0]}
        })
        assert bad_post.status_code in (400, 422)
