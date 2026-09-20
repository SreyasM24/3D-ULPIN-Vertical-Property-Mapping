from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.parcels import router as parcels_router
from app.api.v1.buildings import router as buildings_router
from app.api.v1.floors import router as floors_router
from app.api.v1.units import router as units_router
from app.api.v1.spatial import router as spatial_router
from app.api.v1.ownership import router as ownership_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.validation import router as validation_router
from app.api.v1.ml import router as ml_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.process import router as process_router
from app.api.v1.temporal import router as temporal_router

api_v1_router = APIRouter()

api_v1_router.include_router(health_router)
api_v1_router.include_router(parcels_router)
api_v1_router.include_router(buildings_router)
api_v1_router.include_router(floors_router)
api_v1_router.include_router(units_router)
api_v1_router.include_router(spatial_router)
api_v1_router.include_router(ownership_router)
api_v1_router.include_router(ingestion_router)
api_v1_router.include_router(validation_router)
api_v1_router.include_router(ml_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(process_router)
api_v1_router.include_router(temporal_router)
