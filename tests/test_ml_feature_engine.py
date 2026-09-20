"""
Comprehensive Test Suite for ML/AI-Assisted 3D Feature Extraction Engine (SIH 26011).
Tests capability discovery, point cloud and raster preprocessing, multi-strategy height estimation,
strata decomposition, confidence calibration, anomaly detection, pipelines, and REST APIs.
"""

import pytest
from fastapi.testclient import TestClient

from app.ml.schemas import (
    EvidenceSourceType,
    ConfidenceLevel,
    DataStage,
    ModelStatus,
)
from app.ml.preprocessing.pointcloud import PointCloudPreprocessor
from app.ml.preprocessing.raster import RasterPreprocessor
from app.ml.preprocessing.imagery import ImageryPreprocessor
from app.ml.models.building_detector import BuildingDetector
from app.ml.models.height_estimator import HeightEstimatorModel
from app.ml.models.floor_estimator import FloorEstimatorModel
from app.ml.models.anomaly_detector import CadastralMLAnomalyDetector
from app.ml.features.building_features import BuildingFeatureExtractor
from app.ml.features.height_features import HeightFeatureExtractor
from app.ml.features.floor_features import FloorFeatureExtractor
from app.ml.confidence.calibration import ConfidenceCalibrator
from app.ml.pipelines.vertical_cadastre import VerticalCadastreFeatureService
from app.ml.pipelines.feature_extraction import FeatureExtractionPipeline
from app.services.floor_engine import FloorEngine


# ============================================================================
# 1. CAPABILITIES, HEALTH, AND MODEL STATUS
# ============================================================================

def test_ml_capabilities_detection(client: TestClient):
    """GET /api/v1/ml/capabilities dynamically detects libraries without crashing."""
    resp = client.get("/api/v1/ml/capabilities")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "has_pdal" in data
    assert "has_open3d" in data
    assert "has_rasterio" in data
    assert "has_laspy" in data
    assert "has_torch" in data
    assert "hardware_acceleration" in data
    assert isinstance(data["notes"], list)


def test_ml_health_probe(client: TestClient):
    """GET /api/v1/ml/health reports operational status of models."""
    resp = client.get("/api/v1/ml/health")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["subsystem"] == "ML_FEATURE_EXTRACTION"
    assert data["status"] in ("OPERATIONAL", "DEGRADED")
    assert len(data["models"]) >= 4


def test_ml_models_listing(client: TestClient):
    """GET /api/v1/ml/models reports registered models and their configuration state."""
    resp = client.get("/api/v1/ml/models")
    assert resp.status_code == 200
    models = resp.json()["data"]
    assert len(models) >= 4
    names = {m["model_name"] for m in models}
    assert "BuildingDetector_LOD1" in names
    assert "HeightEstimator_Cascade" in names
    assert "FloorEstimator_StrataDecomposer" in names
    assert "CadastralAnomalyDetector_Ensemble" in names


def test_building_detector_not_configured_when_no_weights():
    """BuildingDetector reports NOT_CONFIGURED when weights are unconfigured."""
    detector = BuildingDetector(weights_path="nonexistent_weights.onnx")
    assert detector.status == ModelStatus.NOT_CONFIGURED
    res = detector.predict({"building_id": "test-bld"})
    assert res.processing_metadata["status"] == "NOT_CONFIGURED"
    assert "No trained deep-learning segmentation model weights" in res.processing_metadata["explanation"]


# ============================================================================
# 2. POINT CLOUD & RASTER PREPROCESSING
# ============================================================================

def test_pointcloud_preprocessing_metadata_and_fallback():
    """Tests synthetic point cloud metadata parsing and elevation extraction."""
    synthetic_pc = {
        "file_name": "survey_site_01.laz",
        "point_count": 8500000,
        "horizontal_crs": "EPSG:32643",
        "vertical_datum": "EGM96",
        "bounds_bbox": [73.8500, 18.5100, 545.0, 73.8600, 18.5200, 575.5],
        "classification_stats": {
            "ground_z_mean": 545.2,
            "building_z_max": 574.8
        }
    }
    parsed = PointCloudPreprocessor.inspect_pointcloud(synthetic_pc)
    assert parsed["point_count"] == 8500000
    assert parsed["estimated_height_range_m"] == 30.5

    elev = PointCloudPreprocessor.estimate_ground_and_surface(parsed)
    assert elev["ground_elevation_m"] == 545.2
    assert elev["top_elevation_m"] == 574.8
    assert elev["height_m"] == 29.6
    assert elev["confidence"] > 0.85

    # Test file path that does not exist returns clean error, does not crash
    missing_file_res = PointCloudPreprocessor.inspect_pointcloud("nonexistent_cloud.las")
    assert missing_file_res["status"] == "FILE_NOT_FOUND"


