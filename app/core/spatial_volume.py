"""
3D Spatial Volume & Geometry Abstraction.

Provides clean abstraction for volumetric cadastral entities:
- SpatialVolume (abstract base)
- PrismVolume (footprint + z_min/z_max)
- ExtrudedPolygonVolume
- PolyhedralMeshVolume (extensibility hook for arbitrary 3D solids)
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Tuple, Optional
from shapely.geometry import shape, Polygon, MultiPolygon, Point
from app.core.exceptions import InvalidGeometryException
from app.core.crs import (
    WGS84_CRS,
    project_geometry,
    get_utm_epsg_for_point,
    validate_wgs84_coordinates,
)


class VolumeType(str, Enum):
    PRISM = "PRISM"
    EXTRUDED_POLYGON = "EXTRUDED_POLYGON"
    POLYHEDRAL_MESH = "POLYHEDRAL_MESH"


class VerticalClassification(str, Enum):
    UNDERGROUND = "UNDERGROUND"
    GROUND_LEVEL = "GROUND_LEVEL"
    ELEVATED = "ELEVATED"
    MULTI_LEVEL_INFRASTRUCTURE = "MULTI_LEVEL_INFRASTRUCTURE"


class UnitCadastralType(str, Enum):
    APARTMENT = "APARTMENT"
    OFFICE = "OFFICE"
    SHOP = "SHOP"
    PARKING = "PARKING"
    BASEMENT = "BASEMENT"
    UTILITY = "UTILITY"
    TUNNEL = "TUNNEL"
    ELEVATED_STRUCTURE = "ELEVATED_STRUCTURE"
    COMMON_AREA = "COMMON_AREA"
    OTHER = "OTHER"


def classify_vertical_position(
    z_min: float,
    z_max: float,
    ground_elevation_m: float,
    tolerance_m: float = 0.5
) -> VerticalClassification:
    """
    Classifies the vertical placement of a volume relative to ground elevation datum:
    - UNDERGROUND: Entire volume is below ground reference
    - GROUND_LEVEL: Volume straddles the ground elevation datum
    - ELEVATED: Entire volume is above ground reference
    - MULTI_LEVEL_INFRASTRUCTURE: Height exceeds typical floor bounds (e.g. > 15m) spanning multiple tiers
    """
    height = z_max - z_min
    if height > 15.0 and (z_min < ground_elevation_m and z_max > ground_elevation_m):
        return VerticalClassification.MULTI_LEVEL_INFRASTRUCTURE

    if z_max <= ground_elevation_m + tolerance_m:
        return VerticalClassification.UNDERGROUND
    elif z_min >= ground_elevation_m - tolerance_m:
        return VerticalClassification.ELEVATED
    else:
        return VerticalClassification.GROUND_LEVEL


class SpatialVolume(ABC):
    """Abstract Base Class for Volumetric Cadastral Geometries."""

    def __init__(
        self,
        volume_type: VolumeType,
        z_min: float,
        z_max: float,
        projected_crs: str,
        vertical_classification: VerticalClassification = VerticalClassification.ELEVATED
    ):
        if z_max <= z_min:
            raise ValueError(f"z_max ({z_max}) must be strictly greater than z_min ({z_min})")
        self.volume_type = volume_type
        self.z_min = float(z_min)
        self.z_max = float(z_max)
        self.height_m = round(self.z_max - self.z_min, 3)
        self.projected_crs = projected_crs
        self.vertical_classification = vertical_classification

    @property
    @abstractmethod
    def area_sqm(self) -> float:
        """Projected horizontal area in square meters."""
        pass

    @property
    @abstractmethod
    def volume_cu_m(self) -> float:
        """Enclosed 3D volume in cubic meters."""
        pass

    @abstractmethod
    def contains_point_3d(self, lon: float, lat: float, z: float) -> bool:
        """Tests if a 3D point (lon, lat, z) lies inside the volumetric envelope."""
        pass

    @abstractmethod
    def intersects_bbox_3d(
        self,
        min_lon: float,
        min_lat: float,
        min_z: float,
        max_lon: float,
        max_lat: float,
        max_z: float
    ) -> bool:
        """Tests intersection against a 3D bounding box."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serializes volumetric properties into a standard dictionary."""
        pass


