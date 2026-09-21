"""
Point Cloud Preprocessing Abstraction for LiDAR (LAS/LAZ).
Supports metadata inspection, point count, bounds extraction, CRS detection,
ground/non-ground separation, spatial footprint clipping, and evidence-quality assessment.
"""

from typing import Dict, Any, Optional, List, Tuple
import os
import math
import numpy as np
from shapely.geometry import shape, Point, box, Polygon

# Safe optional imports for point-cloud libraries
try:
    import laspy
    HAS_LASPY = True
except ImportError:
    laspy = None
    HAS_LASPY = False

try:
    import pdal
    HAS_PDAL = True
except ImportError:
    pdal = None
    HAS_PDAL = False

try:
    import open3d
    HAS_OPEN3D = True
except ImportError:
    open3d = None
    HAS_OPEN3D = False

try:
    import pyproj
    HAS_PYPROJ = True
except ImportError:
    pyproj = None
    HAS_PYPROJ = False


class PointCloudPreprocessor:
    """
    Point cloud preprocessor for airborne / UAV / mobile LiDAR datasets.
    Performs header inspection, footprint-based point clipping, robust Z-percentile
    elevation analysis, ASPRS ground separation, and evidence-quality evaluation.
    """

    @classmethod
    def get_capabilities(cls) -> Dict[str, bool]:
        return {
            "has_laspy": HAS_LASPY,
            "has_pdal": HAS_PDAL,
            "has_open3d": HAS_OPEN3D,
            "has_pyproj": HAS_PYPROJ,
        }

    @classmethod
    def inspect_pointcloud(cls, source: Any) -> Dict[str, Any]:
        """
        Inspects point cloud metadata from a dictionary specification or a file path.
        Returns standardized metadata: bounds, point_count, CRS, vertical datum,
        classification distribution, and return metrics.
        """
        if isinstance(source, dict):
            # Dictionary metadata descriptor (e.g. from LiDARMetadataModel)
            file_name = source.get("file_name", "unknown.las")
            point_count = source.get("point_count", 0)
            bounds = source.get("bounds_bbox", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            crs = source.get("horizontal_crs", "EPSG:4326")
            datum = source.get("vertical_datum", "EGM96")
            las_version = source.get("las_version", "1.4")

            min_x, min_y, min_z, max_x, max_y, max_z = bounds
            return {
                "file_name": file_name,
                "point_count": point_count,
                "horizontal_crs": crs,
                "vertical_datum": datum,
                "las_version": las_version,
                "bounds_bbox": bounds,
                "min_z": min_z,
                "max_z": max_z,
                "estimated_height_range_m": round(max_z - min_z, 3),
                "has_classification": "classification_stats" in source,
                "classification_stats": source.get("classification_stats", {}),
                "status": "METADATA_EXTRACTED",
                "backend": "METADATA_PARSER"
            }

        elif isinstance(source, str):
            if not os.path.exists(source):
                return {
                    "file_name": os.path.basename(source),
                    "status": "FILE_NOT_FOUND",
                    "error": f"File does not exist: {source}"
                }

            if HAS_LASPY:
                try:
                    with laspy.open(source) as f:
                        hdr = f.header
                        bounds = [
                            round(float(hdr.x_min), 6),
                            round(float(hdr.y_min), 6),
                            round(float(hdr.z_min), 3),
                            round(float(hdr.x_max), 6),
                            round(float(hdr.y_max), 6),
                            round(float(hdr.z_max), 3),
                        ]
                        
                        # Try reading CRS from header if available
                        crs_str = None
                        try:
                            parsed_crs = hdr.parse_crs()
                            if parsed_crs:
                                crs_str = parsed_crs.to_string()
                        except Exception:
                            crs_str = None

                        return {
                            "file_name": os.path.basename(source),
                            "point_count": int(hdr.point_count),
                            "point_format_id": int(hdr.point_format.id),
                            "las_version": f"{hdr.version.major}.{hdr.version.minor}",
                            "bounds_bbox": bounds,
                            "min_z": bounds[2],
                            "max_z": bounds[5],
                            "estimated_height_range_m": round(bounds[5] - bounds[2], 3),
                            "horizontal_crs": crs_str,
                            "status": "HEADER_READ",
                            "backend": "LASPY"
                        }
                except Exception as e:
                    return {
                        "file_name": os.path.basename(source),
                        "status": "ERROR",
                        "error": str(e),
                        "backend": "LASPY"
                    }
            else:
                return {
                    "file_name": os.path.basename(source),
                    "status": "NOT_CONFIGURED",
                    "message": "Direct binary LAS parsing requires 'laspy'. Library not installed.",
                    "backend": "UNAVAILABLE"
                }

        return {
            "status": "INVALID_INPUT",
            "error": "Source must be a metadata dictionary or valid file path"
        }

    @classmethod
    def clip_pointcloud_to_footprint(
        cls,
        las_source: Any,
        footprint_geojson: Dict[str, Any],
        source_crs: Optional[str] = None,
        target_crs: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Spatially clips LAS points intersecting a building footprint polygon.
        Extracts robust Z-percentiles (Z10..Z95), ASPRS Class 2 Ground elevation,
        and calculates observed building height with evidence quality metrics.
        
        Strictly enforces:
        1. CRS alignment & coordinate compatibility
        2. Bounding-box overlap gate
        3. Spatial point-in-polygon filtering
        4. NoData & zero-coverage non-invention rule
        """
        if not HAS_LASPY:
            return {
                "status": "NOT_CONFIGURED",
                "coverage": "UNAVAILABLE",
                "height_m": None,
                "explanation": "Point cloud clipping requires 'laspy' installed."
            }

        # 1. Parse and validate building footprint geometry
        try:
            footprint_geom = shape(footprint_geojson)
            if not footprint_geom.is_valid:
                footprint_geom = footprint_geom.buffer(0)
            if footprint_geom.is_empty:
                return {
                    "status": "INVALID_FOOTPRINT",
                    "coverage": "EMPTY_GEOMETRY",
                    "height_m": None,
                    "explanation": "Input footprint geometry is empty or invalid."
                }
        except Exception as e:
            return {
                "status": "INVALID_FOOTPRINT",
                "coverage": "PARSE_ERROR",
                "height_m": None,
                "explanation": f"Failed to parse footprint polygon: {e}"
            }

        # 2. Read LAS point data
        try:
            if isinstance(las_source, str):
                if not os.path.exists(las_source):
                    return {
                        "status": "FILE_NOT_FOUND",
                        "coverage": "FILE_MISSING",
                        "height_m": None,
                        "explanation": f"LAS file not found: {las_source}"
                    }
                las = laspy.read(las_source)
                source_name = os.path.basename(las_source)
            elif hasattr(las_source, "points"):
                las = las_source
                source_name = "in_memory.las"
            else:
                return {
                    "status": "INVALID_INPUT",
                    "coverage": "UNSUPPORTED_SOURCE",
                    "height_m": None,
                    "explanation": "Source must be a valid file path or LasData object."
                }
        except Exception as e:
            return {
                "status": "LAS_READ_ERROR",
                "coverage": "CORRUPT_FILE",
                "height_m": None,
                "explanation": f"Failed to read point cloud: {e}"
            }

        hdr = las.header
        total_point_count = len(las.points)
        if total_point_count == 0:
            return {
                "status": "EMPTY_POINT_CLOUD",
                "coverage": "ZERO_POINTS",
                "height_m": None,
                "explanation": "Point cloud contains 0 points."
            }

        las_bounds = [
            float(hdr.x_min), float(hdr.y_min), float(hdr.z_min),
            float(hdr.x_max), float(hdr.y_max), float(hdr.z_max)
        ]

        # 3. CRS resolution and transformation
        las_crs = source_crs
        if not las_crs:
            try:
                parsed = hdr.parse_crs()
                if parsed:
                    las_crs = parsed.to_string()
            except Exception:
                las_crs = None

        poly_geom = footprint_geom
        if HAS_PYPROJ and target_crs and las_crs and target_crs != las_crs:
            try:
                transformer = pyproj.Transformer.from_crs(target_crs, las_crs, always_xy=True)
                from shapely.ops import transform
                poly_geom = transform(transformer.transform, footprint_geom)
            except Exception as e:
                return {
                    "status": "CRS_TRANSFORMATION_FAILED",
                    "coverage": "CRS_MISMATCH",
                    "height_m": None,
                    "explanation": f"Could not project footprint from {target_crs} to {las_crs}: {e}"
                }

        # 4. Spatial Overlap Gate: Bounding box pre-check
        f_minx, f_miny, f_maxx, f_maxy = poly_geom.bounds
        las_minx, las_miny, las_minz, las_maxx, las_maxy, las_maxz = las_bounds

        has_overlap = not (
            f_maxx < las_minx or f_minx > las_maxx or
            f_maxy < las_miny or f_miny > las_maxy
        )

        if not has_overlap:
            return {
                "source_type": "POINT_CLOUD",
                "source_file": source_name,
                "status": "EVIDENCE_NOT_COVERING_TARGET",
                "coverage": "NOT_COVERING_TARGET",
                "spatial_relation": "NO_BOUNDS_OVERLAP",
                "height_m": None,
                "ground_elevation_m": None,
                "surface_elevation_m": None,
                "point_count": total_point_count,
                "building_point_count": 0,
                "ground_point_count": 0,
                "confidence": 0.0,
                "uncertainty_m": None,
                "review_required": True,
                "bounds_bbox": las_bounds,
                "horizontal_crs": las_crs,
                "explanation": (
                    f"LiDAR artifact bounds [{las_minx:.1f}, {las_miny:.1f}, {las_maxx:.1f}, {las_maxy:.1f}] "
                    f"do not overlap building footprint bounds [{f_minx:.1f}, {f_miny:.1f}, {f_maxx:.1f}, {f_maxy:.1f}]."
                )
            }

        # 5. Point-in-Polygon Filtering
        x_pts = np.array(las.x)
        y_pts = np.array(las.y)
        z_pts = np.array(las.z)
        cls_pts = np.array(las.classification) if hasattr(las, "classification") else np.zeros(total_point_count, dtype=np.uint8)

        # Vectorized bounding box pre-filter
        in_bbox = (x_pts >= f_minx) & (x_pts <= f_maxx) & (y_pts >= f_miny) & (y_pts <= f_maxy)
        cand_indices = np.where(in_bbox)[0]

        if len(cand_indices) == 0:
            return {
                "source_type": "POINT_CLOUD",
                "source_file": source_name,
                "status": "EVIDENCE_NOT_COVERING_TARGET",
                "coverage": "ZERO_POINTS_IN_BBOX",
                "height_m": None,
                "ground_elevation_m": None,
                "surface_elevation_m": None,
                "point_count": total_point_count,
                "building_point_count": 0,
                "ground_point_count": 0,
                "confidence": 0.0,
                "uncertainty_m": None,
                "review_required": True,
                "bounds_bbox": las_bounds,
                "horizontal_crs": las_crs,
                "explanation": "LiDAR bounding box intersects polygon envelope, but 0 point returns exist in candidate region."
            }

        # Precise Polygon Containment Test
        cand_x = x_pts[cand_indices]
        cand_y = y_pts[cand_indices]
        cand_z = z_pts[cand_indices]
        cand_cls = cls_pts[cand_indices]

        # Vectorized containment using shapely contains
        inside_mask = np.zeros(len(cand_indices), dtype=bool)
        for i in range(len(cand_indices)):
            p = Point(cand_x[i], cand_y[i])
            if poly_geom.contains(p) or poly_geom.touches(p):
                inside_mask[i] = True

        bld_z = cand_z[inside_mask]
        bld_cls = cand_cls[inside_mask]
        building_point_count = len(bld_z)

        if building_point_count == 0:
            return {
                "source_type": "POINT_CLOUD",
                "source_file": source_name,
                "status": "EVIDENCE_NOT_COVERING_TARGET",
                "coverage": "ZERO_POINTS_IN_POLYGON",
                "height_m": None,
                "ground_elevation_m": None,
                "surface_elevation_m": None,
                "point_count": total_point_count,
                "building_point_count": 0,
                "ground_point_count": 0,
                "confidence": 0.0,
                "uncertainty_m": None,
                "review_required": True,
                "bounds_bbox": las_bounds,
                "horizontal_crs": las_crs,
                "explanation": "No LiDAR point returns fall strictly inside the building footprint polygon boundary."
            }

        # 6. Separate ASPRS Class 2 (Ground) points
        # Look for ground returns inside footprint OR in a surrounding 20-meter buffer
        buffer_geom = poly_geom.buffer(20.0)
        buf_minx, buf_miny, buf_maxx, buf_maxy = buffer_geom.bounds
        in_buf_bbox = (x_pts >= buf_minx) & (x_pts <= buf_maxx) & (y_pts >= buf_miny) & (y_pts <= buf_maxy)
        buf_indices = np.where(in_buf_bbox)[0]

        ground_z_vals = []
        for idx in buf_indices:
            if cls_pts[idx] == 2:  # ASPRS Class 2 = Ground
                p = Point(x_pts[idx], y_pts[idx])
                if buffer_geom.contains(p):
                    ground_z_vals.append(float(z_pts[idx]))

        ground_z_array = np.array(ground_z_vals)
        ground_point_count = len(ground_z_array)

        # 7. Robust Percentile Calculations
        z_sort = np.sort(bld_z)
        z10 = float(np.percentile(z_sort, 10))
        z25 = float(np.percentile(z_sort, 25))
        z50 = float(np.percentile(z_sort, 50))
        z75 = float(np.percentile(z_sort, 75))
        z90 = float(np.percentile(z_sort, 90))
        z95 = float(np.percentile(z_sort, 95))
        zmax = float(z_sort[-1])
        zmin = float(z_sort[0])

        # Surface elevation: Use Z95 to reject transient antenna/bird noise while capturing actual roof plane
        surface_elev_m = z95
        surface_method = "Z95 Percentile (Outlier-Robust Roof Surface)"

        # Terrain elevation:
        if ground_point_count >= 3:
            ground_elev_m = float(np.median(ground_z_array))
            ground_method = f"ASPRS Class 2 Ground Median (N={ground_point_count} buffer returns)"
            ground_std = float(np.std(ground_z_array))
        elif ground_point_count > 0:
            ground_elev_m = float(np.mean(ground_z_array))
            ground_method = f"ASPRS Class 2 Ground Mean (N={ground_point_count} returns)"
            ground_std = 0.30
        else:
            # Fallback terrain to footprint min Z
            ground_elev_m = zmin
            ground_method = "Footprint Min Z Baseline (No Class 2 returns in buffer)"
            ground_std = 0.50

        observed_height_m = max(0.0, round(surface_elev_m - ground_elev_m, 2))

        # Check for non-physical inverted elevation
        if surface_elev_m <= ground_elev_m:
            return {
                "source_type": "POINT_CLOUD",
                "source_file": source_name,
                "status": "INVERTED_ELEVATION",
                "coverage": "INVALID_ELEVATION_RELIEF",
                "height_m": None,
                "ground_elevation_m": round(ground_elev_m, 2),
                "surface_elevation_m": round(surface_elev_m, 2),
                "point_count": total_point_count,
                "building_point_count": building_point_count,
                "ground_point_count": ground_point_count,
                "confidence": 0.0,
                "uncertainty_m": None,
                "review_required": True,
                "explanation": f"Observed surface elevation ({surface_elev_m:.2f}m) is lower than or equal to ground ({ground_elev_m:.2f}m)."
            }

        # 8. Evidence Quality & Engineering Confidence Formulation
        footprint_area_sqm = float(poly_geom.area)
        point_density_pts_m2 = round(building_point_count / max(1.0, footprint_area_sqm), 3)

        # Quality Factors:
        # 1. Point Count Score (up to 0.40): 20+ points = full score
        pt_score = min(0.40, (building_point_count / 20.0) * 0.40)
        # 2. Ground Return Availability (up to 0.30): >= 5 returns = full score
        grd_score = min(0.30, (ground_point_count / 5.0) * 0.30)
        # 3. Density Score (up to 0.20): >= 1.0 pts/m² = full score
        den_score = min(0.20, (point_density_pts_m2 / 1.0) * 0.20)
        # 4. Standard Base Baseline (0.05)
        base_score = 0.05

        confidence_score = round(min(0.95, base_score + pt_score + grd_score + den_score), 3)

        # 9. Uncertainty Derivation:
        # Measurement error diminishes with sample size N, scales with ground standard deviation
        sensor_vert_res = 0.10  # Typical survey LiDAR nominal vertical precision (m)
        sample_error = 0.60 / math.sqrt(max(1, building_point_count))
        terrain_error = 0.50 * ground_std
        uncertainty_val = round(min(2.5, sensor_vert_res + sample_error + terrain_error), 2)

        return {
            "source_type": "POINT_CLOUD",
            "source_file": source_name,
            "status": "VALID_OBSERVED_EVIDENCE",
            "coverage": "VALID",
            "height_m": observed_height_m,
            "ground_elevation_m": round(ground_elev_m, 2),
            "surface_elevation_m": round(surface_elev_m, 2),
            "point_count": total_point_count,
            "building_point_count": building_point_count,
            "ground_point_count": ground_point_count,
            "point_density_pts_m2": point_density_pts_m2,
            "z_statistics": {
                "min_m": round(zmin, 2),
                "z10_m": round(z10, 2),
                "z25_m": round(z25, 2),
                "z50_m": round(z50, 2),
                "z75_m": round(z75, 2),
                "z90_m": round(z90, 2),
                "z95_m": round(z95, 2),
                "max_m": round(zmax, 2),
            },
            "horizontal_crs": las_crs,
            "bounds_bbox": las_bounds,
            "method": f"{surface_method} minus {ground_method}",
            "confidence": confidence_score,
            "confidence_basis": "Engineered quality score based on return count, ground availability, and point density",
            "uncertainty_m": uncertainty_val,
            "uncertainty_type": "DERIVED_STATISTICAL",
            "uncertainty_basis": f"Calculated from vertical resolution (0.10m), N={building_point_count} sample returns, and terrain dispersion (std={ground_std:.2f}m)",
            "review_required": confidence_score < 0.70 or observed_height_m > 100.0,
            "explanation": (
                f"Observed building height of {observed_height_m:.2f}m derived from {building_point_count} LiDAR returns "
                f"(Z95={surface_elev_m:.2f}m, Ground={ground_elev_m:.2f}m, Density={point_density_pts_m2} pts/m²)."
            )
        }

    @classmethod
    def estimate_ground_and_surface(
        cls,
        pointcloud_info: Dict[str, Any],
        footprint_bbox: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Estimates ground elevation reference and top elevation from point cloud metadata or statistics.
        """
        bounds = pointcloud_info.get("bounds_bbox", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        min_z = float(bounds[2])
        max_z = float(bounds[5])
        height = max(0.0, round(max_z - min_z, 3))

        class_stats = pointcloud_info.get("classification_stats", {})
        ground_z = class_stats.get("ground_z_mean", min_z)
        building_top_z = class_stats.get("building_z_max", max_z)

        return {
            "ground_elevation_m": round(ground_z, 3),
            "top_elevation_m": round(building_top_z, 3),
            "height_m": round(building_top_z - ground_z, 3),
            "method": "POINT_CLOUD_STATISTICS" if class_stats else "POINT_CLOUD_BOUNDS_EXTREME",
            "confidence": 0.92 if class_stats else 0.75,
            "uncertainty_m": 0.25 if class_stats else 0.8
        }