def test_raster_preprocessing_and_dsm_dtm_difference():
    """Tests DSM - DTM height extraction and strict NoData rejection."""
    synthetic_dsm = {
        "raster_name": "pune_dsm.tif",
        "model_type": "DSM",
        "spatial_resolution_m": 0.25,
        "elevation_min_m": 550.0,
        "elevation_max_m": 582.4,
        "bounds_bbox": [73.85, 18.51, 73.86, 18.52]
    }
    synthetic_dtm = {
        "raster_name": "pune_dtm.tif",
        "model_type": "DTM",
        "spatial_resolution_m": 0.25,
        "elevation_min_m": 550.0,
        "elevation_max_m": 552.1,
        "bounds_bbox": [73.85, 18.51, 73.86, 18.52]
    }

    diff_res = RasterPreprocessor.compute_height_difference(synthetic_dsm, synthetic_dtm)
    assert diff_res["status"] == "CALCULATED"
    assert diff_res["height_m"] == 32.4
    assert diff_res["confidence"] >= 0.90

    # NoData safety test: missing DTM must NEVER convert to 0 height
    missing_dtm_res = RasterPreprocessor.compute_height_difference(synthetic_dsm, None)
    assert missing_dtm_res["status"] == "MISSING_RASTER_INPUT"
    assert missing_dtm_res["height_m"] is None

    # NoData value test: pixel evaluated to nodata
    nodata_dsm = dict(synthetic_dsm)
    nodata_dsm["elevation_max_m"] = -9999.0
    nodata_dsm["nodata_value"] = -9999.0
    nodata_res = RasterPreprocessor.compute_height_difference(nodata_dsm, synthetic_dtm)
    assert nodata_res["status"] == "NODATA_ENCOUNTERED"
    assert nodata_res["height_m"] is None


# ============================================================================
# 3. HEIGHT ESTIMATION PRIORITY CASCADE
# ============================================================================

def test_height_estimator_priority_cascade():
    """
    Verifies the deterministic priority order:
    1. DSM_DTM -> 2. POINT_CLOUD -> 3. BUILDING_METADATA -> 4. FLOOR_COUNT -> 5. UNKNOWN
    """
    model = HeightEstimatorModel()

    # 1. DSM + DTM available -> selects DSM_DTM
    res_dsm = model.predict({
        "dsm_metadata": {"model_type": "DSM", "elevation_max_m": 580.0, "elevation_min_m": 550.0},
        "dtm_metadata": {"model_type": "DTM", "elevation_min_m": 550.0, "elevation_max_m": 550.0},
        "pointcloud_metadata": {"bounds_bbox": [0, 0, 100, 0, 0, 115]},
        "building_metadata": {"total_height_m": 25.0}
    })
    assert res_dsm["method"] == "DSM_DTM_DIFFERENCE"
    assert res_dsm["height_m"] == 30.0

    # 2. Only Point Cloud available -> selects POINT_CLOUD
    res_pc = model.predict({
        "pointcloud_metadata": {
            "bounds_bbox": [73.8, 18.5, 500.0, 73.9, 18.6, 522.0]
        },
        "building_metadata": {"total_height_m": 18.0}
    })
    assert res_pc["source"] == EvidenceSourceType.POINT_CLOUD
    assert res_pc["height_m"] == 22.0

    # 3. Only Building Metadata available -> selects EXPLICIT_METADATA
    res_meta = model.predict({
        "building_metadata": {"total_height_m": 18.5, "ground_elevation_m": 100.0}
    })
    assert res_meta["method"] == "EXPLICIT_METADATA"
    assert res_meta["height_m"] == 18.5

    # 4. Only Floor Count available -> selects FLOOR_COUNT_HEURISTIC
    res_fl = model.predict({
        "floors_above_ground": 4
    })
    assert res_fl["method"] == "FLOOR_COUNT_HEURISTIC"
    # Ground floor: 3.8m + (3 upper floors * 3.0m) = 12.8m
    assert res_fl["height_m"] == 12.8
    assert res_fl["confidence_level"] == ConfidenceLevel.LOW

    # 5. No sources -> returns UNKNOWN, does NOT invent height
    res_unknown = model.predict({})
    assert res_unknown["method"] == "UNKNOWN"
    assert res_unknown["height_m"] is None
    assert res_unknown["confidence_level"] == ConfidenceLevel.UNKNOWN


