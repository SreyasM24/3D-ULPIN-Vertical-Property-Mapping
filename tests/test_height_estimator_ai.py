"""
Unit and Integration Tests for Real Building Height Intelligence.
Tests HeightEstimatorModel ONNX loading, PyTorch-ONNX parity,
multi-strategy cascade (Observed -> AI Regression -> Deterministic Fallback),
provenance tracking, and FastAPI endpoints.
"""

import os
import json
import pytest
import numpy as np
import torch
import onnxruntime as ort
from fastapi import status

from app.ml.models.height_mlp import HeightRegressorMLP
from app.ml.models.height_estimator import HeightEstimatorModel
from app.ml.schemas import ModelStatus, DataStage, EvidenceSourceType


def test_height_model_loading_valid_weights():
    """1. Height model loading with valid weights -> status ACTIVE, backend ONNX_RUNTIME."""
    estimator = HeightEstimatorModel()
    assert estimator.status == ModelStatus.ACTIVE
    assert estimator.backend == "ONNX_RUNTIME"
    assert estimator.weights_path is not None and os.path.exists(estimator.weights_path)
    assert estimator.ort_session is not None
    assert estimator.model_sha256 is not None
    assert len(estimator.model_sha256) == 64


def test_height_model_loading_missing_weights():
    """2. Height model loading with missing weights -> status NOT_CONFIGURED (graceful fallback)."""
    estimator = HeightEstimatorModel(weights_path="models/nonexistent_height_model.onnx")
    assert estimator.status == ModelStatus.NOT_CONFIGURED
    assert estimator.backend == "NONE"
    assert estimator.ort_session is None

    # Fallback to floor heuristic
    res = estimator.predict(floor_count=4, ground_elevation_m=10.0)
    assert res["status"] == "SUCCESS"
    assert res["method"] == "FLOOR_COUNT_HEURISTIC"
    assert res["provenance"] == "DETERMINISTIC_CASCADE"
    assert res["height_m"] == 12.8


def test_height_onnx_inference_parity():
    """3. PyTorch model and ONNX export produce consistent outputs (< 1e-4 max absolute diff)."""
    weights_path = "models/height_estimator.onnx"
    checkpoint_path = "models/checkpoints/best_height_mlp.pt"
    assert os.path.exists(weights_path)
    assert os.path.exists(checkpoint_path)

    # Load PyTorch checkpoint
    model = HeightRegressorMLP(in_features=7)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state_dict = checkpoint["model_state_dict"] if "model_state_dict" in checkpoint else checkpoint
    model.load_state_dict(state_dict)
    model.eval()

    # Fixed deterministic input
    np.random.seed(42)
    sample_np = np.random.randn(10, 7).astype(np.float32)

    with torch.no_grad():
        pt_out = model(torch.from_numpy(sample_np)).numpy()

    # Load ONNX session
    session = ort.InferenceSession(weights_path, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    onnx_out = session.run(None, {input_name: sample_np})[0]

    max_diff = float(np.max(np.abs(pt_out - onnx_out)))
    assert max_diff < 1e-4, f"PyTorch/ONNX discrepancy too large: {max_diff}"


def test_height_evidence_extraction_observed():
    """4. Observed elevation / survey metadata produces OBSERVED provenance."""
    estimator = HeightEstimatorModel()

    # Explicit survey metadata
    res_meta = estimator.predict(total_height_m=24.5, ground_elevation_m=15.0)
    assert res_meta["status"] == "SUCCESS"
    assert res_meta["provenance"] == "OBSERVED_SURVEY_METADATA"
    assert res_meta["method"] == "EXPLICIT_METADATA"
    assert res_meta["height_m"] == 24.5
    assert res_meta["confidence"] == 0.95

    # DSM - DTM difference
    res_dsm = estimator.predict(
        dsm_metadata={"elevation_max_m": 45.0, "elevation_mean_m": 42.0},
        dtm_metadata={"elevation_min_m": 25.0, "elevation_mean_m": 27.0}
    )
    assert res_dsm["status"] == "SUCCESS"
    assert res_dsm["provenance"] == "OBSERVED_ELEVATION_EVIDENCE"
    assert res_dsm["method"] == "DSM_DTM_DIFFERENCE"
    assert res_dsm["height_m"] > 0.0


def test_height_ai_regression_inference():
    """5. Real AI regression inference on footprint geometry and terrain elevation."""
    estimator = HeightEstimatorModel()
    sample_poly = {
        "type": "Polygon",
        "coordinates": [[[4.3500, 52.0100], [4.35015, 52.0100], [4.35015, 52.0101], [4.3500, 52.0101], [4.3500, 52.0100]]]
    }

    res = estimator.predict(footprint_geojson=sample_poly, ground_elevation_m=0.5)
    assert res["status"] == "SUCCESS"
    assert res["provenance"] == "AI_REGRESSION"
    assert res["method"] == "AI_TABULAR_REGRESSION"
    assert 2.0 <= res["height_m"] <= 120.0
    assert res["confidence"] == 0.75
    assert res["source"] == EvidenceSourceType.DRONE_PHOTOGRAMMETRY

    meta = res["processing_metadata"]
    assert meta["mode"] == "AI_ONNX_INFERENCE"
    assert meta["backend"] == "ONNX_RUNTIME"
    assert meta["input_features"]["footprint_area_m2"] > 0
    assert meta["input_features"]["terrain_elevation_m"] == 0.5


def test_height_deterministic_fallback():
    """6. Deterministic floor count fallback when no observed or footprint evidence."""
    estimator = HeightEstimatorModel()
    res = estimator.predict(floor_count=3, ground_elevation_m=100.0)
    assert res["status"] == "SUCCESS"
    assert res["provenance"] == "DETERMINISTIC_CASCADE"
    assert res["method"] == "FLOOR_COUNT_HEURISTIC"
    assert res["height_m"] == 9.8  # 3.8 + 2 * 3.0
    assert res["ground_elevation_m"] == 100.0
    assert res["top_elevation_m"] == 109.8


def test_invalid_elevation_and_empty_input_handling():
    """7. Gracefully handles empty or invalid inputs without crashing."""
    estimator = HeightEstimatorModel()
    res = estimator.predict({})
    assert res["status"] == "INSUFFICIENT_DATA"
    assert res["height_m"] is None
    assert res["method"] == "UNKNOWN"
    assert res["provenance"] == "DETERMINISTIC_CASCADE"


def test_health_endpoint_reports_height_estimator_active(client):
    """8. Health endpoint reports HeightEstimator as ACTIVE with ONNX_RUNTIME backend."""
    resp = client.get("/api/v1/ml/health")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]

    models = {m["model_name"]: m for m in data["models"]}
    assert "HeightEstimator_Cascade" in models
    h_model = models["HeightEstimator_Cascade"]
    assert h_model["status"] == "ACTIVE"
    assert h_model["is_ready"] is True
    assert h_model["backend"] == "ONNX_RUNTIME"
    assert h_model["inference_ready"] is True
    assert h_model["weights_path"] == "models/height_estimator.onnx"
    assert h_model["metrics"]["test_mae_m"] == 2.323


