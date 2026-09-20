"""
DEM / DSM / DTM Raster Preprocessing Abstraction.
Supports raster metadata extraction, coordinate sampling, and building height
calculation via DSM - DTM with strict NoData handling.
"""

from typing import Dict, Any, Optional, List, Tuple
import os

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
    """

    @classmethod
    def get_capabilities(cls) -> Dict[str, bool]:
        return {
            "has_rasterio": HAS_RASTERIO,
        }

    @classmethod
    def inspect_raster(cls, source: Any) -> Dict[str, Any]:
        """
        Inspects raster metadata from a dictionary specification or a GeoTIFF file.
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
                "mean_m": source.get("elevation_mean_m", (elev_min + elev_max) / 2.0 if (elev_min and elev_max) else None),
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
                    "message": "Direct GeoTIFF raster parsing requires 'rasterio'. Optional library not installed.",
                    "backend": "UNAVAILABLE"
                }

        return {
            "status": "INVALID_INPUT",
            "error": "Source must be a metadata dictionary or valid file path"
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
        Enforces strict NoData handling: if DTM is missing or either has NoData,
        does NOT invent a height and flags explicit uncertainty.
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

        # Check model types
        dsm_type = str(dsm_info.get("model_type", "DSM")).upper()
        dtm_type = str(dtm_info.get("model_type", "DTM")).upper()

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
        if dsm_val is None or dtm_val is None or dsm_val == dsm_nodata or dtm_val == dtm_nodata:
            return {
                "height_m": None,
                "confidence": 0.0,
                "uncertainty_m": None,
                "method": "DSM_DTM_DIFFERENCE",
                "status": "NODATA_ENCOUNTERED",
                "explanation": "Raster pixel evaluated to NoData value. Height calculation aborted to prevent corruption."
            }

        height_m = round(float(dsm_val - dtm_val), 3)
        if height_m < 0.0:
            return {
                "height_m": None,
                "confidence": 0.0,
                "uncertainty_m": None,
                "method": "DSM_DTM_DIFFERENCE",
                "status": "INVERTED_ELEVATION",
                "explanation": f"Terrain elevation ({dtm_val}m) is higher than surface ({dsm_val}m). Invalid raster alignment."
            }

        res_dsm = dsm_info.get("spatial_resolution_m", 0.5)
        uncertainty = round(res_dsm * 0.5 + 0.15, 2)

        return {
            "height_m": height_m,
            "ground_elevation_m": round(float(dtm_val), 3),
            "top_elevation_m": round(float(dsm_val), 3),
            "confidence": 0.94 if res_dsm <= 0.5 else 0.82,
            "uncertainty_m": uncertainty,
            "method": "DSM_DTM_DIFFERENCE",
            "status": "CALCULATED",
            "explanation": f"Computed height of {height_m:.2f}m from DSM ({dsm_val:.2f}m) and DTM ({dtm_val:.2f}m)."
        }
