"""
Building Detector AI Model Adapter.
Detects and proposes building footprints from satellite/drone imagery using a trained
Lightweight U-Net model executed via ONNX Runtime, with robust deterministic fallback.
"""

from typing import Dict, Any, Optional, List
import os
import json
import hashlib
from datetime import datetime, timezone
import numpy as np
from PIL import Image

from app.ml.models.base import BaseFeatureModel
from app.ml.schemas import (
    ModelStatus,
    BuildingDetectionResult,
    EvidenceSourceType,
    ConfidenceLevel,
    DataStage,
)

try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:
    ort = None
    HAS_ORT = False


class BuildingDetector(BaseFeatureModel):
    """
    Building Footprint Detector model adapter.
    Executes real trained neural network inference via ONNX Runtime when model weights
    are available, while strictly preserving deterministic cadastral fallback.
    """

    DEFAULT_ONNX_PATH = "models/building_detector.onnx"
    DEFAULT_META_PATH = "models/building_detector_metadata.json"

    def __init__(self, weights_path: Optional[str] = None):
        # Resolve weights path: explicit argument, env var, or project default
        resolved_path = weights_path
        if resolved_path is None:
            candidate = os.environ.get("BUILDING_DETECTOR_MODEL_PATH", self.DEFAULT_ONNX_PATH)
            if os.path.exists(candidate):
                resolved_path = candidate

        super().__init__(
            model_name="BuildingDetector_LOD1",
            model_version="1.0.0-trained" if resolved_path and os.path.exists(resolved_path) else "0.1.0-prototype",
            model_type="INSTANCE_SEGMENTATION",
            weights_path=resolved_path
        )
        self.ort_session: Optional[Any] = None
        self.model_sha256: Optional[str] = None
        self.model_metadata: Dict[str, Any] = {}
        self.load()

    def load(self) -> bool:
        """
        Loads and validates the ONNX model using ONNX Runtime.
        Executes a test inference probe to ensure genuine operational readiness.
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
            # 1. Initialize ONNX Runtime Session
            self.ort_session = ort.InferenceSession(
                self.weights_path,
                providers=['CPUExecutionProvider']
            )

            # 2. Sanity probe with dummy input [1, 3, 256, 256]
            input_name = self.ort_session.get_inputs()[0].name
            dummy_tensor = np.zeros((1, 3, 256, 256), dtype=np.float32)
            probe_out = self.ort_session.run(None, {input_name: dummy_tensor})[0]

            if probe_out.shape[1:] != (1, 256, 256):
                raise ValueError(f"Unexpected model output shape: {probe_out.shape}")

            # 3. Calculate SHA256 and load metadata if available
            with open(self.weights_path, 'rb') as f:
                self.model_sha256 = hashlib.sha256(f.read()).hexdigest()

            meta_path = getattr(self, 'DEFAULT_META_PATH', 'models/building_detector_metadata.json')
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as mf:
                    self.model_metadata = json.load(mf)
                    if 'model_version' in self.model_metadata:
                        self.model_version = self.model_metadata['model_version']

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
        """Returns runtime readiness, backend, and health probes for BuildingDetector."""
        base_h = super().health()
        base_h.update({
            "backend": self.backend,
            "model_sha256": self.model_sha256,
            "inference_ready": self.status == ModelStatus.ACTIVE and self.ort_session is not None,
            "target_resolution": [256, 256],
            "metrics": self.model_metadata.get("test_metrics", {})
        })
        return base_h

    def metadata(self) -> Dict[str, Any]:
        """Exposes model descriptor and operational capabilities."""
        meta = super().metadata()
        meta.update({
            "backend": "ONNX_RUNTIME" if self.status == ModelStatus.ACTIVE else "NONE",
            "is_ready": self.status == ModelStatus.ACTIVE,
            "weights_sha256": self.model_sha256,
            "architecture": self.model_metadata.get("architecture", "LightweightUNet"),
            "test_metrics": self.model_metadata.get("test_metrics", {}),
            "training_dataset": self.model_metadata.get("training_dataset", {}).get("name", "SpaceNet 1 (Rio)")
        })
        return meta

    def predict(self, inputs: Optional[Dict[str, Any]] = None, **kwargs) -> BuildingDetectionResult:
        """
        Executes building detection:
        1. If footprint_geojson is supplied with valid coordinates -> Pass-through observed fallback.
        2. If trained model is ACTIVE and imagery is provided -> Real ONNX inference.
        3. Otherwise -> Deterministic unconfigured fallback.
        """
        merged_inputs = dict(inputs or {})
        merged_inputs.update(kwargs)
        inputs = merged_inputs

        source_footprint = inputs.get("footprint_geojson")
        source_type = inputs.get("source_type") or EvidenceSourceType.BUILDING_METADATA

        # -------------------------------------------------------------------
        # Branch 1: Deterministic Observed Footprint Pass-Through
        # -------------------------------------------------------------------
        if source_footprint and source_footprint.get("coordinates") and len(source_footprint["coordinates"]) > 0:
            return BuildingDetectionResult(
                building_id=inputs.get("building_id"),
                footprint_geojson=source_footprint,
                estimated_height_m=inputs.get("height_m"),
                estimated_ground_elevation_m=inputs.get("ground_elevation_m"),
                estimated_top_elevation_m=inputs.get("top_elevation_m"),
                estimated_floor_count=inputs.get("floor_count"),
                confidence=0.90,
                confidence_level=ConfidenceLevel.HIGH,
                uncertainty_m=0.2,
                source=source_type,
                model_name=self.model_name,
                model_version=self.model_version,
                stage=DataStage.OBSERVED,
                processing_metadata={"mode": "PASS_THROUGH_OBSERVED"}
            )

        # -------------------------------------------------------------------
        # Branch 2: Real Trained Neural Network Inference (ONNX Runtime)
        # -------------------------------------------------------------------
        image_input = (
            inputs.get("image") or
            inputs.get("image_path") or
            inputs.get("source_imagery") or
            inputs.get("image_file")
        )

        if self.status == ModelStatus.ACTIVE and self.ort_session is not None and image_input:
            try:
                # Load image
                if isinstance(image_input, str):
                    if not os.path.exists(image_input):
                        raise FileNotFoundError(f"Imagery file not found: {image_input}")
                    pil_img = Image.open(image_input).convert('RGB')
                elif isinstance(image_input, Image.Image):
                    pil_img = image_input.convert('RGB')
                elif isinstance(image_input, np.ndarray):
                    pil_img = Image.fromarray(image_input).convert('RGB')
                else:
                    raise ValueError(f"Unsupported image input type: {type(image_input)}")

                orig_w, orig_h = pil_img.size

                # Preprocessing: Resize to 256x256, normalize to [0, 1], shape [1, 3, 256, 256]
                resized_img = pil_img.resize((256, 256), Image.BILINEAR)
                img_arr = np.array(resized_img, dtype=np.float32) / 255.0
                tensor_input = img_arr.transpose(2, 0, 1)[np.newaxis, ...]  # [1, 3, 256, 256]

                # Run ONNX inference
                input_name = self.ort_session.get_inputs()[0].name
                logits = self.ort_session.run(None, {input_name: tensor_input})[0]  # [1, 1, 256, 256]

                # Sigmoid probability & thresholding
                probs = 1.0 / (1.0 + np.exp(-logits[0, 0]))
                binary_mask = (probs > 0.50).astype(np.uint8)

                # Vectorize mask to GeoJSON
                detected_geojson, mean_conf = self._vectorize_prediction(
                    binary_mask=binary_mask,
                    probs=probs,
                    inputs=inputs,
                    orig_size=(orig_w, orig_h)
                )

                bld_confidence = float(mean_conf) if mean_conf > 0 else 0.85
                conf_level = (
                    ConfidenceLevel.HIGH if bld_confidence >= 0.80 else (
                        ConfidenceLevel.MEDIUM if bld_confidence >= 0.60 else ConfidenceLevel.LOW
                    )
                )

                return BuildingDetectionResult(
                    building_id=inputs.get("building_id"),
                    footprint_geojson=detected_geojson,
                    estimated_height_m=inputs.get("height_m"),
                    estimated_ground_elevation_m=inputs.get("ground_elevation_m"),
                    estimated_top_elevation_m=inputs.get("top_elevation_m"),
                    estimated_floor_count=inputs.get("floor_count"),
                    confidence=round(bld_confidence, 4),
                    confidence_level=conf_level,
                    uncertainty_m=0.3,
                    source=inputs.get("source_type", EvidenceSourceType.DRONE_PHOTOGRAMMETRY),
                    model_name=self.model_name,
                    model_version=self.model_version,
                    stage=DataStage.ESTIMATED,
                    processing_metadata={
                        "mode": "AI_ONNX_INFERENCE",
                        "backend": "ONNX_RUNTIME",
                        "model_sha256": self.model_sha256,
                        "model_path": self.weights_path,
                        "inference_device": "CPU",
                        "building_pixels": int(np.sum(binary_mask)),
                        "building_pixel_ratio": float(np.mean(binary_mask)),
                        "detected_building_count": 1 if np.sum(binary_mask) > 0 else 0,
                        "threshold": 0.50,
                        "input_resolution": [orig_w, orig_h]
                    }
                )

            except Exception as e:
                import logging
                logging.getLogger("BuildingDetector").warning(f"ONNX inference exception: {e}")

        # -------------------------------------------------------------------
        # Branch 3: Unconfigured / Fallback State
        # -------------------------------------------------------------------
        return BuildingDetectionResult(
            building_id=inputs.get("building_id"),
            footprint_geojson={"type": "Polygon", "coordinates": []},
            confidence=0.0,
            confidence_level=ConfidenceLevel.UNKNOWN,
            source=EvidenceSourceType.ASSUMPTION_FALLBACK,
            model_name=self.model_name,
            model_version=self.model_version,
            stage=DataStage.ESTIMATED,
            processing_metadata={
                "mode": "DETERMINISTIC_FALLBACK",
                "status": "NOT_CONFIGURED" if self.status != ModelStatus.ACTIVE else "NO_IMAGERY_SUPPLIED",
                "explanation": (
                    "No trained deep-learning segmentation model weights (e.g. Mask-RCNN / SAM / PointNet) are configured in the environment. Please supply an ingested boundary polygon or configure model weights."
                    if self.status != ModelStatus.ACTIVE else
                    "BuildingDetector is ACTIVE and ready, but no imagery was provided or imagery could not be read. Supply valid 'image' or 'image_path' to execute AI inference."
                )
            }
        )

    def _vectorize_prediction(
        self,
        binary_mask: np.ndarray,
        probs: np.ndarray,
        inputs: Dict[str, Any],
        orig_size: tuple
    ) -> tuple:
        """
        Converts a 256x256 binary mask into a valid GeoJSON Polygon with optional georeferencing.
        """
        from scipy import ndimage
        from shapely.geometry import MultiPoint, Polygon

        orig_w, orig_h = orig_size
        labeled, num_features = ndimage.label(binary_mask)

        if num_features == 0 or np.sum(binary_mask) < 10:
            # Empty fallback rectangle if no building detected
            return {"type": "Polygon", "coordinates": []}, 0.0

        # Find the largest detected building component
        component_sizes = ndimage.sum(binary_mask, labeled, range(1, num_features + 1))
        largest_label = int(np.argmax(component_sizes) + 1)

        pts = np.argwhere(labeled == largest_label)[:, ::-1]  # (x, y) in 256x256 space

        # Scale points back to original image dimensions
        scale_x = orig_w / 256.0
        scale_y = orig_h / 256.0
        pts_orig = pts.astype(np.float32)
        pts_orig[:, 0] *= scale_x
        pts_orig[:, 1] *= scale_y

        # Convex hull for polygon extraction
        hull = MultiPoint(pts_orig).convex_hull
        if hull.geom_type != 'Polygon':
            hull = hull.envelope
            if hull.geom_type != 'Polygon':
                return {"type": "Polygon", "coordinates": []}, 0.0

        hull_coords = list(hull.exterior.coords)

        # Check for geographic coordinate transformation
        # Supports origin_lon, origin_lat, scale_deg_x, scale_deg_y or bbox [min_lon, min_lat, max_lon, max_lat]
        origin_lon = inputs.get("origin_lon")
        origin_lat = inputs.get("origin_lat")
        res_deg_x = inputs.get("resolution_deg_x") or inputs.get("resolution_deg")
        res_deg_y = inputs.get("resolution_deg_y") or inputs.get("resolution_deg")

        if origin_lon is not None and origin_lat is not None and res_deg_x is not None:
            # Map pixel coordinates to real-world WGS84 coordinates
            geo_coords = []
            for px, py in hull_coords:
                lon = float(origin_lon + (px * res_deg_x))
                lat = float(origin_lat - (py * (res_deg_y or res_deg_x)))
                geo_coords.append([round(lon, 7), round(lat, 7)])
            final_coords = [geo_coords]
        elif "bbox" in inputs and len(inputs["bbox"]) == 4:
            min_x, min_y, max_x, max_y = inputs["bbox"]
            geo_coords = []
            for px, py in hull_coords:
                lon = float(min_x + (px / orig_w) * (max_x - min_x))
                lat = float(max_y - (py / orig_h) * (max_y - min_y))
                geo_coords.append([round(lon, 7), round(lat, 7)])
            final_coords = [geo_coords]
        else:
            # Default normalized coordinates [0.0 to 1.0] if no georeferencing
            norm_coords = [[round(px / orig_w, 4), round(py / orig_h, 4)] for px, py in hull_coords]
            final_coords = [norm_coords]

        mean_confidence = float(np.mean(probs[labeled == largest_label]))
        return {"type": "Polygon", "coordinates": final_coords}, mean_confidence
