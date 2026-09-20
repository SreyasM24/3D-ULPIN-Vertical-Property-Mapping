"""
FastAPI Application Entrypoint: 3D ULPIN & Vertical Property Mapping System.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import logger
from app.core.middleware import CorrelationIdMiddleware
from app.core.exceptions import (
    CadastreException,
    cadastre_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)
from app.db.session import init_db, get_db
from app.api.v1.router import api_v1_router
from app.schemas.common import APIResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown routines."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION} [{settings.APP_ENV}]")
    # Initialize database tables
    init_db()
    logger.info("Application startup completed successfully.")
    yield
    logger.info("Application shutdown completed.")


def create_application() -> FastAPI:
    """Factory function for FastAPI application."""
    tags_metadata = [
        {"name": "Health & Status", "description": "Liveness, readiness, and system metadata probes."},
        {"name": "2D Cadastral Parcels", "description": "2D Land parcels, base ULPIN generation, and geodetic areas."},
        {"name": "Buildings & Structures", "description": "Physical structures situated on parcels with vertical limits."},
        {"name": "Floor Levels & Strata", "description": "Vertical floor slices and elevation strata management."},
        {"name": "3D Vertical Units & Volumetric Cadastre", "description": "3D Units, Prototype 3D ULPIN derivation, and 3D volume calculations."},
        {"name": "3D Spatial Analysis & GeoJSON 3D", "description": "Volumetric collision/clash detection and 3D GeoJSON export for web visualizers."},
        {"name": "Record of Rights (RoR) & Ownership", "description": "Ownership title registration, share validation, and encumbrance tracking."},
        {"name": "Cadastral Validation & Topology Engine", "description": "Deterministic rule-based validation, 3D clash audit, explainable quality scoring, and audit history."},
        {"name": "ML/AI-Assisted 3D Feature Extraction Engine", "description": "Remote-sensing inspection, multi-strategy height and floor estimation, and vertical feature proposal."},
        {"name": "Asynchronous Cadastral Orchestration & Ingestion Jobs", "description": "Non-blocking background survey ingestion, stage tracking, cancellation, and job results."},
        {"name": "Unified Cadastral Processing Entrypoints", "description": "Convenience async processing pipelines for 3D land parcels and digital twin generation."},
    ]

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Backend Foundation for Smart India Hackathon (SIH 26011): "
            "3D ULPIN Generation and Vertical Property Mapping System. "
            "Extends 2D Bhu-Aadhaar cadastre into multi-dimensional volumetric cadastre."
        ),
        version=settings.VERSION,
        openapi_tags=tags_metadata,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 1. Register Middlewares
    app.add_middleware(CorrelationIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Register Centralized Exception Handlers
    app.add_exception_handler(CadastreException, cadastre_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # 3. Register Root Health / Info Route
    @app.get("/", response_model=APIResponse[dict], status_code=status.HTTP_200_OK, tags=["Root"])
    def root_info():
        return APIResponse(
            data={
                "name": settings.APP_NAME,
                "version": settings.VERSION,
                "docs_url": "/docs",
                "api_v1": settings.API_V1_STR,
                "ulpin_specification": "SIH 26011 Prototype Specification (Vertical Cadastre)"
            }
        )

    @app.get("/health", response_model=APIResponse[dict], status_code=status.HTTP_200_OK, tags=["Root"])
    def root_health():
        return APIResponse(
            success=True,
            data={
                "status": "healthy",
                "app_name": settings.APP_NAME,
                "version": settings.VERSION,
                "environment": settings.APP_ENV,
            }
        )

    @app.get("/readiness", response_model=APIResponse[dict], status_code=status.HTTP_200_OK, tags=["Root"])
    def root_readiness(response: Response, db: Session = Depends(get_db)):
        db_ok = False
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False

        if not db_ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return APIResponse(
            success=db_ok,
            data={
                "status": "ready" if db_ok else "unready",
                "database_connected": db_ok,
                "app_name": settings.APP_NAME,
                "version": settings.VERSION,
            }
        )

    # 4. Mount API v1 Routers
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    return app


app = create_application()
