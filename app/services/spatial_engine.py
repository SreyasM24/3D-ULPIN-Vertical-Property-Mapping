"""
Spatial Engine: 2D/3D Volumetric Computations, Topology Validation & Clash Detection.
Powered by Shapely, PyProj UTM Cartography, and GeometryNormalizationService.
"""

from typing import Dict, Any, List, Tuple, Optional, Union
from dataclasses import dataclass, field
from shapely.geometry import shape, Polygon, MultiPolygon, mapping
from shapely.validation import explain_validity

from app.core.exceptions import InvalidGeometryException
from app.core.crs import (
    WGS84_CRS,
    project_geometry,
    unproject_geometry,
    get_utm_epsg_for_point,
    validate_wgs84_coordinates,
)
from app.services.geometry_normalization import (
    GeometryNormalizationService,
    NormalizationResult,
)


@dataclass
class VolumetricPrism:
    """
    Extensible 3D Cadastral Volumetric Representation.
    MVP models LoD1 extruded prisms from 2D projected footprints;
    designed to interface with arbitrary polyhedral / CityGML LoD2+ models.
    """
    footprint_geojson: Dict[str, Any]
    projected_crs: str
    z_min: float
    z_max: float
    height_m: float
    area_sqm: float
    volume_cu_m: float
    representation_type: str = "EXTRUDED_PRISM_LOD1"
    provenance: Dict[str, Any] = field(default_factory=dict)


def geojson_to_shapely(
    geojson_dict: Dict[str, Any],
    auto_heal: bool = False
) -> Union[Polygon, MultiPolygon]:
    """
    Converts a GeoJSON dict into a validated Shapely Polygon or MultiPolygon.
    If auto_heal is True, applies ring closure, deduplication, and safe healing via normalization service.
    If auto_heal is False, performs strict standard GeoJSON validation.
    """
    if auto_heal:
        res = GeometryNormalizationService.normalize_geojson(geojson_dict)
        return res.geometry

    if not isinstance(geojson_dict, dict):
        raise InvalidGeometryException("GeoJSON must be a dictionary.")

    geom_type = geojson_dict.get("type")
    if geom_type not in ("Polygon", "MultiPolygon"):
        raise InvalidGeometryException(f"Expected GeoJSON type 'Polygon' or 'MultiPolygon', got '{geom_type}'")

    coords = geojson_dict.get("coordinates")
    if not coords or not isinstance(coords, list) or len(coords) == 0:
        raise InvalidGeometryException("Polygon must contain at least one linear ring.")

    if geom_type == "Polygon":
        rings = coords
    else:
        rings = [r for poly in coords for r in poly]

    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            raise InvalidGeometryException("A linear ring must contain at least 4 coordinate pairs.")
        if ring[0][:2] != ring[-1][:2]:
            raise InvalidGeometryException("Linear ring is not closed: first and last coordinates must match.")

    try:
        geom = shape(geojson_dict)
        if not geom.is_valid:
            reason = explain_validity(geom)
            raise InvalidGeometryException(f"Invalid polygon geometry: {reason}")
        return geom
    except Exception as e:
        if isinstance(e, InvalidGeometryException):
            raise
        raise InvalidGeometryException(f"Failed to parse GeoJSON: {str(e)}")


def compute_centroid(geom: Union[Polygon, MultiPolygon]) -> Tuple[float, float]:
    """Computes [latitude, longitude] WGS84 centroid of geometry."""
    c = geom.centroid
    validate_wgs84_coordinates(c.x, c.y)
    return float(c.y), float(c.x)  # lat, lon


def compute_projected_spatial_metrics(
    geojson_or_geom: Union[Dict[str, Any], Polygon, MultiPolygon]
) -> Dict[str, Any]:
    """
    Calculates rigorous metric spatial measurements (area in m², perimeter in m,
    bounding box, centroid) by projecting to the optimal local UTM CRS.
    """
    repair_actions = []
    was_repaired = False

    if isinstance(geojson_or_geom, dict):
        norm_result = GeometryNormalizationService.normalize_geojson(geojson_or_geom)
        geom = norm_result.geometry
        was_repaired = norm_result.was_repaired
        repair_actions = norm_result.repair_actions
        norm_geojson = norm_result.geojson
    else:
        geom = geojson_or_geom
        norm_geojson = mapping(geom)

    # 1. Centroid in WGS84
    c = geom.centroid
    lat, lon = float(c.y), float(c.x)

    # 2. Project to dynamic local UTM zone
    projected_geom, projected_crs = project_geometry(geom, src_crs=WGS84_CRS)

    # 3. Metric measurements in projected Cartesian space
    area_sqm = round(float(abs(projected_geom.area)), 2)
    perimeter_m = round(float(projected_geom.length), 2)

    # 4. Bounding box [min_lon, min_lat, max_lon, max_lat]
    bounds = geom.bounds  # (minx, miny, maxx, maxy) = (min_lon, min_lat, max_lon, max_lat)
    bbox = [round(b, 7) for b in bounds]

    # Projected centroid
    pc = projected_geom.centroid

    return {
        "area_sqm": area_sqm,
        "perimeter_m": perimeter_m,
        "centroid_lat": round(lat, 7),
        "centroid_lon": round(lon, 7),
        "centroid_projected_x": round(float(pc.x), 2),
        "centroid_projected_y": round(float(pc.y), 2),
        "bbox": bbox,
        "source_crs": WGS84_CRS,
        "projected_crs": projected_crs,
        "normalized_geojson": norm_geojson,
        "was_repaired": was_repaired,
        "repair_actions": repair_actions,
    }


