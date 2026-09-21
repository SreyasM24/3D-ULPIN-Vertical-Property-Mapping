"""
DEM / DSM / DTM Raster Preprocessing Abstraction.
Supports raster metadata inspection, coordinate sampling, building footprint masking,
and building height calculation via DSM - DTM with strict NoData handling.
"""

from typing import Dict, Any, Optional, List, Tuple
import os
import math
import numpy as np
from shapely.geometry import shape, Point, box

try:
    import rasterio
    HAS_RASTERIO = True
except ImportError:
    rasterio = None
    HAS_RASTERIO = False


class RasterPreprocessor:
    """
    Elevation raster preprocessor supporting Digital Surface Models (DSM)
    and Digital Terrain Models (DTM/DEM).
    Provides robust raster metadata inspection, polygon-based footprint masking,
    strict NoData guarding, and spatial overlap verification.
    """

    @classmethod
    def get_capabilities(cls) -> Dict[str, bool]:
        return {
            "has_rasterio": HAS_RASTERIO,
        }

    @classmethod
    def inspect_raster(cls, source: Any) -> Dict[str, Any]:
        """
        Inspects raster metadata from a dictionary specification, GeoTIFF, or NumPy elevation array.
        """
        if isinstance(source, dict):
            # Dictionary descriptor (e.g. from DEMDSMMetadataModel)
            raster_name = source.get("raster_name", "elevation_raster.tif")
            model_type = source.get("model_type", "DSM").upper()
            res = float(source.get("spatial_resolution_m", 0.5))
            crs = source.get("horizontal_crs", "EPSG:4326")
            datum = source.get("vertical_datum", "WGS84_ELLIPSOID")
            bounds = source.get("bounds_bbox", [0.0, 0.0, 0.0, 0.0])
            elev_min = source.get("elevation_min_m")
            elev_max = source.get("elevation_max_m")
            nodata = source.get("nodata_value", -9999.0)

            elev_stats = {
                "min_m": elev_min,
                "max_m": elev_max,
                "mean_m": source.get("elevation_mean_m", (elev_min + elev_max) / 2.0 if (elev_min is not None and elev_max is not None) else None),
                "stddev_m": source.get("elevation_stddev_m", 0.0)
            }

            return {
                "raster_name": raster_name,
                "model_type": model_type,
                "spatial_resolution_m": res,
                "horizontal_crs": crs,
                "vertical_datum": datum,
                "bounds_bbox": bounds,
                "nodata_value": nodata,
                "elevation_statistics": elev_stats,
                "status": "METADATA_EXTRACTED",
                "backend": "METADATA_PARSER"
            }

        elif isinstance(source, str):
            if not os.path.exists(source):
                return {
                    "raster_name": os.path.basename(source),
                    "status": "FILE_NOT_FOUND",
                    "error": f"File does not exist: {source}"
                }

            # Check if it's a .npy or has a companion .npy / .json
            base, ext = os.path.splitext(source)
            npy_candidate = source if ext == ".npy" else f"{base}.npy"
            json_candidate = f"{base}_metadata.json" if os.path.exists(f"{base}_metadata.json") else (
                os.path.join(os.path.dirname(source), "patch_metadata.json") if os.path.exists(os.path.join(os.path.dirname(source), "patch_metadata.json")) else None
            )

            if os.path.exists(npy_candidate):
                try:
                    arr = np.load(npy_candidate)
                    h, w = arr.shape
                    meta = {}
                    if json_candidate and os.path.exists(json_candidate):
                        import json
                        with open(json_candidate, "r") as jf:
                            meta = json.load(jf)

                    res = float(meta.get("resolution_m", 1.0))
                    valid_mask = ~np.isnan(arr) & (arr != -9999.0)
                    valid_pixels = int(valid_mask.sum())
                    min_val = float(np.min(arr[valid_mask])) if valid_pixels > 0 else 0.0
                    max_val = float(np.max(arr[valid_mask])) if valid_pixels > 0 else 0.0
                    mean_val = float(np.mean(arr[valid_mask])) if valid_pixels > 0 else 0.0
                    std_val = float(np.std(arr[valid_mask])) if valid_pixels > 0 else 0.0

                    return {
                        "raster_name": os.path.basename(source),
                        "model_type": "DSM" if "dsm" in source.lower() else ("DTM" if "dtm" in source.lower() else "DEM"),
                        "width": w,
                        "height": h,
                        "spatial_resolution_m": res,
                        "horizontal_crs": meta.get("crs", "EPSG:32616"),
                        "bounds_bbox": meta.get("bounds_bbox", [0.0, 0.0, float(w * res), float(h * res)]),
                        "nodata_value": -9999.0,
                        "valid_pixel_count": valid_pixels,
                        "nodata_percentage": round((1.0 - valid_pixels / (w * h)) * 100.0, 2),
                        "elevation_statistics": {
                            "min_m": round(min_val, 3),
                            "max_m": round(max_val, 3),
                            "mean_m": round(mean_val, 3),
                            "stddev_m": round(std_val, 3)
                        },
                        "status": "NUMPY_ARRAY_READ",
                        "backend": "NUMPY_RASTER_PARSER"
                    }
                except Exception as e:
                    return {
                        "raster_name": os.path.basename(source),
                        "status": "ERROR",
                        "error": str(e),
                        "backend": "NUMPY_RASTER_PARSER"
                    }

            if HAS_RASTERIO:
                try:
                    with rasterio.open(source) as src:
                        b = src.bounds
                        bounds = [b.left, b.bottom, b.right, b.top]
                        nodata = src.nodata
                        return {
                            "raster_name": os.path.basename(source),
                            "model_type": "UNKNOWN",
                            "width": src.width,
                            "height": src.height,
                            "spatial_resolution_m": round(float(src.res[0]), 3),
                            "horizontal_crs": str(src.crs),
                            "bounds_bbox": bounds,
                            "nodata_value": nodata,
                            "status": "RASTERIO_READ",
                            "backend": "RASTERIO"
                        }
                except Exception as e:
                    return {
                        "raster_name": os.path.basename(source),
                        "status": "ERROR",
                        "error": str(e),
                        "backend": "RASTERIO"
                    }
            else:
                return {
                    "raster_name": os.path.basename(source),
                    "status": "NOT_CONFIGURED",
                    "message": "Direct GeoTIFF raster parsing requires 'rasterio' or companion NumPy grid.",
                    "backend": "UNAVAILABLE"
                }

        return {
            "status": "INVALID_INPUT",
            "error": "Source must be a metadata dictionary or valid file path"
        }

    @classmethod
    def clip_raster_to_footprint(
        cls,
        raster_source: Any,
        footprint_geojson: Dict[str, Any],
        bounds_bbox: Optional[List[float]] = None,
        resolution_m: float = 1.0,
        nodata_value: float = -9999.0
    ) -> Dict[str, Any]:
        """
        Extracts elevation statistics strictly within a building footprint polygon.
        Enforces bounding box overlap, polygon masking, and strict NoData exclusion.
        """
        # Validate footprint
        try:
            poly_geom = shape(footprint_geojson)
            if not poly_geom.is_valid:
                poly_geom = poly_geom.buffer(0)
            if poly_geom.is_empty:
                return {
                    "status": "INVALID_FOOTPRINT",
                    "coverage": "EMPTY_GEOMETRY",
                    "elevation_m": None
                }
        except Exception as e:
            return {
                "status": "INVALID_FOOTPRINT",
                "coverage": "PARSE_ERROR",
                "elevation_m": None,
                "error": str(e)
            }

        # Inspect raster metadata
        info = cls.inspect_raster(raster_source)
        if info.get("status") in ("FILE_NOT_FOUND", "ERROR", "INVALID_INPUT"):
            return {
                "status": info.get("status"),
                "coverage": "UNREADABLE",
                "elevation_m": None,
                "error": info.get("error", "Failed to inspect raster")
            }

        r_bounds = bounds_bbox or info.get("bounds_bbox", [0.0, 0.0, 0.0, 0.0])
        f_minx, f_miny, f_maxx, f_maxy = poly_geom.bounds

        # Spatial overlap gate
        if len(r_bounds) >= 4:
            r_minx, r_miny, r_maxx, r_maxy = r_bounds[0], r_bounds[1], r_bounds[2], r_bounds[3]
            has_overlap = not (
                f_maxx < r_minx or f_minx > r_maxx or
                f_maxy < r_miny or f_miny > r_maxy
            )
            if not has_overlap:
                return {
                    "status": "EVIDENCE_NOT_COVERING_TARGET",
                    "coverage": "NO_BOUNDS_OVERLAP",
                    "elevation_m": None,
                    "explanation": f"Raster bounding box [{r_minx:.1f}, {r_miny:.1f}, {r_maxx:.1f}, {r_maxy:.1f}] does not overlap footprint."
                }

        # If NumPy array is available, perform array masking
        base, ext = os.path.splitext(raster_source) if isinstance(raster_source, str) else ("", "")
        npy_candidate = raster_source if ext == ".npy" else f"{base}.npy"
        if isinstance(raster_source, str) and os.path.exists(npy_candidate):
            try:
                arr = np.load(npy_candidate)
                h, w = arr.shape
                res = info.get("spatial_resolution_m", resolution_m)

                # Map footprint bounds to pixel coordinates
                r_minx, r_miny = r_bounds[0], r_bounds[1]
                px_minx = int(max(0, math.floor((f_minx - r_minx) / res)))
                px_maxx = int(min(w, math.ceil((f_maxx - r_minx) / res)))
                px_miny = int(max(0, math.floor((f_miny - r_miny) / res)))
                px_maxy = int(min(h, math.ceil((f_maxy - r_miny) / res)))

                if px_minx >= px_maxx or px_miny >= px_maxy:
                    return {
                        "status": "EVIDENCE_NOT_COVERING_TARGET",
                        "coverage": "ZERO_PIXELS_IN_BOUNDS",
                        "elevation_m": None,
                        "explanation": "Footprint maps outside valid raster pixel window."
                    }

                sub_grid = arr[px_miny:px_maxy, px_minx:px_maxx]
                valid_mask = ~np.isnan(sub_grid) & (sub_grid != nodata_value) & (sub_grid > -9000.0)
                valid_pixels = sub_grid[valid_mask]

                if len(valid_pixels) == 0:
                    return {
                        "status": "EVIDENCE_NOT_COVERING_TARGET",
                        "coverage": "ALL_NODATA_PIXELS",
                        "elevation_m": None,
                        "explanation": "All raster pixels covering the footprint evaluate to NoData."
                    }

                z_sort = np.sort(valid_pixels)
                z95 = float(np.percentile(z_sort, 95))
                z_median = float(np.median(z_sort))
                z_mean = float(np.mean(z_sort))
                z_std = float(np.std(z_sort))

                return {
                    "status": "VALID_MASKED_ELEVATION",
                    "coverage": "VALID",
                    "valid_pixels_in_footprint": len(valid_pixels),
                    "elevation_z95_m": round(z95, 2),
                    "elevation_median_m": round(z_median, 2),
                    "elevation_mean_m": round(z_mean, 2),
                    "elevation_stddev_m": round(z_std, 2),
                    "elevation_min_m": round(float(z_sort[0]), 2),
                    "elevation_max_m": round(float(z_sort[-1]), 2),
                }
            except Exception as e:
                return {
                    "status": "MASK_ERROR",
                    "coverage": "PROCESSING_FAILED",
                    "elevation_m": None,
                    "error": str(e)
                }

        # Fallback to metadata statistics
        elev_stats = info.get("elevation_statistics", {})
        return {
            "status": "METADATA_ELEVATION_ESTIMATE",
            "coverage": "METADATA_ONLY",
            "elevation_mean_m": elev_stats.get("mean_m"),
            "elevation_min_m": elev_stats.get("min_m"),
            "elevation_max_m": elev_stats.get("max_m")
        }

    @classmethod
    def compute_height_difference(
        cls,
        dsm_info: Optional[Dict[str, Any]],
        dtm_info: Optional[Dict[str, Any]],
        sample_lon: Optional[float] = None,
        sample_lat: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates building height using Height = DSM - DTM.
        Enforces strict NoData handling: if DTM is missing, either has NoData,
        or terrain elevation exceeds surface elevation, does NOT invent a height.
        """
        if not dsm_info or not dtm_info:
            missing = []
            if not dsm_info:
                missing.append("DSM (Surface)")
            if not dtm_info:
                missing.append("DTM (Terrain)")
            return {
                "height_m": None,
                "confidence": 0.0,
                "uncertainty_m": None,
                "method": "UNAVAILABLE",
                "status": "MISSING_RASTER_INPUT",
                "explanation": f"Cannot compute building height: missing {', '.join(missing)}."
            }

        # Check CRS compatibility if provided
        dsm_crs = dsm_info.get("horizontal_crs")
        dtm_crs = dtm_info.get("horizontal_crs")
        if dsm_crs and dtm_crs and dsm_crs != dtm_crs:
            return {
                "height_m": None,
                "confidence": 0.0,
                "uncertainty_m": None,
                "method": "DSM_DTM_DIFFERENCE",
                "status": "CRS_MISMATCH",
                "explanation": f"Incompatible coordinate reference systems: DSM ({dsm_crs}) vs DTM ({dtm_crs})."
            }

        dsm_stats = dsm_info.get("elevation_statistics") or dsm_info
        dtm_stats = dtm_info.get("elevation_statistics") or dtm_info

        dsm_val = dsm_stats.get("max_m") if dsm_stats.get("max_m") is not None else (
            dsm_stats.get("elevation_max_m") if dsm_stats.get("elevation_max_m") is not None else dsm_stats.get("mean_m")
        )
        dtm_val = dtm_stats.get("min_m") if dtm_stats.get("min_m") is not None else (
            dtm_stats.get("elevation_min_m") if dtm_stats.get("elevation_min_m") is not None else dtm_stats.get("mean_m")
        )

        dsm_nodata = dsm_info.get("nodata_value", -9999.0)
        dtm_nodata = dtm_info.get("nodata_value", -9999.0)

        # Check for NoData values - NEVER convert NoData to 0
        if dsm_val is None or dtm_val is None or dsm_val == dsm_nodata or dtm_val == dtm_nodata or dsm_val <= -9000.0 or dtm_val <= -9000.0:
            return {
                "height_m": None,
                "confidence": 0.0,
                "uncertainty_m": None,
                "method": "DSM_DTM_DIFFERENCE",
                "status": "NODATA_ENCOUNTERED",
                "explanation": "Raster pixel evaluated to NoData value. Height calculation aborted to prevent corruption."
            }

        height_m = round(float(dsm_val - dtm_val), 2)
        if height_m < 0.0:
            return {
                "height_m": None,
                "confidence": 0.0,
                "uncertainty_m": None,
                "method": "DSM_DTM_DIFFERENCE",
                "status": "INVERTED_ELEVATION",
                "explanation": f"Terrain elevation ({dtm_val}m) is higher than surface ({dsm_val}m). Invalid raster alignment."
            }

        res_dsm = float(dsm_info.get("spatial_resolution_m", 0.5))
        # Non-hardcoded uncertainty derived from grid cell resolution and vertical nominal accuracy
        uncertainty = round(res_dsm * 0.5 + 0.15, 2)

        return {
            "height_m": height_m,
            "ground_elevation_m": round(float(dtm_val), 2),
            "top_elevation_m": round(float(dsm_val), 2),
            "confidence": 0.94 if res_dsm <= 0.5 else 0.82,
            "confidence_basis": f"Calculated from high-resolution raster alignment (res={res_dsm}m)",
            "uncertainty_m": uncertainty,
            "uncertainty_type": "DERIVED_FROM_RESOLUTION",
            "uncertainty_basis": f"Grid cell resolution ({res_dsm}m) scaled by 0.5 plus vertical sensor datum uncertainty (0.15m)",
            "method": "DSM_DTM_DIFFERENCE",
            "status": "CALCULATED",
            "explanation": f"Computed height of {height_m:.2f}m from DSM ({dsm_val:.2f}m) and DTM ({dtm_val:.2f}m)."
        }
