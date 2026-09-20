from typing import List, Optional
from sqlalchemy import String, Float, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin, TimestampMixin


class VerticalUnit(Base, UUIDMixin, TimestampMixin):
    """
    3D Spatial Property Unit model (Apartment, Commercial Unit, Parking Bay, etc.).
    Represents volumetric parcel space bounded by (footprint 2D polygon) x (z_min, z_max).
    """
    __tablename__ = "vertical_units"

    floor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("floor_levels.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    unit_number: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    unit_type: Mapped[str] = mapped_column(String(40), default="APARTMENT", nullable=False)

    # 3D ULPIN Prototype identifier (SIH 26011 specification)
    ulpin_3d: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    ulpin_status: Mapped[str] = mapped_column(String(30), default="PROTOTYPE_GENERATED", nullable=False)

    # Volumetric Spatial Definition
    footprint_geojson: Mapped[dict] = mapped_column(JSON, nullable=False)
    z_min: Mapped[float] = mapped_column(Float, nullable=False)
    z_max: Mapped[float] = mapped_column(Float, nullable=False)
    carpet_area_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    builtup_area_sqm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume_cu_m: Mapped[float] = mapped_column(Float, nullable=False)

    # 3D Validation & Topology Flags
    is_clash_free: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_multi_floor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    floor_span: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Spatial capture & provenance metadata
    spatial_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    # Relationships
    floor: Mapped["FloorLevel"] = relationship("FloorLevel", back_populates="units")
    ownership_records: Mapped[List["OwnershipRecord"]] = relationship(
        "OwnershipRecord",
        back_populates="unit",
        cascade="all, delete-orphan",
        order_by="OwnershipRecord.created_at"
    )