def compute_geodesic_area_sqm(geom: Union[Polygon, MultiPolygon]) -> float:
    """
    Calculates metric area in m² by projecting WGS84 geometry to local UTM zone.
    Replaces rough trigonometric approximation with rigorous cartographic projection.
    """
    metrics = compute_projected_spatial_metrics(geom)
    return metrics["area_sqm"]


def compute_volumetric_bounds(
    footprint_geojson: Dict[str, Any],
    z_min: float,
    z_max: float
) -> Dict[str, Any]:
    """
    Calculates 3D vertical boundaries:
    - Horizontal/projected carpet area in m²
    - Vertical elevations (z_min, z_max in m MSL)
    - Derived vertical height (h = z_max - z_min in m)
    - Derived 3D volume (V = area * height in m³)
    """
    if z_max <= z_min:
        raise ValueError(f"z_max ({z_max}) must be strictly greater than z_min ({z_min})")

    metrics = compute_projected_spatial_metrics(footprint_geojson)
    area_sqm = metrics["area_sqm"]
    height_m = round(z_max - z_min, 3)
    volume_cu_m = round(area_sqm * height_m, 2)

    prism = VolumetricPrism(
        footprint_geojson=metrics["normalized_geojson"],
        projected_crs=metrics["projected_crs"],
        z_min=z_min,
        z_max=z_max,
        height_m=height_m,
        area_sqm=area_sqm,
        volume_cu_m=volume_cu_m,
        representation_type="EXTRUDED_PRISM_LOD1",
        provenance={
            "source_crs": WGS84_CRS,
            "projected_crs": metrics["projected_crs"],
            "was_repaired": metrics["was_repaired"],
            "repair_actions": metrics["repair_actions"]
        }
    )

    return {
        "area_sqm": area_sqm,
        "perimeter_m": metrics["perimeter_m"],
        "height_m": height_m,
        "volume_cu_m": volume_cu_m,
        "projected_crs": metrics["projected_crs"],
        "prism": prism,
    }


def evaluate_building_containment(
    building_geojson: Dict[str, Any],
    parcel_geojson: Dict[str, Any],
    tolerance_sqm: float = 0.05
) -> Dict[str, Any]:
    """
    Rigorously checks building footprint containment against parent parcel in projected UTM.
    Returns structured status:
      - CONTAINED
      - PARTIALLY_OUTSIDE
      - COMPLETELY_OUTSIDE
      - INVALID_GEOMETRY
    """
    try:
        bld_geom = geojson_to_shapely(building_geojson)
        pcl_geom = geojson_to_shapely(parcel_geojson)
    except Exception as e:
        return {
            "status": "INVALID_GEOMETRY",
            "is_contained": False,
            "building_area_sqm": 0.0,
            "intersection_area_sqm": 0.0,
            "excess_area_sqm": 0.0,
            "excess_percentage": 0.0,
            "message": f"Invalid geometry: {str(e)}"
        }

    # Project both to parcel's optimal UTM zone
    c = pcl_geom.centroid
    utm_crs = get_utm_epsg_for_point(c.y, c.x)
    bld_proj, _ = project_geometry(bld_geom, src_crs=WGS84_CRS, dst_crs=utm_crs)
    pcl_proj, _ = project_geometry(pcl_geom, src_crs=WGS84_CRS, dst_crs=utm_crs)

    bld_area = round(float(bld_proj.area), 2)
    if bld_area == 0.0:
        return {
            "status": "INVALID_GEOMETRY",
            "is_contained": False,
            "building_area_sqm": 0.0,
            "intersection_area_sqm": 0.0,
            "excess_area_sqm": 0.0,
            "excess_percentage": 0.0,
            "message": "Building geometry has 0 area."
        }

    inter = bld_proj.intersection(pcl_proj)
    inter_area = round(float(inter.area), 2) if not inter.is_empty else 0.0

    diff = bld_proj.difference(pcl_proj)
    excess_area = round(float(diff.area), 2) if not diff.is_empty else 0.0

    effective_tolerance = max(tolerance_sqm, round(0.0005 * bld_area, 2))
    if excess_area <= effective_tolerance:
        return {
            "status": "CONTAINED",
            "is_contained": True,
            "building_area_sqm": bld_area,
            "intersection_area_sqm": bld_area,
            "excess_area_sqm": 0.0,
            "excess_percentage": 0.0,
            "message": "Building footprint is strictly contained within parcel boundary."
        }
    elif inter_area <= tolerance_sqm or inter_area == 0.0:
        return {
            "status": "COMPLETELY_OUTSIDE",
            "is_contained": False,
            "building_area_sqm": bld_area,
            "intersection_area_sqm": 0.0,
            "excess_area_sqm": bld_area,
            "excess_percentage": 100.0,
            "message": "Building footprint is completely outside parent parcel boundary."
        }
    else:
        excess_pct = round((excess_area / bld_area) * 100.0, 2)
        return {
            "status": "PARTIALLY_OUTSIDE",
            "is_contained": False,
            "building_area_sqm": bld_area,
            "intersection_area_sqm": inter_area,
            "excess_area_sqm": excess_area,
            "excess_percentage": excess_pct,
            "message": f"Building footprint extends outside parcel by {excess_area:.2f} m² ({excess_pct}%)."
        }