# ============================================================================
# 4. FLOOR ESTIMATOR & STRATA DECOMPOSITION
# ============================================================================

def test_floor_estimator_strata_decomposition():
    """Tests non-uniform strata decomposition with basements, ground, and residential floors."""
    model = FloorEstimatorModel()

    res = model.predict({
        "total_height_m": 15.8,
        "ground_elevation_m": 100.0,
        "floors_above_ground": 5,
        "basement_floors": 2
    })
    assert res["estimated_floor_count"] == 7
    strata = res["strata"]
    assert len(strata) == 7

    # Check basement ordering and z ranges
    assert strata[0].level_code == "B02"
    assert strata[0].classification == "UNDERGROUND"
    assert strata[0].z_min < 100.0

    assert strata[1].level_code == "B01"
    assert strata[1].classification == "UNDERGROUND"

    # Check ground floor
    assert strata[2].level_code == "G00"
    assert strata[2].classification == "GROUND_LEVEL"
    assert strata[2].z_min == 100.0
    assert strata[2].estimated_height_m == 3.8

    # Check upper floors
    assert strata[3].level_code == "L01"
    assert strata[3].classification == "ELEVATED"
    assert strata[-1].level_code == "L04"


# ============================================================================
# 5. CONFIDENCE CALIBRATION
# ============================================================================

def test_confidence_calibration():
    """Verifies technical confidence scoring and uncertainty quantification."""
    # LiDAR evidence -> HIGH confidence
    score_pc, level_pc, unc_pc, _ = ConfidenceCalibrator.calibrate(
        [EvidenceSourceType.POINT_CLOUD], method="POINT_CLOUD_STATISTICS"
    )
    assert score_pc >= 0.90
    assert level_pc == ConfidenceLevel.HIGH
    assert unc_pc <= 0.3

    # Assumption fallback -> LOW confidence
    score_fall, level_fall, unc_fall, _ = ConfidenceCalibrator.calibrate(
        [EvidenceSourceType.ASSUMPTION_FALLBACK], method="FLOOR_COUNT_HEURISTIC"
    )
    assert score_fall <= 0.65
    assert level_fall == ConfidenceLevel.LOW
    assert unc_fall >= 1.0


# ============================================================================
# 6. ANOMALY DETECTION ADAPTER
# ============================================================================

def test_anomaly_detector():
    """Detects height outliers, vertical compression, and MultiPolygon disjoint components."""
    detector = CadastralMLAnomalyDetector()

    # Outlier height
    anomalies = detector.predict({
        "height_m": 420.0,
        "floor_count": 10
    })
    types = {a.anomaly_type for a in anomalies}
    assert "UNUSUAL_BUILDING_HEIGHT" in types
    assert "EXCESSIVE_FLOOR_HEIGHT" in types

    # Floor compression
    comp_anomalies = detector.predict({
        "height_m": 5.0,
        "floor_count": 4  # 1.25m per floor -> compression
    })
    comp_types = {a.anomaly_type for a in comp_anomalies}
    assert "FLOOR_HEIGHT_COMPRESSION" in comp_types


# ============================================================================
# 7. VERTICAL CADASTRE PROPOSALS & DETERMINISTIC VALIDATION HANDOFF
# ============================================================================

