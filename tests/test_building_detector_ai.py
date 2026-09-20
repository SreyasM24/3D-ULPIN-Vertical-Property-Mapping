"""
Unit and Integration Tests for AI Building Footprint Segmentation.
Tests ONNX model loading, PyTorch-ONNX parity, real inference,
vectorization, deterministic fallback, and ML API endpoints.
"""

import os
import json
import pytest
import numpy as np
import torch
import onnxruntime as ort
from fastapi import status

from app.ml.models.unet import LightweightUNet
from app.ml.models.building_detector import BuildingDetector
from app.ml.schemas import ModelStatus, DataStage, EvidenceSourceType


def test_model_loading_valid_weights():
    """1. Model loading with valid weights -> status ACTIVE, backend ONNX_RUNTIME."""
    detector = BuildingDetector()
    assert detector.status == ModelStatus.ACTIVE
    assert detector.backend == "ONNX_RUNTIME"
    assert detector.weights_path is not None and os.path.exists(detector.weights_path)
    assert detector.ort_session is not None
    assert detector.model_sha256 is not None
    assert len(detector.model_sha256) == 64


def test_model_loading_missing_weights():
    """2. Model loading with missing weights -> status NOT_CONFIGURED (graceful fallback)."""
    detector = BuildingDetector(weights_path="models/nonexistent_model.onnx")
    assert detector.status == ModelStatus.NOT_CONFIGURED
    assert detector.backend == "NONE"
    assert detector.ort_session is None

    # Verify fallback inference works without error
    sample_poly = {
        "type": "Polygon",
        "coordinates": [[[73.85, 18.52], [73.86, 18.52], [73.86, 18.53], [73.85, 18.53], [73.85, 18.52]]]
    }
    res = detector.predict({"footprint_geojson": sample_poly, "height_m": 14.0})
    assert res.footprint_geojson == sample_poly
    assert res.estimated_height_m == 14.0
    assert res.processing_metadata.get("mode") == "PASS_THROUGH_OBSERVED"


