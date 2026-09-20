"""
Job Manager: State machine and database persistence layer for Processing Jobs.
Enforces valid state transitions, stage event logs, and job idempotency.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from app.jobs.models import ProcessingJob
from app.jobs.schemas import JobStatus, JobStage
from app.core.exceptions import EntityNotFoundException, CadastreException
from app.core.logging import logger


TERMINAL_STATUSES = {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}


def _calc_duration(start: Optional[datetime], end: Optional[datetime] = None) -> float:
    """Calculate elapsed duration in seconds, safely handling tz-naive and tz-aware datetimes."""
    if not start:
        return 0.0
    if end is None:
        end = datetime.now(timezone.utc)
    if start.tzinfo is None and end.tzinfo is not None:
        start = start.replace(tzinfo=timezone.utc)
    elif start.tzinfo is not None and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0.0, (end - start).total_seconds())


class JobManager:
    """Manages transactional lifecycle and state transitions of asynchronous jobs."""

    @staticmethod
    def create_job(
        db: Session,
        job_type: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        source_filename: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
        initial_stage: str = JobStage.QUEUED.value,
        request_id: Optional[str] = None,
    ) -> ProcessingJob:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        if not request_id:
            from app.core.logging import correlation_id_ctx
            request_id = correlation_id_ctx.get()

        job = ProcessingJob(
            job_id=job_id,
            job_type=job_type,
            request_id=request_id,
            status=JobStatus.QUEUED.value,
            current_stage=initial_stage,
            progress_percent=0.0,
            entity_type=entity_type,
            entity_id=entity_id,
            source_filename=source_filename,
            source_metadata=source_metadata or {},
            stage_details={
                "events": [
                    {
                        "stage": initial_stage,
                        "timestamp": now.isoformat(),
                        "progress": 0.0,
                        "message": "Job registered and queued for execution."
                    }
                ]
            },
            result_reference={},
            created_at=now,
            updated_at=now
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info(f"Created ProcessingJob [id={job_id}, type={job_type}, req={request_id}, status=QUEUED]")
        return job

    @staticmethod
    def get_job(db: Session, job_id: str) -> Optional[ProcessingJob]:
        return db.execute(
            select(ProcessingJob).where(ProcessingJob.job_id == job_id)
        ).scalar_one_or_none()

    @staticmethod
    def list_jobs(
        db: Session,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[ProcessingJob], int]:
        stmt = select(ProcessingJob)
        count_stmt = select(func.count()).select_from(ProcessingJob)

        if status:
            stmt = stmt.where(ProcessingJob.status == status)
            count_stmt = count_stmt.where(ProcessingJob.status == status)
        if job_type:
            stmt = stmt.where(ProcessingJob.job_type == job_type)
            count_stmt = count_stmt.where(ProcessingJob.job_type == job_type)
        if entity_id:
            stmt = stmt.where(ProcessingJob.entity_id == entity_id)
            count_stmt = count_stmt.where(ProcessingJob.entity_id == entity_id)

        total = db.execute(count_stmt).scalar_one()
        jobs = db.execute(
            stmt.order_by(desc(ProcessingJob.created_at)).limit(limit).offset(offset)
        ).scalars().all()

        return list(jobs), total

    @staticmethod
    def find_active_job(
        db: Session,
        job_type: str,
        entity_id: Optional[str] = None,
        source_filename: Optional[str] = None
    ) -> Optional[ProcessingJob]:
        """Finds any non-terminal job to enforce idempotency."""
        if not entity_id and not source_filename:
            return None

        stmt = select(ProcessingJob).where(
            ProcessingJob.job_type == job_type,
            ProcessingJob.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value])
        )
        if entity_id:
            stmt = stmt.where(ProcessingJob.entity_id == entity_id)
        if source_filename:
            stmt = stmt.where(ProcessingJob.source_filename == source_filename)

        return db.execute(stmt.order_by(desc(ProcessingJob.created_at))).scalars().first()

    @staticmethod
    def start_job(db: Session, job_id: str) -> ProcessingJob:
        job = db.execute(select(ProcessingJob).where(ProcessingJob.job_id == job_id)).scalar_one_or_none()
        if not job:
            raise EntityNotFoundException("ProcessingJob", job_id)

        if job.status in TERMINAL_STATUSES:
            raise CadastreException(f"Cannot start job in terminal state: {job.status}")

        now = datetime.now(timezone.utc)
        job.status = JobStatus.RUNNING.value
        job.started_at = now
        job.updated_at = now

        events = list(job.stage_details.get("events", []))
        events.append({
            "stage": job.current_stage,
            "timestamp": now.isoformat(),
            "progress": job.progress_percent,
            "message": "Job worker commenced execution."
        })
        job.stage_details = {**job.stage_details, "events": events}

        db.commit()
        db.refresh(job)
        logger.info(f"Started ProcessingJob [id={job_id}, status=RUNNING]")
        return job

    @staticmethod
    def transition_stage(
        db: Session,
        job_id: str,
        stage: str,
        progress_percent: float,
        details: Optional[Dict[str, Any]] = None
    ) -> ProcessingJob:
        job = db.execute(select(ProcessingJob).where(ProcessingJob.job_id == job_id)).scalar_one_or_none()
        if not job:
            raise EntityNotFoundException("ProcessingJob", job_id)

        if job.status in TERMINAL_STATUSES:
            logger.warning(f"Ignored stage transition to {stage} for terminal job {job_id} ({job.status})")
            return job

        now = datetime.now(timezone.utc)
        job.status = JobStatus.RUNNING.value
        job.current_stage = stage
        job.progress_percent = min(100.0, max(0.0, float(progress_percent)))
        job.updated_at = now

        events = list(job.stage_details.get("events", []))
        event_entry = {
            "stage": stage,
            "timestamp": now.isoformat(),
            "progress": job.progress_percent,
            "details": details or {}
        }
        events.append(event_entry)
        job.stage_details = {**job.stage_details, "events": events}

        db.commit()
        db.refresh(job)
        duration_s = _calc_duration(job.started_at, now)
        logger.info(f"Job {job_id} transitioned to stage={stage} ({job.progress_percent}%) [duration={duration_s:.2f}s]")
        return job

    @staticmethod
    def mark_completed(
        db: Session,
        job_id: str,
        result_reference: Dict[str, Any],
        stage_details: Optional[Dict[str, Any]] = None
    ) -> ProcessingJob:
        job = db.execute(select(ProcessingJob).where(ProcessingJob.job_id == job_id)).scalar_one_or_none()
        if not job:
            raise EntityNotFoundException("ProcessingJob", job_id)

        if job.status == JobStatus.CANCELLED.value:
            logger.info(f"Job {job_id} was cancelled; skipping mark_completed.")
            return job

        now = datetime.now(timezone.utc)
        job.status = JobStatus.COMPLETED.value
        job.current_stage = JobStage.COMPLETED.value
        job.progress_percent = 100.0
        job.completed_at = now
        job.updated_at = now
        job.result_reference = result_reference

        events = list(job.stage_details.get("events", []))
        events.append({
            "stage": JobStage.COMPLETED.value,
            "timestamp": now.isoformat(),
            "progress": 100.0,
            "message": "Job successfully completed all processing stages."
        })
        current_details = dict(job.stage_details)
        current_details["events"] = events
        if stage_details:
            current_details.update(stage_details)
        job.stage_details = current_details

        db.commit()
        db.refresh(job)
        duration_s = _calc_duration(job.started_at, now)
        logger.info(f"ProcessingJob [id={job_id}] marked COMPLETED (100%) in {duration_s:.2f}s.")
        return job

    @staticmethod
    def mark_failed(
        db: Session,
        job_id: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> ProcessingJob:
        job = db.execute(select(ProcessingJob).where(ProcessingJob.job_id == job_id)).scalar_one_or_none()
        if not job:
            raise EntityNotFoundException("ProcessingJob", job_id)

        now = datetime.now(timezone.utc)
        job.status = JobStatus.FAILED.value
        job.current_stage = JobStage.FAILED.value
        job.completed_at = now
        job.updated_at = now
        job.error_message = error_message
        job.error_details = error_details or {}

        events = list(job.stage_details.get("events", []))
        events.append({
            "stage": JobStage.FAILED.value,
            "timestamp": now.isoformat(),
            "progress": job.progress_percent,
            "error": error_message
        })
        job.stage_details = {**job.stage_details, "events": events}

        db.commit()
        db.refresh(job)
        duration_s = _calc_duration(job.started_at, now)
        logger.error(f"ProcessingJob [id={job_id}] marked FAILED after {duration_s:.2f}s: {error_message}")
        return job

    @staticmethod
    def cancel_job(
        db: Session,
        job_id: str,
        reason: str = "Cancelled by user"
    ) -> ProcessingJob:
        job = db.execute(select(ProcessingJob).where(ProcessingJob.job_id == job_id)).scalar_one_or_none()
        if not job:
            raise EntityNotFoundException("ProcessingJob", job_id)

        if job.status in TERMINAL_STATUSES:
            raise CadastreException(f"Cannot cancel job in terminal state: {job.status}")

        now = datetime.now(timezone.utc)
        job.status = JobStatus.CANCELLED.value
        job.current_stage = JobStage.CANCELLED.value
        job.completed_at = now
        job.updated_at = now
        job.error_message = reason

        events = list(job.stage_details.get("events", []))
        events.append({
            "stage": JobStage.CANCELLED.value,
            "timestamp": now.isoformat(),
            "progress": job.progress_percent,
            "reason": reason
        })
        job.stage_details = {**job.stage_details, "events": events}

        db.commit()
        db.refresh(job)
        logger.warning(f"ProcessingJob [id={job_id}] marked CANCELLED: {reason}")
        return job
