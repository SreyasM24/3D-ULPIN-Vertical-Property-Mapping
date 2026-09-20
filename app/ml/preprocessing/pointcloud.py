"""
Point Cloud Preprocessing Abstraction for LiDAR (LAS/LAZ).
Supports metadata inspection, point count, bounds extraction, CRS detection,
and ground/non-ground separation abstractions with graceful fallback.
"""

from typing import Dict, Any, Optional, List, Tuple
import os

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


class PointCloudPreprocessor:
    """
    Lightweight point cloud preprocessor for airborne/UAV LiDAR datasets.
    Gracefully inspects metadata from raw files or metadata descriptors without
    requiring heavyweight native binary dependencies.
    """

    @classmethod
    def get_capabilities(cls) -> Dict[str, bool]:
        return {
            "has_laspy": HAS_LASPY,
            "has_pdal": HAS_PDAL,
            "has_open3d": HAS_OPEN3D,
        }

    @classmethod
    def inspect_pointcloud(cls, source: Any) -> Dict[str, Any]:
        """
        Inspects point cloud metadata from a dictionary specification or a file path.
        Returns standardized metadata: bounds, point_count, CRS, vertical datum.
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
            # File path
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
                        return {
                            "file_name": os.path.basename(source),
                            "point_count": hdr.point_count,
                            "las_version": f"{hdr.version.major}.{hdr.version.minor}",
                            "bounds_bbox": bounds,
                            "min_z": bounds[2],
                            "max_z": bounds[5],
                            "estimated_height_range_m": round(bounds[5] - bounds[2], 3),
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
                    "message": "Direct binary LAS parsing requires 'laspy' or 'pdal'. Optional library not installed.",
                    "backend": "UNAVAILABLE"
                }

        return {
            "status": "INVALID_INPUT",
            "error": "Source must be a metadata dictionary or valid file path"
        }

    @classmethod
    def estimate_ground_and_surface(
        cls,
        pointcloud_info: Dict[str, Any],
        footprint_bbox: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Estimates ground elevation reference and top elevation from point cloud data.
        """
        bounds = pointcloud_info.get("bounds_bbox", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        min_z = float(bounds[2])
        max_z = float(bounds[5])
        height = max(0.0, round(max_z - min_z, 3))

        # Check classification if available (ASPRS: 2=Ground, 6=Building)
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
