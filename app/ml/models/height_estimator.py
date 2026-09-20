"""
Building Height Estimator Model & Multi-Strategy Intelligence Engine.
Deterministically and adaptively resolves building height using cascading priority:
1. Observed LiDAR / DSM-DTM Difference / Survey Metadata (Highest Fidelity, Evidence-Backed)
2. Trained Neural Regressor (AI_REGRESSION via ONNX Runtime on Footprint Morphology & Terrain)
3. Deterministic Floor Count Heuristic (DETERMINISTIC_CASCADE)
4. Explicit Incomplete State (Height is never invented)
"""

from typing import Dict, Any, Optional
import os
import json
import math
import hashlib
from datetime import datetime, timezone
import numpy as np

try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:
    HAS_ORT = False

from shapely.geometry import shape
from app.ml.models.base import BaseFeatureModel
from app.ml.schemas import (
    ModelStatus,
    EvidenceSourceType,
    ConfidenceLevel,
    DataStage,
)
from app.ml.preprocessing.raster import RasterPreprocessor
from app.ml.preprocessing.pointcloud import PointCloudPreprocessor
from app.services.spatial_engine import compute_projected_spatial_metrics
from app.core.config import settings


class HeightEstimatorModel(BaseFeatureModel):
    """
    Cadastral Height Estimation Engine with Real AI Regression & Multi-Strategy Fallback.
    Transparently reports provenance (OBSERVED_LIDAR, AI_REGRESSION, DETERMINISTIC_CASCADE).
    """

    DEFAULT_ONNX_PATH = "models/height_estimator.onnx"
    DEFAULT_META_PATH = "models/height_estimator_metadata.json"

    def __init__(self, weights_path: Optional[str] = None):
        resolved_path = weights_path
        if resolved_path is None:
            candidate = os.environ.get("HEIGHT_ESTIMATOR_MODEL_PATH", self.DEFAULT_ONNX_PATH)
            if os.path.exists(candidate):
                resolved_path = candidate

        super().__init__(
            model_name="HeightEstimator_Cascade",
            model_version="1.0.0-trained" if resolved_path and os.path.exists(resolved_path) else "0.1.0-prototype",
            model_type="HEIGHT_REGRESSOR",
            weights_path=resolved_path
        )
        self.ort_session: Optional[Any] = None
        self.model_sha256: Optional[str] = None
        self.model_metadata: Dict[str, Any] = {}
        self.load()

    def load(self) -> bool:
        """
        Loads the trained ONNX regression model and validates with an operational probe.
        Gracefully falls back to DEGRADED status if weights or ONNX runtime are missing.
        """
        if not self.weights_path or not os.path.exists(self.weights_path):
            self.status = ModelStatus.NOT_CONFIGURED
            self.ort_session = None
            return False

        if not HAS_ORT:
            self.status = ModelStatus.DEGRADED
            self.ort_session = None
            return False

        try:
            self.ort_session = ort.InferenceSession(
                self.weights_path,
                providers=["CPUExecutionProvider"]
            )

            # Probe with dummy input [1, 7]
            input_name = self.ort_session.get_inputs()[0].name
            dummy_tensor = np.zeros((1, 7), dtype=np.float32)
            probe_out = self.ort_session.run(None, {input_name: dummy_tensor})[0]

            if probe_out.shape[1:] != (1,):
                raise ValueError(f"Unexpected height model output shape: {probe_out.shape}")

            with open(self.weights_path, "rb") as f:
                self.model_sha256 = hashlib.sha256(f.read()).hexdigest()

            meta_path = getattr(self, "DEFAULT_META_PATH", "models/height_estimator_metadata.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as mf:
                    self.model_metadata = json.load(mf)
                    if "model_version" in self.model_metadata:
                        self.model_version = self.model_metadata["model_version"]

            self.status = ModelStatus.ACTIVE
            self.loaded_at = datetime.now(timezone.utc)
            return True

        except Exception:
            self.status = ModelStatus.DEGRADED
            self.ort_session = None
            return False

    @property
    def backend(self) -> str:
        return "ONNX_RUNTIME" if self.status == ModelStatus.ACTIVE else "NONE"

    def health(self) -> Dict[str, Any]:
        """Returns runtime readiness and probe health for HeightEstimator."""
        base_h = super().health()
        base_h.update({
            "backend": self.backend,
            "model_sha256": self.model_sha256,
            "inference_ready": self.status == ModelStatus.ACTIVE and self.ort_session is not None,
            "metrics": self.model_metadata.get("test_metrics", {})
        })
        return base_h

    def metadata(self) -> Dict[str, Any]:
        """Exposes model descriptor, features, and evaluation benchmarks."""
        meta = super().metadata()
        meta.update({
            "backend": self.backend,
            "is_ready": self.status == ModelStatus.ACTIVE,
            "weights_sha256": self.model_sha256,
            "architecture": self.model_metadata.get("architecture", "HeightRegressorMLP"),
            "test_metrics": self.model_metadata.get("test_metrics", {}),
            "training_dataset": self.model_metadata.get("dataset", {}).get("name", "3DBAG (AHN4 LiDAR)")
        })
        return meta

    def predict(self, inputs: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """
        Executes height estimation across candidate strategies in strict priority:
        1. Observed Elevation / LiDAR / Registered Metadata (Highest Fidelity)
        2. Trained Neural Regressor (AI_REGRESSION via ONNX Runtime on Footprint & Terrain)
        3. Deterministic Floor Count Heuristic (DETERMINISTIC_CASCADE)
        4. Incomplete / Unknown State
        """
        merged_inputs = dict(inputs or {})
        merged_inputs.update(kwargs)
        inputs = merged_inputs

        # -------------------------------------------------------------------
        # Strategy 1: Observed LiDAR / DSM-DTM Difference Evidence
        # -------------------------------------------------------------------
        dsm_info = inputs.get("dsm_metadata") or inputs.get("dsm")
        dtm_info = inputs.get("dtm_metadata") or inputs.get("dtm")
        if dsm_info and dtm_info:
            res = RasterPreprocessor.compute_height_difference(dsm_info, dtm_info)
            if res.get("status") == "CALCULATED" and res.get("height_m") is not None:
                h = res["height_m"]
                conf = res.get("confidence", 0.90)
                unc = res.get("uncertainty_m", 0.3)
                return {
                    "height_m": h,
                    "ground_elevation_m": res.get("ground_elevation_m"),
                    "top_elevation_m": res.get("top_elevation_m"),
                    "uncertainty_m": unc,
                    "confidence": conf,
                    "confidence_level": ConfidenceLevel.HIGH if conf >= 0.85 else ConfidenceLevel.MEDIUM,
                    "method": "DSM_DTM_DIFFERENCE",
                    "provenance": "OBSERVED_ELEVATION_EVIDENCE",
                    "source": EvidenceSourceType.DSM_DTM,
                    "stage": DataStage.ESTIMATED,
                    "status": "SUCCESS",
                    "explanation": res.get("explanation", "Height derived directly from DSM - DTM raster difference.")
                }

        pc_info = inputs.get("pointcloud_metadata") or inputs.get("point_cloud")
        if pc_info:
            parsed = PointCloudPreprocessor.inspect_pointcloud(pc_info)
            if parsed.get("status") in ("METADATA_EXTRACTED", "HEADER_READ"):
                ground_surf = PointCloudPreprocessor.estimate_ground_and_surface(parsed)
                h = ground_surf["height_m"]
                if h > 0.0:
                    conf = ground_surf["confidence"]
                    unc = ground_surf["uncertainty_m"]
                    return {
                        "height_m": h,
                        "ground_elevation_m": ground_surf["ground_elevation_m"],
                        "top_elevation_m": ground_surf["top_elevation_m"],
                        "uncertainty_m": unc,
                        "confidence": conf,
                        "confidence_level": ConfidenceLevel.HIGH if conf >= 0.85 else ConfidenceLevel.MEDIUM,
                        "method": ground_surf["method"],
                        "provenance": "OBSERVED_LIDAR",
                        "source": EvidenceSourceType.POINT_CLOUD,
                        "stage": DataStage.ESTIMATED,
                        "status": "SUCCESS",
                        "explanation": f"Height ({h:.2f}m) estimated from observed airborne LiDAR point cloud returns."
                    }

        bld_meta = inputs.get("building_metadata") or {}
        explicit_height = bld_meta.get("total_height_m") or inputs.get("total_height_m")
        if explicit_height is not None and float(explicit_height) > 0.0:
            h = round(float(explicit_height), 2)
            ground_z = float(bld_meta.get("ground_elevation_m", inputs.get("ground_elevation_m", 0.0)) or 0.0)
            return {
                "height_m": h,
                "ground_elevation_m": ground_z,
                "top_elevation_m": round(ground_z + h, 2),
                "uncertainty_m": 0.1,
                "confidence": 0.95,
                "confidence_level": ConfidenceLevel.HIGH,
                "method": "EXPLICIT_METADATA",
                "provenance": "OBSERVED_SURVEY_METADATA",
                "source": EvidenceSourceType.BUILDING_METADATA,
                "stage": DataStage.OBSERVED,
                "status": "SUCCESS",
                "explanation": f"Building height ({h:.2f}m) obtained directly from registered survey/architectural metadata."
            }

        # -------------------------------------------------------------------
        # Strategy 2: Real Trained Neural Network Inference (AI_REGRESSION)
        # -------------------------------------------------------------------
        footprint_poly = inputs.get("footprint_geojson") or inputs.get("footprint")
        if self.status == ModelStatus.ACTIVE and self.ort_session is not None and footprint_poly:
            try:
                # Compute projected metric geometry
                spatial_metrics = compute_projected_spatial_metrics(footprint_poly)
                area_m2 = float(spatial_metrics["area_sqm"])
                perim_m = float(spatial_metrics["perimeter_m"])

                if area_m2 >= 5.0 and perim_m >= 3.0:
                    compactness = float(4.0 * math.pi * area_m2 / (perim_m ** 2)) if perim_m > 0 else 0.0
                    equiv_diam = float(math.sqrt(4.0 * area_m2 / math.pi))

                    poly_obj = shape(spatial_metrics["normalized_geojson"])
                    hull = poly_obj.convex_hull
                    convexity = float(poly_obj.area / hull.area) if (hull and hull.area > 0) else 1.0
                    aspect_ratio = float(spatial_metrics.get("aspect_ratio") or 1.0)

                    ground_z = float(bld_meta.get("ground_elevation_m", inputs.get("ground_elevation_m", 0.0)) or 0.0)

                    raw_features = np.array([
                        area_m2,
                        perim_m,
                        compactness,
                        convexity,
                        aspect_ratio,
                        equiv_diam,
                        ground_z
                    ], dtype=np.float32)

                    # Standard scaling with training statistics
                    norm_cfg = self.model_metadata.get("normalization", {})
                    means = np.array(norm_cfg.get("means", [68.16, 37.05, 0.585, 0.948, 1.20, 8.70, 0.025]), dtype=np.float32)
                    stds = np.array(norm_cfg.get("stds", [82.28, 19.71, 0.120, 0.065, 0.19, 3.33, 0.181]), dtype=np.float32)
                    stds[stds < 1e-6] = 1.0

                    norm_feats = ((raw_features - means) / stds).reshape(1, -1).astype(np.float32)

                    # Execute ONNX Runtime inference
                    input_name = self.ort_session.get_inputs()[0].name
                    pred_raw = float(self.ort_session.run(None, {input_name: norm_feats})[0][0][0])
                    clamped_h = round(float(np.clip(pred_raw, 2.0, 120.0)), 2)

                    mae_unc = self.model_metadata.get("test_metrics", {}).get("test_mae_m", 2.32)

                    return {
                        "height_m": clamped_h,
                        "ground_elevation_m": ground_z,
                        "top_elevation_m": round(ground_z + clamped_h, 2),
                        "uncertainty_m": mae_unc,
                        "confidence": 0.75,
                        "confidence_level": ConfidenceLevel.MEDIUM,
                        "method": "AI_TABULAR_REGRESSION",
                        "provenance": "AI_REGRESSION",
                        "source": EvidenceSourceType.DRONE_PHOTOGRAMMETRY,
                        "stage": DataStage.ESTIMATED,
                        "status": "SUCCESS",
                        "explanation": f"Inferred building height ({clamped_h:.2f}m) via trained neural regressor on footprint geometry.",
                        "processing_metadata": {
                            "mode": "AI_ONNX_INFERENCE",
                            "backend": "ONNX_RUNTIME",
                            "model_sha256": self.model_sha256,
                            "model_path": self.weights_path,
                            "input_features": {
                                "footprint_area_m2": round(area_m2, 2),
                                "footprint_perimeter_m": round(perim_m, 2),
                                "compactness": round(compactness, 4),
                                "convexity": round(convexity, 4),
                                "aspect_ratio": aspect_ratio,
                                "equivalent_diameter_m": round(equiv_diam, 2),
                                "terrain_elevation_m": round(ground_z, 2)
                            }
                        }
                    }
            except Exception:
                pass  # Gracefully fall through to Strategy 3

        # -------------------------------------------------------------------
        # Strategy 3: Deterministic Floor Count Fallback (DETERMINISTIC_CASCADE)
        # -------------------------------------------------------------------
        floor_count = bld_meta.get("floors_above_ground") or inputs.get("floors_above_ground") or inputs.get("floor_count")
        if floor_count is not None and int(floor_count) > 0:
            fl_count = int(floor_count)
            default_floor_h = getattr(settings, "DEFAULT_FLOOR_HEIGHT_M", 3.0)
            default_ground_h = getattr(settings, "DEFAULT_GROUND_FLOOR_HEIGHT_M", 3.8)

            estimated_h = round(default_ground_h + max(0, fl_count - 1) * default_floor_h, 2)
            ground_z = float(bld_meta.get("ground_elevation_m", inputs.get("ground_elevation_m", 0.0)) or 0.0)
            return {
                "height_m": estimated_h,
                "ground_elevation_m": ground_z,
                "top_elevation_m": round(ground_z + estimated_h, 2),
                "uncertainty_m": round(fl_count * 0.4, 2),
                "confidence": 0.60,
                "confidence_level": ConfidenceLevel.LOW,
                "method": "FLOOR_COUNT_HEURISTIC",
                "provenance": "DETERMINISTIC_CASCADE",
                "source": EvidenceSourceType.ASSUMPTION_FALLBACK,
                "stage": DataStage.ESTIMATED,
                "status": "SUCCESS",
                "explanation": f"Inferred height ({estimated_h:.2f}m) based on {fl_count} floors using default floor heights ({default_floor_h}m)."
            }

        # -------------------------------------------------------------------
        # Strategy 4: Incomplete / Unknown State
        # -------------------------------------------------------------------
        return {
            "height_m": None,
            "ground_elevation_m": None,
            "top_elevation_m": None,
            "uncertainty_m": None,
            "confidence": 0.0,
            "confidence_level": ConfidenceLevel.UNKNOWN,
            "method": "UNKNOWN",
            "provenance": "DETERMINISTIC_CASCADE",
            "source": EvidenceSourceType.UNRESOLVED,
            "stage": DataStage.ESTIMATED,
            "status": "INSUFFICIENT_DATA",
            "explanation": "No valid DSM/DTM, point cloud, architectural metadata, footprint geometry, or floor count provided. Height cannot be determined."
        }
