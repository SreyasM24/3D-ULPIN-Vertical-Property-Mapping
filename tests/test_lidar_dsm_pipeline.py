"""
Comprehensive Test Suite for Real LiDAR / DSM / Point-Cloud -> 3D ULPIN Pipeline
Tests the strict evidence-driven extraction, CRS validation, ASPRS Class 2 ground separation,
spatial footprint clipping, Z95 surface statistics, non-hardcoded uncertainty formulation,
and spatial coverage gating (Critical Rules 1 & 2).
"""

import os
import pytest
import numpy as np
from shapely.geometry import Polygon, mapping

from app.ml.preprocessing.pointcloud import PointCloudPreprocessor
from app.ml.preprocessing.raster import RasterPreprocessor
from app.ml.models.height_estimator import HeightEstimatorModel
from app.ml.pipelines.feature_extraction import FeatureExtractionPipeline
from app.ml.schemas import EvidenceSourceType, ModelStatus
from app.models.parcel import LandParcel
from app.jobs.manager import JobManager
from app.jobs.schemas import JobType, JobStatus
from app.jobs.orchestrator import CadastralProcessingOrchestrator
from app.services.digital_twin_service import DigitalTwinService


LAS_FILE_PATH = "data/ml/raw/lidar/sample_pointcloud.las"
DEM_NPY_PATH = "data/ml/processed/elevation_profiles/usgs_3dep_dem_patch_512x512.npy"

# Projected coordinate footprint directly matching sample_pointcloud.las extent
VALID_LAS_PROJECTED_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [[
        [636500.0, 850000.0],
        [638000.0, 850000.0],
        [638000.0, 852000.0],
        [636500.0, 852000.0],
        [636500.0, 850000.0]
    ]]
}

# WGS84 geographic footprint corresponding to the projected LAS extent in EPSG:32643
VALID_LAS_WGS84_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [[
        [76.2376, 7.6879],
        [76.2513, 7.6879],
        [76.2513, 7.7060],
        [76.2376, 7.7060],
        [76.2376, 7.6879]
    ]]
}

# Building footprint strictly contained within the LAS flight extent in EPSG:32643
VALID_LAS_WGS84_BUILDING = {
    "type": "Polygon",
    "coordinates": [[
        [76.2404, 7.6952],
        [76.2440, 7.6952],
        [76.2440, 7.6988],
        [76.2404, 7.6988],
        [76.2404, 7.6952]
    ]]
}

# Pune demo parcel coordinates (EPSG:4326 degrees, far from LAS spatial extent)
PUNE_DEMO_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [[
        [73.8560, 18.5200],
        [73.8570, 18.5200],
        [73.8570, 18.5210],
        [73.8560, 18.5210],
        [73.8560, 18.5200]
    ]]
}


class TestPointCloudPreprocessing:
    """Tests for raw LAS point cloud inspection and spatial polygon footprint clipping."""

    def test_las_file_exists(self):
        assert os.path.exists(LAS_FILE_PATH), f"LAS artifact not found at {LAS_FILE_PATH}"

    def test_las_inspection(self):
        meta = PointCloudPreprocessor.inspect_pointcloud(LAS_FILE_PATH)
        assert meta["status"] in ("HEADER_READ", "METADATA_EXTRACTED")
        assert meta["point_count"] == 1065
        bbox = meta.get("bounds_bbox")
        assert bbox is not None and len(bbox) >= 6
        assert bbox[0] < bbox[3]  # min_x < max_x
        assert bbox[1] < bbox[4]  # min_y < max_y
        assert bbox[2] < bbox[5]  # min_z < max_z
        assert "las_version" in meta
        assert meta.get("min_z") == 406.59
        assert meta.get("max_z") == 586.38

    def test_las_clipping_covering_footprint(self):
        """DEMO A: Footprint inside LAS extent produces valid observed height and stats."""
        res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
            las_source=LAS_FILE_PATH,
            footprint_geojson=VALID_LAS_PROJECTED_FOOTPRINT
        )
        assert res["status"] == "VALID_OBSERVED_EVIDENCE"
        assert res["coverage"] == "VALID"
        assert res["point_count"] == 1065
        assert res["building_point_count"] > 0
        assert res["ground_point_count"] > 0
        assert res["surface_elevation_m"] > res["ground_elevation_m"]
        assert res["height_m"] > 0.0
        # Critical Rule 1 check: Uncertainty must NOT be a hardcoded 0.20m, but derived statistically
        assert "uncertainty_basis" in res
        assert "vertical resolution" in res["uncertainty_basis"] or "sample returns" in res["uncertainty_basis"]
        assert res["uncertainty_type"] == "DERIVED_STATISTICAL"
        assert res["uncertainty_m"] > 0.0
        assert "Z95" in res["method"]
        assert "ASPRS" in res["method"]

    def test_las_clipping_non_covering_footprint_rejection(self):
        """DEMO B: Pune parcel outside LAS extent triggers EVIDENCE_NOT_COVERING_TARGET (Critical Rule 2)."""
        res = PointCloudPreprocessor.clip_pointcloud_to_footprint(
            las_source=LAS_FILE_PATH,
            footprint_geojson=PUNE_DEMO_FOOTPRINT,
            source_crs="EPSG:32643",
            target_crs="EPSG:4326"
        )
        assert res["status"] == "EVIDENCE_NOT_COVERING_TARGET"
        assert res["coverage"] == "NOT_COVERING_TARGET"
        assert res["spatial_relation"] == "NO_BOUNDS_OVERLAP"
        assert res.get("height_m") is None
        assert "do not overlap" in res["explanation"].lower()


