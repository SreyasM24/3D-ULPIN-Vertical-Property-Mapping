"""
Advanced 3D Cadastral Clash & Volumetric Overlap Analysis Engine.
Calculates metric 3D overlap volumes, vertical depths, and context-aware
classifications (CRITICAL, WARNING, INFO, UNKNOWN_REQUIRES_REVIEW).
"""

from typing import List, Dict, Any, Optional
from shapely.geometry import shape, Polygon, MultiPolygon
from app.core.crs import (
    WGS84_CRS,
    project_geometry,
    get_utm_epsg_for_point,
)
from app.services.spatial_engine import geojson_to_shapely
from app.schemas.validation import ClashClassification, DetailedClashFinding


class AdvancedClashEngine:
    """
    Rigorously detects and classifies 3D volumetric intersections between cadastral units,
    distinguishing true ownership collisions from shared infrastructure and common spaces.
    """

    COMMON_OR_INFRA_TYPES = {
        "COMMON_AREA", "UTILITY", "TUNNEL", "ELEVATED_STRUCTURE", "STAIRWELL", "ELEVATOR_SHAFT"
    }

    PRIVATE_PROPERTY_TYPES = {
        "APARTMENT", "OFFICE", "SHOP", "COMMERCIAL", "RESIDENTIAL", "PARKING"
    }

    @classmethod
    def analyze_unit_clashes(
        cls,
        units: List[Dict[str, Any]],
        tolerance_overlap_m: float = 0.03,
        tolerance_area_sqm: float = 0.05,
    ) -> List[DetailedClashFinding]:
        """
        Performs pairwise volumetric collision analysis across cadastral units.
        Computes metric overlap area in projected UTM space, vertical overlap depth,
        and elevation boundaries.
        """
        findings: List[DetailedClashFinding] = []
        n = len(units)
        if n < 2:
            return findings

        # 1. Pre-parse and project geometries to local UTM
        parsed_polys = []
        utm_crs = None

        for u in units:
            try:
                poly = geojson_to_shapely(u["footprint_geojson"], auto_heal=True)
                if utm_crs is None and not poly.is_empty:
                    c = poly.centroid
                    utm_crs = get_utm_epsg_for_point(c.y, c.x)
                proj_poly, _ = project_geometry(poly, src_crs=WGS84_CRS, dst_crs=utm_crs)
                parsed_polys.append(proj_poly)
            except Exception:
                parsed_polys.append(None)

        # 2. Pairwise volumetric analysis
        for i in range(n):
            u1 = units[i]
            poly1 = parsed_polys[i]
            if poly1 is None or poly1.is_empty:
                continue

            for j in range(i + 1, n):
                u2 = units[j]
                poly2 = parsed_polys[j]
                if poly2 is None or poly2.is_empty:
                    continue

                # Vertical elevation overlap
                z_min_overlap = max(u1["z_min"], u2["z_min"])
                z_max_overlap = min(u1["z_max"], u2["z_max"])
                z_depth = z_max_overlap - z_min_overlap

                if z_depth <= tolerance_overlap_m:
                    # Clear vertical clearance, no 3D intersection
                    continue

                # 2D Bounding envelope pre-check
                if not poly1.envelope.intersects(poly2.envelope):
                    continue

                # Exact 2D intersection in projected UTM space
                try:
                    inter = poly1.intersection(poly2)
                except Exception:
                    continue

                if inter.is_empty or inter.area <= 0:
                    continue

                overlap_area = round(float(abs(inter.area)), 3)
                if overlap_area <= 0.001:
                    continue

                overlap_vol = round(overlap_area * z_depth, 3)

                # Context-aware classification
                type1 = str(u1.get("unit_type", "OTHER")).upper()
                type2 = str(u2.get("unit_type", "OTHER")).upper()

                classification, explanation, suggestion = cls._classify_intersection(
                    type1, type2, overlap_area, z_depth, overlap_vol, tolerance_area_sqm, tolerance_overlap_m
                )

                findings.append(
                    DetailedClashFinding(
                        entity_a_id=str(u1.get("id")),
                        entity_a_identifier=str(u1.get("unit_number") or u1.get("ulpin_3d") or "Unit A"),
                        entity_a_type=type1,
                        entity_b_id=str(u2.get("id")),
                        entity_b_identifier=str(u2.get("unit_number") or u2.get("ulpin_3d") or "Unit B"),
                        entity_b_type=type2,
                        classification=classification,
                        horizontal_overlap_sqm=overlap_area,
                        vertical_overlap_m=round(z_depth, 3),
                        overlap_elevation_range=[round(z_min_overlap, 3), round(z_max_overlap, 3)],
                        estimated_overlap_volume_cu_m=overlap_vol,
                        explanation=explanation,
                        suggested_action=suggestion
                    )
                )

        return findings

    @classmethod
    def _classify_intersection(
        cls,
        type1: str,
        type2: str,
        overlap_area: float,
        z_depth: float,
        overlap_vol: float,
        tolerance_area: float,
        tolerance_z: float
    ) -> tuple[ClashClassification, str, str]:
        """Classifies volumetric intersection based on property type semantics and tolerance."""
        # 1. Tolerance / Near-boundary condition
        if overlap_area <= tolerance_area or z_depth <= (tolerance_z * 2):
            return (
                ClashClassification.WARNING,
                f"Minor boundary tolerance overlap ({overlap_area:.3f} m², depth: {z_depth:.3f} m). "
                "May indicate shared partition wall thickness or vertex snapping discrepancy.",
                "Review CAD/survey coordinate precision at shared party wall boundary."
            )

        # 2. Shared / Common / Infrastructure coexistence
        has_common = (type1 in cls.COMMON_OR_INFRA_TYPES) or (type2 in cls.COMMON_OR_INFRA_TYPES)
        if has_common:
            # Common area overlapping with another common area or designated utility
            if (type1 in cls.COMMON_OR_INFRA_TYPES) and (type2 in cls.COMMON_OR_INFRA_TYPES):
                return (
                    ClashClassification.INFO,
                    f"Volumetric intersection between common infrastructure elements ({type1} and {type2}). "
                    "Permissible shared utility or circulation corridor.",
                    "Verify dual-use or service easement registration if required by local building bylaws."
                )
            else:
                # Private unit overlapping with common area / utility
                return (
                    ClashClassification.UNKNOWN_REQUIRES_REVIEW,
                    f"Intersection between private unit ({type1 if type1 in cls.PRIVATE_PROPERTY_TYPES else type2}) "
                    f"and shared infrastructure ({type2 if type2 in cls.COMMON_OR_INFRA_TYPES else type1}) "
                    f"by {overlap_vol:.2f} m³. Easement or access right status is unrecorded in spatial data.",
                    "Requires cadastral review: verify if an official utility easement or common passage right is registered."
                )

        # 3. Two private property units intersecting
        if (type1 in cls.PRIVATE_PROPERTY_TYPES) and (type2 in cls.PRIVATE_PROPERTY_TYPES):
            return (
                ClashClassification.CRITICAL,
                f"Critical volumetric collision between private property units ({type1} and {type2}). "
                f"Overlaps by {overlap_area:.2f} m² horizontally and {z_depth:.2f} m vertically ({overlap_vol:.2f} m³).",
                "Immediate remediation required: adjust 3D floor plan or boundary strata to eliminate overlapping property ownership."
            )

        # 4. Unknown / Default fallback
        return (
            ClashClassification.UNKNOWN_REQUIRES_REVIEW,
            f"Volumetric intersection between '{type1}' and '{type2}' by {overlap_vol:.2f} m³. "
            "Insufficient semantic data in unit types to determine legal ownership status.",
            "Inspect physical survey documents and title deeds for both vertical units."
        )
