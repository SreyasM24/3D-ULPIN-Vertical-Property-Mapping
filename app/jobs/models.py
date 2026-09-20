"""
SQLAlchemy Model for Asynchronous Processing Jobs.
Persists job state, execution stage, progress, audit events, and results.
"""

from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import String, Float, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin, TimestampMixin


class ProcessingJob(Base, UUIDMixin, TimestampMixin):
    """
    Persistent record of an asynchronous ingestion and cadastral processing job.
    Supports state tracking across application restarts and cluster workers.
    """
    __tablename__ = "processing_jobs"

    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    
    # State tracking
    status: Mapped[str] = mapped_column(String(30), index=True, default="QUEUED", nullable=False)
    current_stage: Mapped[str] = mapped_column(String(50), default="QUEUED", nullable=False)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Target entity association
    entity_type: Mapped[Optional[str]] = mapped_column(String(30), index=True, nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    
    # Source metadata
    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Traceability & audit trail
    stage_details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Errors if any
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Output results and linked artifacts
    result_reference: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        duration = None
        if self.started_at and self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            duration = (datetime.utcnow() - self.started_at).total_seconds()

        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "request_id": self.request_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "progress_percent": self.progress_percent,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "source_filename": self.source_filename,
            "source_metadata": self.source_metadata,
            "stage_details": self.stage_details,
            "error_message": self.error_message,
            "result_reference": self.result_reference,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "duration_seconds": duration,
        }
