from typing import Optional, Dict, Any
from sqlalchemy import String, Float, Boolean, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, UUIDMixin, TimestampMixin


class ValidationRunRecord(Base, UUIDMixin, TimestampMixin):
    """
    Auditable record of a deterministic cadastral validation execution.
    Stores validation metrics, executed rules, issues, and quality score.
    Supports reproducibility and historical compliance tracking.
    """
    __tablename__ = "validation_run_records"

    validation_run_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)  # PARCEL, BUILDING, UNIT
    target_entity_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), default="1.0.0-cadastral-validator", nullable=False)
    data_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # High-level outcome
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    quality_grade: Mapped[str] = mapped_column(String(30), nullable=False)  # HIGH_CONFIDENCE, GOOD_QUALITY, REQUIRES_REVIEW, INVALID_OR_INCOMPLETE

    # Execution counters
    rules_executed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rules_passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rules_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    critical_issues_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warnings_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    info_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Detailed audit findings and summary payload
    results: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