class TestRasterPreprocessing:
    """Tests for DEM/DSM raster inspection and elevation difference processing."""

    def test_dem_numpy_inspection(self):
        assert os.path.exists(DEM_NPY_PATH), f"DEM numpy grid not found at {DEM_NPY_PATH}"
        meta = RasterPreprocessor.inspect_raster(DEM_NPY_PATH)
        assert meta["status"] in ("NUMPY_ARRAY_READ", "VALID_RASTER")
        assert meta["width"] == 512
        assert meta["height"] == 512
        stats = meta.get("elevation_statistics", {})
        assert stats["min_m"] < stats["max_m"]

    def test_dsm_dtm_difference_calculation(self):
        """Computes height from synthetic DSM and DTM elevation statistics."""
        dsm_info = {
            "elevation_statistics": {"max_m": 584.5},
            "spatial_resolution_m": 0.5
        }
        dtm_info = {
            "elevation_statistics": {"min_m": 560.0},
            "spatial_resolution_m": 0.5
        }
        diff_res = RasterPreprocessor.compute_height_difference(dsm_info, dtm_info)
        assert diff_res["status"] == "CALCULATED"
        assert pytest.approx(diff_res["height_m"], abs=0.1) == 24.5
        assert diff_res["ground_elevation_m"] == 560.0
        assert diff_res["top_elevation_m"] == 584.5
        # Uncertainty should be derived from raster resolution
        assert diff_res["uncertainty_type"] == "DERIVED_FROM_RESOLUTION"
        assert "0.5m" in diff_res["uncertainty_basis"]


class TestHeightEstimatorCascade:
    """Tests that HeightEstimatorModel gives strict precedence to valid LiDAR over neural regressor."""

    def test_lidar_precedence_over_onnx(self):
        model = HeightEstimatorModel()
        pred = model.predict({
            "point_cloud_path": LAS_FILE_PATH,
            "footprint_geojson": VALID_LAS_WGS84_FOOTPRINT,
            "total_height_m": None  # No explicit height
        })
        assert pred["status"] == "SUCCESS"
        assert pred["source"] == EvidenceSourceType.POINT_CLOUD
        assert pred["provenance"] == "OBSERVED_LIDAR"
        assert pred["coverage"] == "VALID"
        assert "Z95" in pred["method"]
        assert pred["height_m"] > 0.0

    def test_non_covering_lidar_graceful_audit_and_fallback(self):
        model = HeightEstimatorModel()
        # Feed Pune footprint with LAS file and explicit fallback height
        pred = model.predict({
            "point_cloud_path": LAS_FILE_PATH,
            "footprint_geojson": PUNE_DEMO_FOOTPRINT,
            "total_height_m": 18.0  # Explicit fallback height
        })
        assert pred["status"] == "SUCCESS"
        # Must NOT be POINT_CLOUD because LiDAR did not cover Pune
        assert pred["source"] != EvidenceSourceType.POINT_CLOUD
        # Check that rejection was recorded in the audit trail
        if "evidence_audit" in pred:
            audit = pred["evidence_audit"]
            assert any(a.get("source") == "POINT_CLOUD" for a in audit)