def test_models_endpoint_returns_height_metadata_and_metrics(client):
    """9. Models endpoint returns correct metadata, architecture, and test benchmarks."""
    resp = client.get("/api/v1/ml/models")
    assert resp.status_code == status.HTTP_200_OK
    models_list = resp.json()["data"]

    h_model = next((m for m in models_list if m["model_name"] == "HeightEstimator_Cascade"), None)
    assert h_model is not None
    assert h_model["status"] == "ACTIVE"
    assert h_model["is_ready"] is True
    assert h_model["backend"] == "ONNX_RUNTIME"
    assert "HeightRegressorMLP" in h_model["architecture"]
    assert h_model["test_metrics"]["test_mae_m"] == 2.323
    assert h_model["test_metrics"]["test_rmse_m"] == 3.869
    assert h_model["test_metrics"]["test_median_ae_m"] == 0.901


def test_api_post_building_height_all_strategies(client):
    """10. Tests POST /api/v1/ml/building/height across all 4 strategies."""
    # 1. Observed Evidence
    r1 = client.post("/api/v1/ml/building/height", json={"total_height_m": 25.0})
    assert r1.status_code == status.HTTP_200_OK
    assert r1.json()["data"]["provenance"] == "OBSERVED_SURVEY_METADATA"
    assert r1.json()["data"]["height_m"] == 25.0

    # 2. AI Regression
    sample_poly = {
        "type": "Polygon",
        "coordinates": [[[4.3500, 52.0100], [4.35015, 52.0100], [4.35015, 52.0101], [4.3500, 52.0101], [4.3500, 52.0100]]]
    }
    r2 = client.post("/api/v1/ml/building/height", json={"footprint_geojson": sample_poly, "ground_elevation_m": 0.5})
    assert r2.status_code == status.HTTP_200_OK
    assert r2.json()["data"]["provenance"] == "AI_REGRESSION"
    assert r2.json()["data"]["method"] == "AI_TABULAR_REGRESSION"
    assert r2.json()["data"]["height_m"] > 0

    # 3. Floor Fallback
    r3 = client.post("/api/v1/ml/building/height", json={"floor_count": 4})
    assert r3.status_code == status.HTTP_200_OK
    assert r3.json()["data"]["provenance"] == "DETERMINISTIC_CASCADE"
    assert r3.json()["data"]["method"] == "FLOOR_COUNT_HEURISTIC"
    assert r3.json()["data"]["height_m"] == 12.8

    # 4. Invalid Input
    r4 = client.post("/api/v1/ml/building/height", json={})
    assert r4.status_code == status.HTTP_200_OK
    assert r4.json()["data"]["status"] == "INSUFFICIENT_DATA"
    assert r4.json()["data"]["height_m"] is None
