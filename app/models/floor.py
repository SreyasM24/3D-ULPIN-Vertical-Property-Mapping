from typing import List, Optional
from sqlalchemy import String, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin, TimestampMixin


class FloorLevel(Base, UUIDMixin, TimestampMixin):
    """
    Floor / Level / Strata Model within a Building.
    Defines a vertical elevation slice (Z-min to Z-max).
    """
    __tablename__ = "floor_levels"

    building_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("buildings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    level_number: Mapped[int] = mapped_column(Integer, nullable=False)  # -2, -1, 0, 1, 2...
    level_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # B02, B01, G00, L01...
    level_type: Mapped[str] = mapped_column(String(30), default="TYPICAL_FLOOR", nullable=False)
    
    # Elevation bounds relative to MSL/datum
    z_min: Mapped[float] = mapped_column(Float, nullable=False)
    z_max: Mapped[float] = mapped_column(Float, nullable=False)
    floor_height_m: Mapped[float] = mapped_column(Float, nullable=False)

    # Optional floor boundary polygon if different from building footprint
    footprint_geojson: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    spatial_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    # Relationships
    building: Mapped["Building"] = relationship("Building", back_populates="floors")
    units: Mapped[List["VerticalUnit"]] = relationship(
        "VerticalUnit",
        back_populates="floor",
        cascade="all, delete-orphan",
        order_by="VerticalUnit.unit_number"
    )