def check_containment(
    inner_geojson: Dict[str, Any],
    outer_geojson: Dict[str, Any],
    tolerance_sqm: float = 0.05
) -> Tuple[bool, float]:
    """
    Backward-compatible check: returns (is_contained, excess_area_sqm).
    Evaluates in projected Cartesian space.
    """
    res = evaluate_building_containment(inner_geojson, outer_geojson, tolerance_sqm=tolerance_sqm)
    return res["is_contained"], res["excess_area_sqm"]


def detect_3d_clashes(
    units: List[Dict[str, Any]],
    tolerance_overlap_m: float = 0.05,
    tolerance_area_sqm: float = 0.05
) -> List[Dict[str, Any]]:
    """
    Performs pairwise 3D clash/collision detection across a set of spatial units.
    Uses projected UTM polygons to calculate true metric overlap areas.
    """
    clashes: List[Dict[str, Any]] = []
    n = len(units)
    if n < 2:
        return clashes

    # Pre-parse and project polygons into local UTM
    parsed_polys = []
    utm_crs = None

    for u in units:
        try:
            poly = geojson_to_shapely(u["footprint_geojson"])
            if utm_crs is None and not poly.is_empty:
                c = poly.centroid
                utm_crs = get_utm_epsg_for_point(c.y, c.x)
            proj_poly, _ = project_geometry(poly, src_crs=WGS84_CRS, dst_crs=utm_crs)
            parsed_polys.append(proj_poly)
        except Exception:
            parsed_polys.append(None)

    for i in range(n):
        u1 = units[i]
        poly1 = parsed_polys[i]
        if poly1 is None:
            continue

        for j in range(i + 1, n):
            u2 = units[j]
            poly2 = parsed_polys[j]
            if poly2 is None:
                continue

            # 1. Check vertical elevation overlap
            z_overlap = min(u1["z_max"], u2["z_max"]) - max(u1["z_min"], u2["z_min"])
            if z_overlap <= tolerance_overlap_m:
                # Vertically separated, no volumetric clash possible
                continue

            # 2. Check 2D bounding box intersection in projected coordinates
            if not poly1.envelope.intersects(poly2.envelope):
                continue

            # 3. Check exact 2D intersection
            inter = poly1.intersection(poly2)
            if inter.is_empty or inter.area == 0:
                continue

            overlap_area = round(float(abs(inter.area)), 2)

            if overlap_area > tolerance_area_sqm:
                overlap_vol = round(overlap_area * z_overlap, 2)
                clashes.append({
                    "unit_a_id": u1["id"],
                    "unit_a_ulpin": u1.get("ulpin_3d", ""),
                    "unit_a_number": u1.get("unit_number", ""),
                    "unit_b_id": u2["id"],
                    "unit_b_ulpin": u2.get("ulpin_3d", ""),
                    "unit_b_number": u2.get("unit_number", ""),
                    "overlap_area_sqm": overlap_area,
                    "vertical_overlap_m": round(z_overlap, 3),
                    "overlap_volume_cu_m": overlap_vol,
                    "severity": "ERROR" if overlap_vol > 0.1 else "WARNING"
                })

    return clashes


def build_3d_geojson_feature(unit: Any) -> Dict[str, Any]:
    """
    Transforms a VerticalUnit ORM/dict into a 3D GeoJSON Feature for web 3D clients.
    """
    footprint = unit.footprint_geojson if isinstance(unit.footprint_geojson, dict) else {}
    return {
        "type": "Feature",
        "id": str(unit.id),
        "geometry": footprint,
        "properties": {
            "ulpin_3d": unit.ulpin_3d,
            "unit_number": unit.unit_number,
            "unit_code": unit.unit_code,
            "unit_type": unit.unit_type,
            "floor_id": str(unit.floor_id),
            "z_min": unit.z_min,
            "z_max": unit.z_max,
            "height_m": round(unit.z_max - unit.z_min, 3),
            "carpet_area_sqm": unit.carpet_area_sqm,
            "volume_cu_m": unit.volume_cu_m,
            "is_clash_free": unit.is_clash_free,
            "status": unit.status,
            "crs": WGS84_CRS,
            "representation_type": "EXTRUDED_PRISM_LOD1"
        }
    }
