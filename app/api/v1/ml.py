"""
FastAPI Router for ML/AI-Assisted 3D Feature Extraction Engine.
Provides endpoints for capability detection, remote-sensing inspection,
multi-strategy estimation, and vertical feature proposals.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.schemas.common import APIResponse
from app.ml.schemas import (
    MLCapability,
    BuildingFeatureResult,
    VerticalFeatureResult,
    AnomalyResult,
    PipelineResult,
    EvidenceSourceType,
)
from app.ml.preprocessing.pointcloud import PointCloudPreprocessor
from app.ml.preprocessing.raster import RasterPreprocessor
from app.ml.models.building_detector import BuildingDetector
from app.ml.models.height_estimator import HeightEstimatorModel
from app.ml.models.floor_estimator import FloorEstimatorModel
from app.ml.models.anomaly_detector import CadastralMLAnomalyDetector
from app.core.exceptions import CadastreException
from app.ml.features.building_features import BuildingFeatureExtractor
from app.ml.features.height_features import HeightFeatureExtractor
from app.ml.features.floor_features import FloorFeatureExtractor
from app.ml.features.vertical_features import VerticalFeatureExtractor
from app.ml.pipelines.vertical_cadastre import VerticalCadastreFeatureService
from app.ml.pipelines.feature_extraction import FeatureExtractionPipeline

router = APIRouter(prefix="/ml", tags=["ML/AI-Assisted 3D Feature Extraction Engine"])


# ---------------------------------------------------------------------------
# Request Schemas for ML Endpoints
# ---------------------------------------------------------------------------

class PointCloudInspectRequest(BaseModel):
    source: Dict[str, Any] = Field(..., description="LiDAR metadata dict or file path specification")


class RasterInspectRequest(BaseModel):
    dsm: Optional[Dict[str, Any]] = None
    dtm: Optional[Dict[str, Any]] = None
    single_raster: Optional[Dict[str, Any]] = None


class BuildingExtractRequest(BaseModel):
    footprint_geojson: Optional[Dict[str, Any]] = None
    image_path: Optional[str] = None
    height_m: Optional[float] = None
    floor_count: Optional[int] = None
    source_type: EvidenceSourceType = EvidenceSourceType.BUILDING_METADATA


class HeightEstimateRequest(BaseModel):
    dsm_metadata: Optional[Dict[str, Any]] = None
    dtm_metadata: Optional[Dict[str, Any]] = None
    pointcloud_metadata: Optional[Dict[str, Any]] = None
    building_metadata: Optional[Dict[str, Any]] = None
    footprint_geojson: Optional[Dict[str, Any]] = None
    total_height_m: Optional[float] = None
    floors_above_ground: Optional[int] = None
    floor_count: Optional[int] = None
    ground_elevation_m: Optional[float] = 0.0


class FloorEstimateRequest(BaseModel):
    height_m: Optional[float] = None
    total_height_m: Optional[float] = None
    ground_elevation_m: float = 0.0
    floors_above_ground: Optional[int] = None
    basement_floors: int = 0
    floors: Optional[List[Dict[str, Any]]] = None


class VerticalProposeRequest(BaseModel):
    footprint_geojson: Dict[str, Any]
    ground_elevation_m: float = 0.0
    total_height_m: float
    strata_levels: List[VerticalFeatureResult]
    units_per_floor: int = 2
    building_code: str = "BLD-PROP"


class AnomalyCheckRequest(BaseModel):
    height_m: Optional[float] = None
    floor_count: Optional[int] = None
    footprint_geojson: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health", response_model=APIResponse[Dict[str, Any]])
def get_ml_subsystem_health():
    """Returns runtime readiness and health probes for all ML model adapters and sensor pipelines."""
    import os
    # 1. Model Probes
    models = [
        BuildingDetector(),
        HeightEstimatorModel(),
        FloorEstimatorModel(),
        CadastralMLAnomalyDetector(),
    ]
    model_probes = [m.health() for m in models]
    
    # 2. Runtime Probe for Point Cloud Inspection
    las_probe = {"status": "UNAVAILABLE", "details": "No sample LAS artifact found."}
    las_sample_path = "data/ml/raw/lidar/sample_pointcloud.las"
    if os.path.exists(las_sample_path):
        las_insp = PointCloudPreprocessor.inspect_pointcloud(las_sample_path)
        if las_insp.get("status") == "HEADER_READ":
            las_probe = {
                "status": "OPERATIONAL",
                "backend": "LASPY",
                "point_count": las_insp.get("point_count"),
                "crs": las_insp.get("horizontal_crs"),
                "sample_artifact": os.path.basename(las_sample_path)
            }
        else:
            las_probe = {"status": "DEGRADED", "error": las_insp.get("error")}

    # 3. Runtime Probe for Raster Inspection
    raster_probe = {"status": "UNAVAILABLE", "details": "No DEM/DSM raster artifact found."}
    raster_sample_path = "data/ml/processed/elevation_profiles/usgs_3dep_dem_patch_512x512.npy"
    if os.path.exists(raster_sample_path):
        dem_insp = RasterPreprocessor.inspect_raster(raster_sample_path)
        if dem_insp.get("status") == "NUMPY_ARRAY_READ":
            raster_probe = {
                "status": "OPERATIONAL",
                "backend": "NUMPY_RASTER_PARSER",
                "model_type": dem_insp.get("model_type"),
                "dimensions": f"{dem_insp.get('width')}x{dem_insp.get('height')}",
                "spatial_resolution_m": dem_insp.get("spatial_resolution_m"),
                "crs": dem_insp.get("horizontal_crs"),
                "sample_artifact": os.path.basename(raster_sample_path)
            }
        else:
            raster_probe = {"status": "DEGRADED", "error": dem_insp.get("error")}

    # 4. Runtime Probe for Observed LiDAR Height Extraction
    lidar_height_probe = {"status": "UNAVAILABLE"}
    if las_probe.get("status") == "OPERATIONAL":
        test_bld = {
            "type": "Polygon",
            "coordinates": [[
                [76.2404, 7.6952],
                [76.2440, 7.6952],
                [76.2440, 7.6988],
                [76.2404, 7.6988],
                [76.2404, 7.6952]
            ]]
        }
        clip_probe = PointCloudPreprocessor.clip_pointcloud_to_footprint(
            las_sample_path, test_bld, source_crs="EPSG:32643", target_crs="EPSG:4326"
        )
        if clip_probe.get("status") == "VALID_OBSERVED_EVIDENCE":
            lidar_height_probe = {
                "status": "OPERATIONAL",
                "method": clip_probe.get("method"),
                "verified_observed_height_m": clip_probe.get("height_m"),
                "uncertainty_m": clip_probe.get("uncertainty_m"),
                "coverage_check": "VERIFIED_SPATIAL_INTERSECTION"
            }
        else:
            lidar_height_probe = {"status": "DEGRADED", "details": clip_probe.get("explanation")}

    all_models_ready = all(p["status"] in ("ACTIVE", "DEGRADED") for p in model_probes)
    all_ready = all_models_ready and las_probe.get("status") == "OPERATIONAL" and raster_probe.get("status") == "OPERATIONAL"

    return APIResponse(
        data={
            "subsystem": "ML_FEATURE_EXTRACTION",
            "status": "OPERATIONAL" if all_ready else "DEGRADED",
            "models": model_probes,
            "sensors": {
                "point_cloud_inspection": las_probe,
                "raster_inspection": raster_probe,
                "observed_lidar_height": lidar_height_probe
            }
        }
    )


@router.get("/capabilities", response_model=APIResponse[MLCapability])
def get_ml_capabilities():
    """
    Discovers available runtime acceleration libraries (PDAL, Open3D, Rasterio, laspy, PyTorch, ONNX).
    Ensures graceful degradation without requiring heavyweight native libraries.
    """
    pc_caps = PointCloudPreprocessor.get_capabilities()
    rast_caps = RasterPreprocessor.get_capabilities()

    # Check torch
    try:
        import torch
        has_torch = True
    except ImportError:
        has_torch = False

    # Check onnx
    try:
        import onnx
        has_onnx = True
    except ImportError:
        has_onnx = False

    notes = []
    if not pc_caps["has_laspy"]:
        notes.append("laspy not installed: binary LAS parsing runs in metadata mode.")
    if not rast_caps["has_rasterio"]:
        notes.append("rasterio not installed: raster processing runs in metadata mode.")
    if not has_torch:
        notes.append("PyTorch not installed: deep learning models default to NOT_CONFIGURED fallback.")

    caps = MLCapability(
        has_pdal=pc_caps["has_pdal"],
        has_open3d=pc_caps["has_open3d"],
        has_rasterio=rast_caps["has_rasterio"],
        has_laspy=pc_caps["has_laspy"],
        has_torch=has_torch,
        has_onnx=has_onnx,
        hardware_acceleration="CPU",
        notes=notes
    )
    return APIResponse(data=caps)


@router.get("/models", response_model=APIResponse[List[Dict[str, Any]]])
def list_ml_models():
    """Lists registered AI/ML models, versioning, and configuration states."""
    models = [
        BuildingDetector(),
        HeightEstimatorModel(),
        FloorEstimatorModel(),
        CadastralMLAnomalyDetector(),
    ]
    return APIResponse(data=[m.metadata() for m in models])


@router.post("/pointcloud/inspect", response_model=APIResponse[Dict[str, Any]])
def inspect_pointcloud(payload: PointCloudInspectRequest):
    """Inspects LiDAR LAS/LAZ metadata, point count, spatial bounds, and ground/canopy elevation."""
    parsed = PointCloudPreprocessor.inspect_pointcloud(payload.source)
    if parsed.get("status") in ("METADATA_EXTRACTED", "HEADER_READ"):
        elev_stats = PointCloudPreprocessor.estimate_ground_and_surface(parsed)
        parsed["elevation_estimates"] = elev_stats
    return APIResponse(data=parsed)


@router.post("/raster/inspect", response_model=APIResponse[Dict[str, Any]])
def inspect_raster(payload: RasterInspectRequest):
    """Inspects elevation raster metadata (DEM/DSM/DTM) and calculates building height via DSM - DTM."""
    results = {}
    if payload.single_raster:
        results["single_raster"] = RasterPreprocessor.inspect_raster(payload.single_raster)

    if payload.dsm and payload.dtm:
        dsm_meta = RasterPreprocessor.inspect_raster(payload.dsm)
        dtm_meta = RasterPreprocessor.inspect_raster(payload.dtm)
        height_diff = RasterPreprocessor.compute_height_difference(dsm_meta, dtm_meta)
        results["dsm"] = dsm_meta
        results["dtm"] = dtm_meta
        results["height_difference"] = height_diff

    return APIResponse(data=results)


@router.post("/building/extract", response_model=APIResponse[BuildingFeatureResult])
def extract_building_features(payload: BuildingExtractRequest):
    """Extracts projected metric area, perimeter, footprint, and volume from building geometry or detected from imagery."""
    footprint = payload.footprint_geojson
    source_type = payload.source_type
    confidence = 0.90
    uncertainty_m = 0.2

    if payload.image_path:
        detector = BuildingDetector()
        detection = detector.predict(image_path=payload.image_path)
        footprint = detection.footprint_geojson
        source_type = detection.source
        confidence = detection.confidence
        uncertainty_m = detection.uncertainty_m

    if not footprint:
        raise CadastreException("Either footprint_geojson or image_path must be provided.")

    res = BuildingFeatureExtractor.extract_features(
        footprint_geojson=footprint,
        height_m=payload.height_m,
        floor_count=payload.floor_count,
        source_type=source_type,
        confidence=confidence,
        uncertainty_m=uncertainty_m
    )
    return APIResponse(data=res)


@router.post("/building/height", response_model=APIResponse[Dict[str, Any]])
def estimate_building_height(payload: HeightEstimateRequest):
    """
    Executes multi-strategy height estimation in deterministic priority:
    DSM_DTM -> POINT_CLOUD -> BUILDING_METADATA -> FLOOR_COUNT_FALLBACK -> UNKNOWN
    """
    res = HeightFeatureExtractor.extract_height(payload.model_dump())
    return APIResponse(data=res)


@router.post("/building/floors", response_model=APIResponse[Dict[str, Any]])
def estimate_building_floors(payload: FloorEstimateRequest):
    """Decomposes building vertical envelope into candidate floor strata."""
    res = FloorFeatureExtractor.extract_floors(payload.model_dump())
    return APIResponse(data=res)


@router.post("/vertical/propose", response_model=APIResponse[Dict[str, Any]])
def propose_vertical_cadastre(payload: VerticalProposeRequest):
    """
    Generates candidate floor strata and vertical property units,
    and runs deterministic floor consistency validation.
    """
    candidate_cadastre = VerticalCadastreFeatureService.generate_candidate_cadastre(
        footprint_geojson=payload.footprint_geojson,
        ground_elevation_m=payload.ground_elevation_m,
        total_height_m=payload.total_height_m,
        strata_levels=payload.strata_levels,
        units_per_floor=payload.units_per_floor,
        building_code=payload.building_code
    )
    return APIResponse(data=candidate_cadastre)


@router.post("/anomalies", response_model=APIResponse[List[AnomalyResult]])
def check_cadastral_anomalies(payload: AnomalyCheckRequest):
    """Scans building properties for statistical, structural, and height anomalies."""
    detector = CadastralMLAnomalyDetector()
    results = detector.predict(payload.model_dump())
    return APIResponse(data=results)


@router.post("/pipeline/extract-all", response_model=APIResponse[PipelineResult])
def run_feature_extraction_pipeline(inputs: Dict[str, Any]):
    """
    Executes the end-to-end ML/AI Feature Extraction Pipeline:
    Source inspection -> Preprocessing -> Height estimation -> Floor decomposition ->
    Confidence calibration -> Verification handoff.
    """
    pipeline = FeatureExtractionPipeline()
    res = pipeline.process(inputs)
    return APIResponse(data=res)
