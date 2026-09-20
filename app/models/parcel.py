from typing import List, Optional
from sqlalchemy import String, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDMixin, TimestampMixin


class LandParcel(Base, UUIDMixin, TimestampMixin):
    """
    2D Cadastral Land Parcel model.
    Represents the surface land parcel identified by base ULPIN (Bhu-Aadhaar).
    """
    __tablename__ = "land_parcels"

    ulpin: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    state_code: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    district_code: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    village_code: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    survey_number: Mapped[str] = mapped_column(String(50), nullable=False)
    subdivision_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Spatial attributes
    area_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lon: Mapped[float] = mapped_column(Float, nullable=False)
    base_elevation_m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # 2D geometry as GeoJSON dict
    geometry_geojson: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Provenance and capture metadata (CRS, source: DRONE, TOTAL_STATION, etc.)
    spatial_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    # Relationship: Parcel has multiple buildings/structures
    buildings: Mapped[List["Building"]] = relationship(
        "Building",
        back_populates="parcel",
        cascade="all, delete-orphan",
        order_by="Building.created_at"
    )
