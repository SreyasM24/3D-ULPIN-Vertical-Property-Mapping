from typing import Optional
from sqlalchemy import String, Float, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin, TimestampMixin


class OwnershipRecord(Base, UUIDMixin, TimestampMixin):
    """
    Ownership and Record of Rights (RoR) model for a 3D Vertical Property Unit.
    """
    __tablename__ = "ownership_records"

    unit_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vertical_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    owner_name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Hashed identifier (Aadhaar / Tax ID hash) for privacy compliance
    owner_identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    share_percentage: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    ownership_type: Mapped[str] = mapped_column(String(30), default="INDIVIDUAL", nullable=False)
    
    title_deed_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    registration_date: Mapped[str] = mapped_column(String(30), nullable=False)
    
    is_encumbered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encumbrance_details: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    meta_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    # Relationships
    unit: Mapped["VerticalUnit"] = relationship("VerticalUnit", back_populates="ownership_records")