def test_onnx_inference_mask_shape_and_range():
    """3. ONNX inference produces valid mask with expected shape and range [0, 1]."""
    weights_path = "models/building_detector.onnx"
    assert os.path.exists(weights_path), f"ONNX model missing at {weights_path}"

    session = ort.InferenceSession(weights_path, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    test_input = np.random.randn(1, 3, 256, 256).astype(np.float32)

    logits = session.run(None, {input_name: test_input})[0]
    assert logits.shape == (1, 1, 256, 256)
    probs = 1.0 / (1.0 + np.exp(-logits))
    assert np.all(probs >= 0.0)
    assert np.all(probs <= 1.0)


def test_pytorch_onnx_consistency():
    """4. PyTorch model and ONNX export produce consistent outputs (< 1e-4 max absolute diff)."""
    weights_path = "models/building_detector.onnx"
    checkpoint_path = "models/checkpoints/best_building_unet.pt"
    assert os.path.exists(weights_path)
    assert os.path.exists(checkpoint_path)

    # Load PyTorch checkpoint
    model = LightweightUNet()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    state_dict = checkpoint["model_state_dict"] if "model_state_dict" in checkpoint else checkpoint
    model.load_state_dict(state_dict)
    model.eval()

    # Fixed deterministic input
    np.random.seed(42)
    sample_np = np.random.rand(1, 3, 256, 256).astype(np.float32)
    sample_pt = torch.from_numpy(sample_np)

    with torch.no_grad():
        pt_out = model(sample_pt).numpy()

    # Load ONNX session
    session = ort.InferenceSession(weights_path, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    onnx_out = session.run(None, {input_name: sample_np})[0]

    max_diff = np.max(np.abs(pt_out - onnx_out))
    assert max_diff < 1e-4, f"PyTorch/ONNX discrepancy too large: {max_diff}"


def test_vectorization_produces_valid_polygon():
    """5. Vectorization produces valid GeoJSON Polygon with >= 3 vertices and positive area."""
    sample_image = "data/ml/samples/sample_image.png"
    assert os.path.exists(sample_image), f"Sample image missing at {sample_image}"

    detector = BuildingDetector()
    res = detector.predict(image_path=sample_image)

    assert res.processing_metadata.get("mode") == "AI_ONNX_INFERENCE"
    assert res.confidence > 0.5
    assert res.source == EvidenceSourceType.DRONE_PHOTOGRAMMETRY

    poly = res.footprint_geojson
    assert poly["type"] == "Polygon"
    coords = poly["coordinates"][0]
    assert len(coords) >= 4  # Closed polygon requires at least 4 points (3 unique + closing)
    assert coords[0] == coords[-1]  # Closed ring

    # Metric properties in processing metadata
    meta = res.processing_metadata
    assert meta.get("detected_building_count", 0) >= 1
    assert meta.get("building_pixel_ratio", 0.0) > 0.0


def test_deterministic_fallback_path():
    """6. Fallback path still works when footprint_geojson is provided."""
    detector = BuildingDetector()
    input_footprint = {
        "type": "Polygon",
        "coordinates": [[[73.856, 18.520], [73.857, 18.520], [73.857, 18.521], [73.856, 18.521], [73.856, 18.520]]]
    }
    res = detector.predict(footprint_geojson=input_footprint, height_m=18.0, floor_count=5)
    assert res.processing_metadata.get("mode") == "PASS_THROUGH_OBSERVED"
    assert res.stage == DataStage.OBSERVED
    assert res.confidence == 0.90
    assert res.estimated_height_m == 18.0
    assert res.estimated_floor_count == 5
    assert res.footprint_geojson == input_footprint


def test_health_endpoint_reports_building_detector_active(client):
    """7. Health endpoint reports BuildingDetector as ACTIVE and subsystem as OPERATIONAL."""
    resp = client.get("/api/v1/ml/health")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]

    assert data["subsystem"] == "ML_FEATURE_EXTRACTION"
    assert data["status"] == "OPERATIONAL"

    models = {m["model_name"]: m for m in data["models"]}
    assert "BuildingDetector_LOD1" in models
    bld_model = models["BuildingDetector_LOD1"]
    assert bld_model["status"] == "ACTIVE"
    assert bld_model["is_ready"] is True
    assert bld_model["backend"] == "ONNX_RUNTIME"
    assert bld_model["inference_ready"] is True
    assert bld_model["weights_path"] == "models/building_detector.onnx"
    assert bld_model["metrics"]["test_iou"] == 0.5001


def test_models_endpoint_returns_correct_metadata_and_metrics(client):
    """8. Models endpoint returns correct metadata, architecture, and test metrics."""
    resp = client.get("/api/v1/ml/models")
    assert resp.status_code == status.HTTP_200_OK
    models_list = resp.json()["data"]

    bld_model = next((m for m in models_list if m["model_name"] == "BuildingDetector_LOD1"), None)
    assert bld_model is not None
    assert bld_model["status"] == "ACTIVE"
    assert bld_model["is_ready"] is True
    assert bld_model["backend"] == "ONNX_RUNTIME"
    assert "LightweightUNet" in bld_model["architecture"]
    assert bld_model["test_metrics"]["test_iou"] == 0.5001
    assert bld_model["test_metrics"]["test_dice_f1"] == 0.6667
    assert bld_model["test_metrics"]["test_precision"] == 0.6193
    assert bld_model["test_metrics"]["test_recall"] == 0.7220
    assert bld_model["test_metrics"]["test_pixel_accuracy"] == 0.9318


def test_ml_building_extract_endpoint_ai_and_fallback(client):
    """Verifies POST /api/v1/ml/building/extract with both image and fallback footprint."""
    # AI image extraction
    r_ai = client.post("/api/v1/ml/building/extract", json={
        "image_path": "data/ml/samples/sample_image.png",
        "height_m": 12.0
    })
    assert r_ai.status_code == status.HTTP_200_OK
    data_ai = r_ai.json()["data"]
    assert data_ai["footprint_geojson"]["type"] == "Polygon"
    assert data_ai["area_m2"] > 0
    assert data_ai["height_m"] == 12.0
    assert data_ai["volume_m3"] > 0
    assert data_ai["confidence"] > 0.5

    # Deterministic fallback extraction
    r_fb = client.post("/api/v1/ml/building/extract", json={
        "footprint_geojson": {
            "type": "Polygon",
            "coordinates": [[[73.856, 18.520], [73.857, 18.520], [73.857, 18.521], [73.856, 18.521], [73.856, 18.520]]]
        },
        "height_m": 15.0
    })
    assert r_fb.status_code == status.HTTP_200_OK
    data_fb = r_fb.json()["data"]
    assert data_fb["footprint_geojson"]["type"] == "Polygon"
    assert data_fb["area_m2"] > 0
    assert data_fb["height_m"] == 15.0
    assert data_fb["volume_m3"] == round(data_fb["area_m2"] * 15.0, 2)