class TestFeatureExtractionPipeline:
    """Tests the full FeatureExtractionPipeline with LiDAR inputs."""

    def test_pipeline_with_covering_lidar(self):
        pipeline = FeatureExtractionPipeline()
        result = pipeline.process({
            "footprint_geojson": VALID_LAS_WGS84_FOOTPRINT,
            "point_cloud_path": LAS_FILE_PATH,
            "source_type": "POINT_CLOUD",
            "source_reference": "sample_pointcloud.las"
        })
        assert result.status == "SUCCESS"
        assert result.features is not None
        assert result.features.height_m > 0.0
        assert len(result.vertical_proposals) > 0
        # Check height provenance
        height_prov = next((p for p in result.provenance if "HEIGHT" in p.source_id), None)
        assert height_prov is not None
        assert height_prov.source_type == EvidenceSourceType.POINT_CLOUD
        assert height_prov.coverage == "VALID"
        assert height_prov.uncertainty_basis is not None


class TestEndToEndCadastralOrchestrator:
    """Tests end-to-end asynchronous cadastral orchestration with LiDAR evidence."""

    def test_e2e_covering_lidar_job(self, db_session):
        """DEMO A: Complete pipeline run for footprint covered by LAS."""
        db = db_session
        job = JobManager.create_job(
            db=db,
            job_type=JobType.END_TO_END_PARCEL_PROCESS.value,
            entity_type="PARCEL",
            source_metadata={"survey_number": "SURVEY-LIDAR-TEST-001"}
        )
        CadastralProcessingOrchestrator.run_end_to_end_parcel_processing(
            db=db,
            job_id=job.job_id,
            payload={
                "survey_number": "SURVEY-LIDAR-TEST-001",
                "state_code": "27",
                "district_code": "PUN",
                "parcel_geojson": VALID_LAS_WGS84_FOOTPRINT,
                "building_footprint_geojson": VALID_LAS_WGS84_BUILDING,
                "units_per_floor": 2,
                "auto_generate_strata": True,
                "source_evidence": {
                    "source_type": "POINT_CLOUD",
                    "source_reference": LAS_FILE_PATH
                }
            }
        )
        job = JobManager.get_job(db, job.job_id)
        assert str(job.status) == "COMPLETED"
        assert str(job.current_stage) == "COMPLETED"
        assert job.progress_percent == 100.0

        result = job.result_reference
        assert result is not None
        assert result["floors_count"] > 0
        assert result["units_count"] > 0
        assert len(result["unit_ulpins"]) > 0

        # Inspect digital twin provenance
        dt = DigitalTwinService.assemble_digital_twin(db, result["parcel_id"])
        assert len(dt.parcel.buildings) > 0
        bld = dt.parcel.buildings[0]
        assert bld.ml_provenance is not None
        assert bld.ml_provenance.get("height_source") == "POINT_CLOUD"
        assert "Z95" in bld.ml_provenance.get("height_method", "")

        # Check unit-level provenance
        assert len(bld.floors) > 0
        unit = bld.floors[0].units[0]
        assert unit.ml_provenance is not None
        assert unit.ml_provenance.get("source") == "POINT_CLOUD"
        assert unit.ml_provenance.get("coverage") == "VALID"
        assert unit.ml_provenance.get("uncertainty_basis") is not None

    def test_e2e_pune_parcel_lidar_clean_fallback(self, db_session):
        """DEMO B: Complete pipeline run for Pune parcel rejecting out-of-bounds LAS cleanly."""
        db = db_session
        job = JobManager.create_job(
            db=db,
            job_type=JobType.END_TO_END_PARCEL_PROCESS.value,
            entity_type="PARCEL",
            source_metadata={"survey_number": "SURVEY-PUNE-LIDAR-FALLBACK-002"}
        )
        CadastralProcessingOrchestrator.run_end_to_end_parcel_processing(
            db=db,
            job_id=job.job_id,
            payload={
                "survey_number": "SURVEY-PUNE-LIDAR-FALLBACK-002",
                "state_code": "27",
                "district_code": "PUN",
                "parcel_geojson": PUNE_DEMO_FOOTPRINT,
                "total_height_m": 24.0,
                "floor_count": 6,
                "basement_count": 1,
                "units_per_floor": 2,
                "auto_generate_strata": True,
                "source_evidence": {
                    "source_type": "POINT_CLOUD",
                    "source_reference": LAS_FILE_PATH
                }
            }
        )
        job = JobManager.get_job(db, job.job_id)
        assert str(job.status) == "COMPLETED"
        result = job.result_reference
        assert result is not None
        # Verified that job completes cleanly with registered survey fallback
        assert result["floors_count"] == 7  # 6 floors + 1 basement
        assert result["units_count"] == 14  # 7 * 2

        dt = DigitalTwinService.assemble_digital_twin(db, result["parcel_id"])
        bld = dt.parcel.buildings[0]
        # Height source should have fallen back to metadata, NOT fake POINT_CLOUD
        assert bld.ml_provenance is not None
        assert bld.ml_provenance.get("height_source") != "POINT_CLOUD"
