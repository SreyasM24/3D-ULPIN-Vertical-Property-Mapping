"""
API v1 Router for Asynchronous Jobs and Cadastral Processing Orchestration.
Provides non-blocking endpoints for dataset ingestion, end-to-end parcel processing,
real-time status polling, cancellation, and result retrieval.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.jobs.models import ProcessingJob
from app.jobs.schemas import (
    JobRead,
    JobListResponse,
    JobResultResponse,
    JobStatus,
    JobStage,
    JobType,
    SurveyIngestJobRequest,
    ParcelProcessJobRequest,
)
from app.jobs.manager import JobManager
from app.jobs.executor import JobExecutor
from app.jobs.orchestrator import CadastralProcessingOrchestrator
from app.schemas.common import APIResponse
from app.core.exceptions import EntityNotFoundException, CadastreException


router = APIRouter(prefix="/jobs", tags=["Asynchronous Cadastral Orchestration & Ingestion Jobs"])


def _to_job_read(job: ProcessingJob) -> JobRead:
    duration = None
    if job.started_at and job.completed_at:
        duration = (job.completed_at - job.started_at).total_seconds()

    return JobRead(
        job_id=job.job_id,
        job_type=job.job_type,
        request_id=job.request_id,
        status=JobStatus(job.status),
        current_stage=JobStage(job.current_stage),
        progress_percent=job.progress_percent,
        entity_type=job.entity_type,
        entity_id=job.entity_id,
        source_filename=job.source_filename,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=duration,
        stage_details=job.stage_details or {},
        error_message=job.error_message,
        tracking_url=f"/api/v1/jobs/{job.job_id}"
    )


@router.post("/ingestion", response_model=APIResponse[JobRead], status_code=status.HTTP_202_ACCEPTED)
def submit_survey_ingestion_job(
    request: SurveyIngestJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Submits a survey dataset (GeoJSON, LiDAR, DEM/DSM raster, Drone imagery, CAD)
    for asynchronous ingestion, geometric normalization, and audit.
    Returns immediately with HTTP 202 Accepted and job tracking details.
    """
    # Check for active duplicate job (Idempotency)
    active_job = JobManager.find_active_job(
        db=db,
        job_type=JobType.SURVEY_INGESTION.value,
        source_filename=request.source_filename
    )
    if active_job:
        return APIResponse(
            data=_to_job_read(active_job),
            message="An active ingestion job for this dataset already exists."
        )

    from app.core.logging import correlation_id_ctx
    req_id = correlation_id_ctx.get()

    job = JobManager.create_job(
        db=db,
        job_type=JobType.SURVEY_INGESTION.value,
        entity_type="DATASET",
        source_filename=request.source_filename,
        request_id=req_id,
        source_metadata={
            "source_type": request.source_type,
            "source_crs": request.source_crs,
            "metadata": request.metadata
        }
    )

    JobExecutor.dispatch(
        background_tasks,
        CadastralProcessingOrchestrator.run_survey_ingestion_job,
        job.job_id,
        payload=request.model_dump()
    )

    return APIResponse(
        data=_to_job_read(job),
        message="Survey ingestion job queued successfully."
    )