class PrismVolume(SpatialVolume):
    """
    Orthogonal Extruded Prism Volumetric Geometry (MVP Standard).
    Bounded horizontally by a normalized 2D Polygon and vertically by [z_min, z_max].
    Calculates metric area and volume rigorously in projected Cartesian UTM space.
    """

    def __init__(
        self,
        footprint_geojson: Dict[str, Any],
        z_min: float,
        z_max: float,
        ground_elevation_m: float = 0.0,
        source_crs: str = WGS84_CRS,
        projected_crs: Optional[str] = None
    ):
        # 1. Normalize footprint geometry
        from app.services.geometry_normalization import GeometryNormalizationService
        norm_result = GeometryNormalizationService.normalize_geojson(footprint_geojson)
        self.footprint_geom = norm_result.geometry
        self.normalized_geojson = norm_result.geojson

        # 2. Determine local UTM projection
        c = self.footprint_geom.centroid
        self.centroid_lon = float(c.x)
        self.centroid_lat = float(c.y)
        validate_wgs84_coordinates(self.centroid_lon, self.centroid_lat)

        resolved_utm = projected_crs or get_utm_epsg_for_point(self.centroid_lat, self.centroid_lon)
        self.projected_geom, self.projected_crs_code = project_geometry(
            self.footprint_geom, src_crs=source_crs, dst_crs=resolved_utm
        )

        # 3. Compute metric dimensions
        self._area_sqm = round(float(abs(self.projected_geom.area)), 2)
        self._perimeter_m = round(float(self.projected_geom.length), 2)
        v_class = classify_vertical_position(z_min, z_max, ground_elevation_m)

        super().__init__(
            volume_type=VolumeType.PRISM,
            z_min=z_min,
            z_max=z_max,
            projected_crs=self.projected_crs_code,
            vertical_classification=v_class
        )
        self.ground_elevation_m = ground_elevation_m
        self._volume_cu_m = round(self._area_sqm * self.height_m, 2)
        self.bbox_wgs84 = [round(b, 7) for b in self.footprint_geom.bounds]

    @property
    def area_sqm(self) -> float:
        return self._area_sqm

    @property
    def perimeter_m(self) -> float:
        return self._perimeter_m

    @property
    def volume_cu_m(self) -> float:
        return self._volume_cu_m

    def contains_point_3d(self, lon: float, lat: float, z: float) -> bool:
        if not (self.z_min <= z <= self.z_max):
            return False
        pt = Point(lon, lat)
        return self.footprint_geom.intersects(pt)

    def intersects_bbox_3d(
        self,
        min_lon: float,
        min_lat: float,
        min_z: float,
        max_lon: float,
        max_lat: float,
        max_z: float
    ) -> bool:
        # 1. Vertical interval overlap
        if max_z < self.z_min or min_z > self.z_max:
            return False

        # 2. Horizontal bounding box overlap
        b_min_lon, b_min_lat, b_max_lon, b_max_lat = self.bbox_wgs84
        if max_lon < b_min_lon or min_lon > b_max_lon:
            return False
        if max_lat < b_min_lat or min_lat > b_max_lat:
            return False

        # 3. Exact 2D polygon intersection
        bbox_poly = Polygon([
            (min_lon, min_lat),
            (max_lon, min_lat),
            (max_lon, max_lat),
            (min_lon, max_lat),
            (min_lon, min_lat)
        ])
        return self.footprint_geom.intersects(bbox_poly)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "volume_type": self.volume_type.value,
            "vertical_classification": self.vertical_classification.value,
            "z_min": self.z_min,
            "z_max": self.z_max,
            "height_m": self.height_m,
            "area_sqm": self.area_sqm,
            "perimeter_m": self.perimeter_m,
            "volume_cu_m": self.volume_cu_m,
            "centroid": [self.centroid_lat, self.centroid_lon],
            "bbox_wgs84": self.bbox_wgs84,
            "projected_crs": self.projected_crs,
            "footprint_geojson": self.normalized_geojson
        }


class PolyhedralMeshVolume(SpatialVolume):
    """
    Extensibility Hook for Arbitrary 3D Polyhedrons / CityGML LoD2+ solids.
    Explicitly declares that full non-manifold 3D boolean operations require
    dedicated 3D geometry kernels (e.g. CGAL/Trimesh) in future phases.
    """

    def __init__(
        self,
        vertices_3d: List[Tuple[float, float, float]],
        faces: List[List[int]],
        z_min: float,
        z_max: float,
        projected_crs: str,
        estimated_volume_cu_m: float,
        estimated_footprint_area_sqm: float
    ):
        super().__init__(
            volume_type=VolumeType.POLYHEDRAL_MESH,
            z_min=z_min,
            z_max=z_max,
            projected_crs=projected_crs
        )
        self.vertices_3d = vertices_3d
        self.faces = faces
        self._volume_cu_m = estimated_volume_cu_m
        self._area_sqm = estimated_footprint_area_sqm

    @property
    def area_sqm(self) -> float:
        return self._area_sqm

    @property
    def volume_cu_m(self) -> float:
        return self._volume_cu_m

    def contains_point_3d(self, lon: float, lat: float, z: float) -> bool:
        # Bounding extent pre-check
        return self.z_min <= z <= self.z_max

    def intersects_bbox_3d(self, *args, **kwargs) -> bool:
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "volume_type": self.volume_type.value,
            "vertical_classification": self.vertical_classification.value,
            "z_min": self.z_min,
            "z_max": self.z_max,
            "height_m": self.height_m,
            "area_sqm": self.area_sqm,
            "volume_cu_m": self.volume_cu_m,
            "vertex_count": len(self.vertices_3d),
            "face_count": len(self.faces),
            "projected_crs": self.projected_crs
        }
