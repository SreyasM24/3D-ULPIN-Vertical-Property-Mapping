"""
Coordinate Reference System (CRS) & Projection Utilities.

Provides rigorous geographic <-> projected coordinate transformations
using PyProj and EPSG geodesy standards.
"""

import math
from typing import Tuple, Optional, Any
import pyproj
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from app.core.exceptions import InvalidGeometryException


# Standard EPSG constants
WGS84_CRS = "EPSG:4326"


def validate_wgs84_coordinates(lon: float, lat: float) -> None:
    """Validates that longitude and latitude conform to WGS84 geographic ranges."""
    if not (-180.0 <= lon <= 180.0):
        raise InvalidGeometryException(
            f"Longitude {lon} is out of bounds [-180.0, 180.0]"
        )
    if not (-90.0 <= lat <= 90.0):
        raise InvalidGeometryException(
            f"Latitude {lat} is out of bounds [-90.0, 90.0]"
        )


def get_utm_epsg_for_point(lat: float, lon: float) -> str:
    """
    Computes the appropriate UTM zone EPSG code for a WGS84 (lat, lon) coordinate.
    Northern hemisphere: EPSG:32601 - EPSG:32660
    Southern hemisphere: EPSG:32701 - EPSG:32760
    """
    validate_wgs84_coordinates(lon, lat)
    zone = int((lon + 180.0) / 6.0) + 1
    if zone > 60:
        zone = 60
    base = 32600 if lat >= 0 else 32700
    epsg_code = f"EPSG:{base + zone}"
    return epsg_code


def get_transformer(src_crs: str, dst_crs: str) -> pyproj.Transformer:
    """
    Creates a pyproj Transformer with always_xy=True to guarantee (x/lon, y/lat) order.
    """
    return pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=True)


def project_geometry(
    geom: BaseGeometry,
    src_crs: str = WGS84_CRS,
    dst_crs: Optional[str] = None
) -> Tuple[BaseGeometry, str]:
    """
    Safely projects a Shapely geometry from source CRS to destination CRS.
    If dst_crs is None, automatically calculates the optimal UTM zone from the geometry centroid.
    Returns (projected_geometry, dst_crs).
    """
    if geom.is_empty:
        raise InvalidGeometryException("Cannot project an empty geometry.")

    if dst_crs is None:
        centroid = geom.centroid
        dst_crs = get_utm_epsg_for_point(centroid.y, centroid.x)

    if src_crs == dst_crs:
        return geom, dst_crs

    try:
        transformer = get_transformer(src_crs, dst_crs)
        projected = transform(transformer.transform, geom)
        return projected, dst_crs
    except Exception as e:
        raise InvalidGeometryException(
            f"Projection failed from {src_crs} to {dst_crs}: {str(e)}"
        )


def unproject_geometry(
    geom: BaseGeometry,
    src_crs: str,
    dst_crs: str = WGS84_CRS
) -> BaseGeometry:
    """Transforms a projected Cartesian geometry back to WGS84 geographic coordinates."""
    if src_crs == dst_crs:
        return geom
    transformer = get_transformer(src_crs, dst_crs)
    return transform(transformer.transform, geom)
