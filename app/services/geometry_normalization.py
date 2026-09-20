"""
Geometry Normalization Service for Cadastral 2D & 3D Boundaries.

Handles Polygon & MultiPolygon validation, ring closure, vertex deduplication,
orientation enforcement (OGC / RFC 7946 Right-Hand Rule), precision snapping,
and safe topological healing with full provenance auditing.
"""

from typing import Dict, Any, List, Tuple, Optional, Union
from dataclasses import dataclass, field
import shapely
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, LinearRing
from shapely.validation import explain_validity
from shapely.ops import orient

from app.core.exceptions import InvalidGeometryException
from app.core.crs import validate_wgs84_coordinates


@dataclass
class NormalizationResult:
    """Audit container for normalized cadastral geometry."""
    geometry: Union[Polygon, MultiPolygon]
    geojson: Dict[str, Any]
    is_valid: bool
    was_repaired: bool
    repair_actions: List[str] = field(default_factory=list)
    validation_message: str = "Valid"
    area_change_pct: float = 0.0


def deduplicate_ring_coords(coords: List[Tuple[float, ...]], tolerance: float = 1e-9) -> List[Tuple[float, ...]]:
    """Removes consecutive identical or sub-tolerance duplicate coordinates without altering closure."""
    if len(coords) < 2:
        return coords

    cleaned: List[Tuple[float, ...]] = [coords[0]]
    for pt in coords[1:]:
        prev = cleaned[-1]
        dist_sq = sum((a - b) ** 2 for a, b in zip(pt[:2], prev[:2]))
        if dist_sq > (tolerance ** 2):
            cleaned.append(pt)

    return cleaned


def snap_coordinate_precision(coords: List[Tuple[float, ...]], decimals: int = 7) -> List[Tuple[float, ...]]:
    """Snaps coordinates to a defined decimal precision (~1cm in WGS84 for 7 decimals)."""
    return [tuple(round(val, decimals) for val in pt) for pt in coords]


