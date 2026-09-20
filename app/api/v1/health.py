from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.core.config import settings
from app.schemas.common import APIResponse

router = APIRouter(tags=["Health & Status"])


@router.get("/health", response_model=APIResponse[dict], status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    """
    Health / Liveness probe.
    Verifies service process and database connectivity.
    """
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    data = {
        "status": "healthy" if db_ok else "degraded",
        "app_name": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.APP_ENV,
        "database_connected": db_ok,
        "ulpin_spec": {
            "status": settings.ULPIN_SPEC_STATUS,
            "description": "Prototype 3D ULPIN generation aligned with SIH 26011"
        }
    }
    return APIResponse(success=db_ok, data=data)


@router.get("/readiness", response_model=APIResponse[dict], status_code=status.HTTP_200_OK)
def readiness_check(response: Response, db: Session = Depends(get_db)):
    """
    Readiness probe.
    Verifies database connectivity and readiness to accept incoming traffic.
    Returns 200 OK when ready or 503 Service Unavailable when degraded.
    """
    db_ok = False
    error_detail = None
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_ok = False
        error_detail = str(exc)

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    data = {
        "status": "ready" if db_ok else "unready",
        "database_connected": db_ok,
        "app_name": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.APP_ENV,
        "error": error_detail,
        "ulpin_spec": {
            "status": settings.ULPIN_SPEC_STATUS,
            "description": "Prototype 3D ULPIN generation aligned with SIH 26011"
        }
    }
    return APIResponse(success=db_ok, data=data)


@router.get("/capabilities", response_model=APIResponse[dict], status_code=status.HTTP_200_OK)
def system_capabilities():
    """
    System capabilities summary.
    Discloses supported cadastral engines, ML pipelines, ingestion formats, and validation features.
    """
    data = {
        "app_name": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.APP_ENV,
        "specification": "SIH 26011 Prototype Specification (Vertical Cadastre)",
        "capabilities": {
            "cadastre_2d": {
                "supported": True,
                "features": ["parcel_polygon", "projected_metrics", "wgs84_normalization", "bhu_aadhaar_ulpin_2d"]
            },
            "cadastre_3d": {
                "supported": True,
                "features": [
                    "multi_strata_floors",
                    "vertical_units",
                    "prototype_ulpin_3d",
                    "prism_volumetric_calculation",
                    "geojson_3d_features"
                ]
            },
            "validation_engine": {
                "supported": True,
                "features": [
                    "deterministic_rule_audit",
                    "3d_volumetric_clash_detection",
                    "explainable_quality_score",
                    "quality_grades_A_B_C_D"
                ]
            },
            "ml_feature_extraction": {
                "supported": True,
                "is_authoritative": False,
                "pipeline": "FeatureExtractionPipeline",
                "features": [
                    "footprint_height_estimation",
                    "vertical_strata_proposal",
                    "lidar_point_cloud_inspection",
                    "raster_dem_elevation_extraction"
                ]
            },
            "async_orchestration": {
                "supported": True,
                "features": [
                    "background_task_execution",
                    "job_state_machine",
                    "stage_progress_tracking",
                    "idempotency_guard",
                    "transactional_rollback_cleanup"
                ]
            },
            "digital_twin": {
                "supported": True,
                "features": ["volumetric_summary", "3d_geojson_assembly", "spatial_unit_registry"]
            }
        }
    }
    return APIResponse(success=True, data=data)

