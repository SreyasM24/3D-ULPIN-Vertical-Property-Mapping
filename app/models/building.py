from typing import List, Optional
from sqlalchemy import String, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin, TimestampMixin


class Building(Base, UUIDMixin, TimestampMixin):
    """
    Building / Physical Structure model situated on a land parcel.
    Serves as the vertical envelope enclosing floor strata and units.
    """
    __tablename__ = "buildings"

    parcel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("land_parcels.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    building_name: Mapped[str] = mapped_column(String(100), nullable=False)
    building_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    rera_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    structure_type: Mapped[str] = mapped_column(String(50), default="RESIDENTIAL", nullable=False)
    
    # Vertical extent
    floors_above_ground: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    basement_floors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_height_m: Mapped[float] = mapped_column(Float, nullable=False)
    ground_elevation_m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Building Footprint (2D polygon GeoJSON)
    footprint_geojson: Mapped[dict] = mapped_column(JSON, nullable=False)
    spatial_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    # Relationships
    parcel: Mapped["LandParcel"] = relationship("LandParcel", back_populates="buildings")
    floors: Mapped[List["FloorLevel"]] = relationship(
        "FloorLevel",
        back_populates="building",
        cascade="all, delete-orphan",
        order_by="FloorLevel.level_number"
    )