class GeometryNormalizationService:
    """
    Normalizes and validates cadastral geometries.
    Audits every transformation so repairs are traceable.
    """

    @classmethod
    def normalize_geojson(
        cls,
        geojson_dict: Dict[str, Any],
        snap_decimals: int = 7,
        allow_multipolygon: bool = True
    ) -> NormalizationResult:
        """
        Normalizes a GeoJSON Polygon or MultiPolygon.
        Validates structure, enforces ring closure, deduplicates vertices,
        orients exterior/interior rings, snaps precision, and validates topology.
        """
        if not isinstance(geojson_dict, dict):
            raise InvalidGeometryException("GeoJSON payload must be a JSON dictionary.")

        geom_type = geojson_dict.get("type")
        if geom_type not in ("Polygon", "MultiPolygon"):
            raise InvalidGeometryException(
                f"Expected GeoJSON geometry type 'Polygon' or 'MultiPolygon', got '{geom_type}'"
            )

        if not allow_multipolygon and geom_type == "MultiPolygon":
            raise InvalidGeometryException("MultiPolygon is not permitted for this cadastral entity.")

        raw_coords = geojson_dict.get("coordinates")
        if not raw_coords:
            raise InvalidGeometryException("Geometry contains no coordinates (empty).")

        repairs: List[str] = []

        # 1. Coordinate level pre-cleaning and ring closure
        cleaned_coords, pre_repairs = cls._clean_coordinates(geom_type, raw_coords, snap_decimals)
        repairs.extend(pre_repairs)

        pre_geojson = {"type": geom_type, "coordinates": cleaned_coords}

        # 2. Shapely instantiation
        try:
            geom = shape(pre_geojson)
        except Exception as e:
            raise InvalidGeometryException(f"Failed to parse cleaned coordinates into geometry: {str(e)}")

        if geom.is_empty:
            raise InvalidGeometryException("Geometry evaluates to empty.")

        # 3. MultiPolygon handling: flatten single-part MultiPolygon to Polygon if appropriate
        if isinstance(geom, MultiPolygon):
            if len(geom.geoms) == 1 and not allow_multipolygon:
                geom = geom.geoms[0]
                repairs.append("FLATTENED_SINGLE_MULTIPOLYGON_TO_POLYGON")

        # 4. Topological validation & safe healing
        initial_area = abs(geom.area)
        was_repaired = len(repairs) > 0

        if not geom.is_valid:
            validity_reason = explain_validity(geom)
            # Safe repair using shapely.make_valid (available in Shapely 2.x)
            healed = shapely.make_valid(geom)
            
            # If make_valid results in GeometryCollection, extract polygons
            if healed.geom_type == "GeometryCollection":
                polys = [g for g in healed.geoms if isinstance(g, (Polygon, MultiPolygon))]
                if polys:
                    healed = shapely.unary_union(polys)
                else:
                    raise InvalidGeometryException(
                        f"Cannot heal invalid geometry ({validity_reason}): non-polygonal output."
                    )

            if isinstance(healed, (Polygon, MultiPolygon)) and healed.is_valid and not healed.is_empty:
                healed_area = abs(healed.area)
                area_diff = abs(healed_area - initial_area)
                pct_change = (area_diff / initial_area * 100.0) if initial_area > 0 else 0.0

                # Reject repair if it changes area drastically (> 5%), indicating boundary distortion
                if pct_change > 5.0:
                    raise InvalidGeometryException(
                        f"Geometry repair rejected: alteration would change cadastral area by {pct_change:.2f}% "
                        f"(original reason: {validity_reason})"
                    )

                geom = healed
                was_repaired = True
                repairs.append(f"MAKE_VALID_APPLIED (original: {validity_reason})")
            else:
                raise InvalidGeometryException(f"Invalid geometry could not be safely repaired: {validity_reason}")

        # 5. Orientation normalization: CCW for exterior, CW for interiors (OGC Standard)
        if isinstance(geom, Polygon):
            geom = orient(geom, sign=1.0)
            repairs.append("ORIENTATION_NORMALIZED")
        elif isinstance(geom, MultiPolygon):
            oriented_polys = [orient(p, sign=1.0) for p in geom.geoms]
            geom = MultiPolygon(oriented_polys)
            repairs.append("ORIENTATION_NORMALIZED")

        # Calculate final area change
        final_area = abs(geom.area)
        final_pct_change = round(
            abs(final_area - initial_area) / initial_area * 100.0, 4
        ) if initial_area > 0 else 0.0

        return NormalizationResult(
            geometry=geom,
            geojson=mapping(geom),
            is_valid=True,
            was_repaired=was_repaired,
            repair_actions=repairs,
            validation_message="Valid and normalized",
            area_change_pct=final_pct_change
        )

    @classmethod
    def _clean_coordinates(
        cls,
        geom_type: str,
        coords: Any,
        decimals: int
    ) -> Tuple[Any, List[str]]:
        """Cleans rings, validates WGS84 ranges, deduplicates vertices, and snaps precision."""
        repairs: List[str] = []

        def process_ring(ring_coords: List[List[float]]) -> List[Tuple[float, ...]]:
            if len(ring_coords) < 3:
                raise InvalidGeometryException("A linear ring must contain at least 3 distinct coordinate points.")

            # Validate range
            for pt in ring_coords:
                validate_wgs84_coordinates(pt[0], pt[1])

            pts = [tuple(pt) for pt in ring_coords]
            
            # Snap precision
            snapped = snap_coordinate_precision(pts, decimals)
            if snapped != pts:
                repairs.append("PRECISION_SNAPPED")

            # Remove consecutive duplicates
            deduped = deduplicate_ring_coords(snapped)
            if len(deduped) != len(snapped):
                repairs.append("DUPLICATE_VERTICES_REMOVED")

            # Check closure
            if deduped[0][:2] != deduped[-1][:2]:
                deduped.append(deduped[0])
                repairs.append("RING_CLOSED")

            if len(deduped) < 4:
                raise InvalidGeometryException(
                    "Ring has fewer than 4 points after deduplication (degenerate linear ring)."
                )

            return deduped

        if geom_type == "Polygon":
            cleaned_polygon = []
            for ring in coords:
                cleaned_polygon.append([list(p) for p in process_ring(ring)])
            return cleaned_polygon, list(set(repairs))

        elif geom_type == "MultiPolygon":
            cleaned_mp = []
            for poly in coords:
                poly_rings = []
                for ring in poly:
                    poly_rings.append([list(p) for p in process_ring(ring)])
                cleaned_mp.append(poly_rings)
            return cleaned_mp, list(set(repairs))

        return coords, repairs
