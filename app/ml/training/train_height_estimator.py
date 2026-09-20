"""
Training, Evaluation, and ONNX Export Pipeline for Building Height Regression.
Performs:
1. Spatially disjoint partitioning (70% train / 15% val / 15% test).
2. Feature extraction and standard normalization (fit strictly on train).
3. Supervised regression training with SmoothL1Loss and AdamW.
4. Comprehensive test evaluation (MAE, RMSE, R2, Median AE, P90 AE).
5. ONNX export (opset 17) and cross-engine verification.
6. Metadata generation for production deployment.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
import onnxruntime as ort

from app.ml.models.height_mlp import HeightRegressorMLP

DATASET_PATH = "data/ml/processed/building_height/validated_height_samples.json"
SPLIT_PATH = "data/ml/manifests/height_regression_split.json"
CHECKPOINT_PATH = "models/checkpoints/best_height_mlp.pt"
ONNX_EXPORT_PATH = "models/height_estimator.onnx"
METADATA_PATH = "models/height_estimator_metadata.json"

FEATURE_NAMES = [
    "footprint_area_m2",
    "footprint_perimeter_m",
    "compactness",
    "convexity",
    "aspect_ratio",
    "equivalent_diameter_m",
    "terrain_elevation_m"
]

def load_and_split_data(seed: int = 42):
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    samples = data["samples"]
    total = len(samples)
    print(f"Loaded {total} validated building height samples.")

    # Sort strictly by geographic longitude to create spatial blocks
    # (West -> Central -> East, preventing spatial autocorrelation leakage)
    samples_sorted = sorted(samples, key=lambda s: (s["centroid_lon"], s["centroid_lat"]))

    n_train = int(round(total * 0.70))
    n_val = int(round(total * 0.15))
    n_test = total - n_train - n_val

    train_samples = samples_sorted[:n_train]
    val_samples = samples_sorted[n_train:n_train + n_val]
    test_samples = samples_sorted[n_train + n_val:]

    print(f"Spatial Disjoint Split: Train={len(train_samples)}, Val={len(val_samples)}, Test={len(test_samples)}")
    print(f"  Train Lon Range: [{train_samples[0]['centroid_lon']:.6f}, {train_samples[-1]['centroid_lon']:.6f}]")
    print(f"  Val Lon Range:   [{val_samples[0]['centroid_lon']:.6f}, {val_samples[-1]['centroid_lon']:.6f}]")
    print(f"  Test Lon Range:  [{test_samples[0]['centroid_lon']:.6f}, {test_samples[-1]['centroid_lon']:.6f}]")

    split_manifest = {
        "split_seed": seed,
        "split_strategy": "SPATIAL_DISJOINT_BLOCKS",
        "counts": {
            "total": total,
            "train": len(train_samples),
            "val": len(val_samples),
            "test": len(test_samples)
        },
        "train_building_ids": [s["building_id"] for s in train_samples],
        "val_building_ids": [s["building_id"] for s in val_samples],
        "test_building_ids": [s["building_id"] for s in test_samples]
    }
    os.makedirs(os.path.dirname(SPLIT_PATH), exist_ok=True)
    with open(SPLIT_PATH, "w", encoding="utf-8") as f:
        json.dump(split_manifest, f, indent=2)

    return train_samples, val_samples, test_samples

def extract_features_and_targets(sample_list):
    X = np.array([[s[fn] for fn in FEATURE_NAMES] for s in sample_list], dtype=np.float32)
    y = np.array([s["building_height_m"] for s in sample_list], dtype=np.float32).reshape(-1, 1)
    return X, y

def train_and_export():
    torch.manual_seed(42)
    np.random.seed(42)

    train_samples, val_samples, test_samples = load_and_split_data(seed=42)

    X_train_raw, y_train = extract_features_and_targets(train_samples)
    X_val_raw, y_val = extract_features_and_targets(val_samples)
    X_test_raw, y_test = extract_features_and_targets(test_samples)

    # Compute normalization statistics strictly on training set
    feature_means = np.mean(X_train_raw, axis=0)
    feature_stds = np.std(X_train_raw, axis=0)
    feature_stds[feature_stds < 1e-6] = 1.0  # Avoid division by zero

    X_train = (X_train_raw - feature_means) / feature_stds
    X_val = (X_val_raw - feature_means) / feature_stds
    X_test = (X_test_raw - feature_means) / feature_stds

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    val_ds = TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val))

    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=64, shuffle=False)

    model = HeightRegressorMLP(in_features=len(FEATURE_NAMES))
    criterion = nn.SmoothL1Loss(beta=1.0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.005, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=5)

    best_val_loss = float("inf")
    best_epoch = 0
    os.makedirs(os.path.dirname(CHECKPOINT_PATH), exist_ok=True)

    print("\nStarting Training (50 epochs)...")
    for epoch in range(1, 51):
        model.train()
        train_losses = []
        for bx, by in train_loader:
            optimizer.zero_grad()
            preds = model(bx)
            loss = criterion(preds, by)
            loss.backward()
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for bx, by in val_loader:
                preds = model(bx)
                val_losses.append(criterion(preds, by).item())

        avg_train = np.mean(train_losses)
        avg_val = np.mean(val_losses)
        scheduler.step(avg_val)

        if avg_val < best_val_loss:
            best_val_loss = avg_val
            best_epoch = epoch
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_loss": avg_val,
                "feature_names": FEATURE_NAMES,
                "feature_means": feature_means.tolist(),
                "feature_stds": feature_stds.tolist()
            }, CHECKPOINT_PATH)

        if epoch % 5 == 0 or epoch == 1:
            print(f"Epoch {epoch:02d}/50 | Train Loss: {avg_train:.4f} | Val Loss: {avg_val:.4f} | LR: {optimizer.param_groups[0]['lr']:.6f}")

    print(f"\nBest Model Saved at Epoch {best_epoch} with Val Loss: {best_val_loss:.4f}")

    # Load best checkpoint for test evaluation
    best_ckpt = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=False)
    model.load_state_dict(best_ckpt["model_state_dict"])
    model.eval()

    with torch.no_grad():
        test_preds = model(torch.from_numpy(X_test)).numpy().flatten()
    y_test_flat = y_test.flatten()

    abs_errors = np.abs(test_preds - y_test_flat)
    mae = float(np.mean(abs_errors))
    rmse = float(np.sqrt(np.mean((test_preds - y_test_flat) ** 2)))
    median_ae = float(np.median(abs_errors))
    p90_ae = float(np.percentile(abs_errors, 90))

    # R2 Score calculation
    ss_res = np.sum((y_test_flat - test_preds) ** 2)
    ss_tot = np.sum((y_test_flat - np.mean(y_test_flat)) ** 2)
    r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0

    test_metrics = {
        "test_mae_m": round(mae, 3),
        "test_rmse_m": round(rmse, 3),
        "test_r2": round(r2, 4),
        "test_median_ae_m": round(median_ae, 3),
        "test_p90_ae_m": round(p90_ae, 3),
        "test_buildings_count": len(test_samples),
        "test_min_height_m": round(float(np.min(y_test_flat)), 2),
        "test_median_height_m": round(float(np.median(y_test_flat)), 2),
        "test_max_height_m": round(float(np.max(y_test_flat)), 2)
    }

    print("\nHeld-Out Test Evaluation:")
    for k, v in test_metrics.items():
        print(f"  {k:22s}: {v}")

    # Export to ONNX
    print("\nExporting to ONNX...")
    model.eval()
    dummy_input = torch.zeros(1, len(FEATURE_NAMES), dtype=torch.float32)

    os.makedirs(os.path.dirname(ONNX_EXPORT_PATH), exist_ok=True)
    torch.onnx.export(
        model,
        dummy_input,
        ONNX_EXPORT_PATH,
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=["features"],
        output_names=["height_m"],
        dynamic_axes={"features": {0: "batch_size"}, "height_m": {0: "batch_size"}},
        dynamo=False
    )

    with open(ONNX_EXPORT_PATH, "rb") as f:
        onnx_sha256 = hashlib.sha256(f.read()).hexdigest()
    file_size_bytes = os.path.getsize(ONNX_EXPORT_PATH)
    print(f"ONNX Model Exported: {ONNX_EXPORT_PATH} ({file_size_bytes} bytes, SHA256: {onnx_sha256})")

    # Cross-Engine Parity Check (PyTorch vs ONNX Runtime)
    ort_session = ort.InferenceSession(ONNX_EXPORT_PATH, providers=["CPUExecutionProvider"])
    sample_inputs = np.random.randn(10, len(FEATURE_NAMES)).astype(np.float32)

    with torch.no_grad():
        pt_outputs = model(torch.from_numpy(sample_inputs)).numpy()
    ort_outputs = ort_session.run(None, {"features": sample_inputs})[0]

    max_diff = float(np.max(np.abs(pt_outputs - ort_outputs)))
    print(f"Cross-Engine Numerical Discrepancy (PyTorch vs ONNX Runtime): {max_diff:.8e}")
    assert max_diff < 1e-4, f"Parity mismatch too large: {max_diff}"
    print("Numerical Parity Check PASSED (< 1e-4).")

    # Save complete metadata
    metadata = {
        "model_name": "HeightEstimator_Cascade",
        "model_version": "1.0.0-trained",
        "model_type": "HEIGHT_REGRESSOR",
        "architecture": "HeightRegressorMLP (Linear, BatchNorm1d, ReLU, Dropout, Softplus, 5,217 params)",
        "framework": "PyTorch 2.14.0 -> ONNX Runtime",
        "onnx_opset": 17,
        "onnx_sha256": onnx_sha256,
        "onnx_file_size_bytes": file_size_bytes,
        "training_date": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "name": "3DBAG (AHN4 Airborne LiDAR + Kadaster Cadastre)",
            "region": "Delft, Netherlands",
            "total_usable_samples": len(train_samples) + len(val_samples) + len(test_samples),
            "split": {
                "train_samples": len(train_samples),
                "val_samples": len(val_samples),
                "test_samples": len(test_samples),
                "seed": 42,
                "strategy": "SPATIAL_DISJOINT_BLOCKS"
            }
        },
        "input_features": FEATURE_NAMES,
        "normalization": {
            "method": "STANDARD_SCALING",
            "means": [round(float(m), 6) for m in feature_means],
            "stds": [round(float(s), 6) for s in feature_stds]
        },
        "test_metrics": test_metrics,
        "target": {
            "name": "building_height_m",
            "unit": "meters",
            "min_allowed_m": 2.0,
            "max_allowed_m": 120.0
        },
        "parity_max_diff": max_diff
    }

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to {METADATA_PATH}")

    return test_metrics

if __name__ == "__main__":
    train_and_export()