@router.post("/process-parcel", response_model=APIResponse[JobRead], status_code=status.HTTP_202_ACCEPTED)
def submit_parcel_processing_job(
    request: ParcelProcessJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Submits an end-to-end 3D cadastral processing job for a parcel:
    Footprint inspection -> ML feature extraction -> 3D Building & Floor strata ->
    3D ULPIN generation -> Deterministic validation -> Digital twin assembly.
    Returns immediately with HTTP 202 Accepted.
    """
    # Check for active duplicate job (Idempotency)
    active_job = None
    if request.parcel_id:
        active_job = JobManager.find_active_job(
            db=db,
            job_type=JobType.END_TO_END_PARCEL_PROCESS.value,
            entity_id=request.parcel_id
        )
    if active_job:
        return APIResponse(
            data=_to_job_read(active_job),
            message="An active processing job for this parcel already exists."
        )

    from app.core.logging import correlation_id_ctx
    req_id = correlation_id_ctx.get()

    job = JobManager.create_job(
        db=db,
        job_type=JobType.END_TO_END_PARCEL_PROCESS.value,
        entity_type="PARCEL",
        entity_id=request.parcel_id,
        request_id=req_id,
        source_metadata={
            "survey_number": request.survey_number,
            "state_code": request.state_code,
            "units_per_floor": request.units_per_floor,
            "auto_generate_strata": request.auto_generate_strata
        }
    )

    JobExecutor.dispatch(
        background_tasks,
        CadastralProcessingOrchestrator.run_end_to_end_parcel_processing,
        job.job_id,
        payload=request.model_dump()
    )

    return APIResponse(
        data=_to_job_read(job),
        message="End-to-end parcel processing job queued successfully."
    )


@router.get("/{job_id}", response_model=APIResponse[JobRead])
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Retrieves current execution status, stage, and progress percentage for a job."""
    job = JobManager.get_job(db, job_id)
    if not job:
        raise EntityNotFoundException("ProcessingJob", job_id)
    return APIResponse(data=_to_job_read(job))


@router.get("", response_model=APIResponse[JobListResponse])
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status: QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    entity_id: Optional[str] = Query(None, description="Filter by associated entity UUID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Lists processing jobs with optional filters and pagination."""
    jobs, total = JobManager.list_jobs(
        db=db,
        status=status,
        job_type=job_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset
    )
    job_reads = [_to_job_read(j) for j in jobs]
    return APIResponse(
        data=JobListResponse(jobs=job_reads, total=total, limit=limit, offset=offset)
    )


@router.post("/{job_id}/cancel", response_model=APIResponse[JobRead])
def cancel_job(
    job_id: str,
    reason: str = Query("Cancelled by user", description="Reason for cancellation"),
    db: Session = Depends(get_db)
):
    """Cancels a QUEUED or RUNNING job."""
    job = JobManager.get_job(db, job_id)
    if not job:
        raise EntityNotFoundException("ProcessingJob", job_id)
    updated_job = JobManager.cancel_job(db, job_id, reason=reason)
    return APIResponse(data=_to_job_read(updated_job), message="Job cancelled successfully.")


@router.get("/{job_id}/result", response_model=APIResponse[JobResultResponse])
def get_job_result(job_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the completed job results, derived 3D ULPINs, validation quality score,
    and digital twin links.
    """
    job = JobManager.get_job(db, job_id)
    if not job:
        raise EntityNotFoundException("ProcessingJob", job_id)

    if job.status != JobStatus.COMPLETED.value:
        raise CadastreException(
            f"Job {job_id} has not completed yet. Current status: {job.status} ({job.progress_percent}%)"
        )

    res = job.result_reference or {}
    parcel_id = res.get("parcel_id") or job.entity_id

    result_payload = JobResultResponse(
        job_id=job.job_id,
        status=JobStatus(job.status),
        job_type=job.job_type,
        entity_type=job.entity_type,
        entity_id=parcel_id,
        quality_score=res.get("quality_score"),
        quality_grade=res.get("quality_grade"),
        is_valid=res.get("is_valid"),
        created_entities={
            "parcel_id": res.get("parcel_id"),
            "parcel_ulpin": res.get("parcel_ulpin"),
            "building_id": res.get("building_id"),
            "building_code": res.get("building_code"),
            "floors_count": res.get("floors_count"),
            "units_count": res.get("units_count"),
            "unit_ulpins": res.get("unit_ulpins", [])
        },
        validation_summary={
            "validation_run_id": res.get("validation_run_id"),
            "quality_score": res.get("quality_score"),
            "quality_grade": res.get("quality_grade"),
            "is_valid": res.get("is_valid")
        },
        digital_twin_url=f"/api/v1/parcels/{parcel_id}/digital-twin" if parcel_id else None,
        anomalies=res.get("anomalies", []),
        artifacts=res
    )

    return APIResponse(data=result_payload)