def test_vertical_cadastre_proposal_and_deterministic_validation(sample_building_geojson):
    """
    Verifies that candidate ML strata are converted to candidate cadastre
    and pass through the deterministic FloorEngine validation.
    """
    model = FloorEstimatorModel()
    strata_res = model.predict({
        "total_height_m": 9.8,
        "ground_elevation_m": 50.0,
        "floors_above_ground": 3,
        "basement_floors": 0
    })
    strata = strata_res["strata"]

    candidate = VerticalCadastreFeatureService.generate_candidate_cadastre(
        footprint_geojson=sample_building_geojson,
        ground_elevation_m=50.0,
        total_height_m=9.8,
        strata_levels=strata,
        units_per_floor=2,
        building_code="BLD-TEST-PROP"
    )
    assert candidate["is_cadastrally_consistent"] is True
    assert len(candidate["candidate_floors"]) == 3
    assert len(candidate["candidate_units"]) == 6
    assert candidate["candidate_units"][0]["volume_cu_m"] > 0
    assert candidate["stage"] == DataStage.ESTIMATED.value


# ============================================================================
# 8. END-TO-END PIPELINE & REST APIS
# ============================================================================

def test_end_to_end_pipeline(sample_building_geojson):
    """Executes FeatureExtractionPipeline and verifies end-to-end extraction result."""
    pipeline = FeatureExtractionPipeline()
    res = pipeline.process({
        "footprint_geojson": sample_building_geojson,
        "total_height_m": 12.8,
        "ground_elevation_m": 100.0,
        "floors_above_ground": 4
    })
    assert res.status == "SUCCESS"
    assert res.validation_ready is True
    assert res.features is not None
    assert res.features.area_m2 > 0
    assert res.features.volume_m3 > 0
    assert len(res.vertical_proposals) == 4
    assert len(res.provenance) >= 1


def test_api_ml_endpoints(client: TestClient, sample_building_geojson):
    """Tests all new /api/v1/ml endpoints via HTTP TestClient."""
    # 1. Inspect point cloud
    pc_resp = client.post("/api/v1/ml/pointcloud/inspect", json={
        "source": {
            "file_name": "lidar_api_test.laz",
            "point_count": 2500000,
            "bounds_bbox": [73.85, 18.51, 100.0, 73.86, 18.52, 125.0]
        }
    })
    assert pc_resp.status_code == 200
    assert pc_resp.json()["data"]["point_count"] == 2500000

    # 2. Inspect raster
    rast_resp = client.post("/api/v1/ml/raster/inspect", json={
        "dsm": {"model_type": "DSM", "elevation_max_m": 130.0, "elevation_min_m": 100.0},
        "dtm": {"model_type": "DTM", "elevation_max_m": 100.0, "elevation_min_m": 100.0}
    })
    assert rast_resp.status_code == 200
    assert rast_resp.json()["data"]["height_difference"]["height_m"] == 30.0

    # 3. Extract building features
    bld_resp = client.post("/api/v1/ml/building/extract", json={
        "footprint_geojson": sample_building_geojson,
        "height_m": 15.0,
        "floor_count": 5
    })
    assert bld_resp.status_code == 200
    assert bld_resp.json()["data"]["area_m2"] > 0
    assert bld_resp.json()["data"]["volume_m3"] > 0

    # 4. Estimate height
    h_resp = client.post("/api/v1/ml/building/height", json={
        "total_height_m": 22.5,
        "ground_elevation_m": 50.0
    })
    assert h_resp.status_code == 200
    assert h_resp.json()["data"]["height_m"] == 22.5

    # 5. Estimate floors
    fl_resp = client.post("/api/v1/ml/building/floors", json={
        "total_height_m": 12.8,
        "floors_above_ground": 4
    })
    assert fl_resp.status_code == 200
    assert fl_resp.json()["data"]["estimated_floor_count"] == 4

    # 6. Anomaly check
    anom_resp = client.post("/api/v1/ml/anomalies", json={
        "height_m": 450.0,
        "floor_count": 5
    })
    assert anom_resp.status_code == 200
    assert len(anom_resp.json()["data"]) >= 1

    # 7. Pipeline extract-all
    pipe_resp = client.post("/api/v1/ml/pipeline/extract-all", json={
        "footprint_geojson": sample_building_geojson,
        "total_height_m": 9.8,
        "floors_above_ground": 3
    })
    assert pipe_resp.status_code == 200
    assert pipe_resp.json()["data"]["status"] == "SUCCESS"
