# AI Model Card: Cadastral Computer Vision & Height Regressor Models

## 1. Model Overview & Purpose
This document provides formal model cards for the artificial intelligence components integrated into the **3D ULPIN & Vertical Property Mapping Engine**. 

In strict adherence to cadastral legal requirements, **AI models are strictly advisory**. They provide preliminary geometric hypotheses (`ADVISORY_ESTIMATE`) when physical survey or LiDAR point-cloud returns are absent. They are automatically bypassed whenever authoritative physical sensor evidence is provided.

---

## 2. Model 1: SpaceNet Building Footprint Detector

### 2.1 Model Specifications
- **Model Name**: SpaceNet-1 Building Footprint Segmenter
- **Architecture**: UNet with Convolutional Downsampling / Upsampling & Skip Connections
- **Format**: ONNX Runtime Engine (`SpaceNet_Building_Detector.onnx`)
- **Artifact Path**: `data/ml/models/SpaceNet_Building_Detector.onnx`
- **Model Checksum (SHA-256)**: `6840feac1ff15945540b839401877ba1eee0460e0b4f80b7d501eaa299c85d1f`
- **Runtime Inference Engine**: ONNX Runtime (CPU / CUDA)
- **Input Tensor**: `[1, 3, 256, 256]` (RGB aerial / satellite imagery, normalized $[0.0, 1.0]$)
- **Output Tensor**: `[1, 1, 256, 256]` (Binary building segmentation probability map, sigmoid activated)

### 2.2 Training & Evaluation
- **Base Dataset**: SpaceNet 1: Building Detection v1 (Rio de Janeiro aerial imagery, $0.5\text{m}$ resolution).
- **Fine-Tuning / Adaptation**: Normalized multi-spectral bands with geometric morphological post-processing.
- **Evaluation Metrics**:
  - Test Intersection-over-Union (IoU): `0.5001`
  - Polygon Boundary Regularization F1: `0.784`
- **Output Post-Processing**:
  1. Otsu / adaptive thresholding at $P \ge 0.50$.
  2. Contour extraction via polygonization.
  3. Douglas-Peucker polygon simplification ($\epsilon = 1.0$).
  4. Coordinate reprojection to target parcel CRS.

### 2.3 Operational Domain & Constraints
- **Intended Use**: Initial detection of building outlines from satellite / UAV orthophotos where vector cadastral records are missing or out of date.
- **Out of Scope**: Must not override legally registered surveyor boundary stones or statutory parcel deeds.

---

## 3. Model 2: Cadastral Building Height Regressor

### 3.1 Model Specifications
- **Model Name**: Cadastral Height Regressor MLP
- **Architecture**: Multi-Layer Perceptron (Dense 64 -> ReLU -> Dense 32 -> ReLU -> Dense 1)
- **Format**: ONNX Runtime Engine (`Height_Regressor_MLP.onnx`)
- **Artifact Path**: `data/ml/models/Height_Regressor_MLP.onnx`
- **Model Checksum (SHA-256)**: `ba15f917dfa74d28430e791e813f009e5b7b9f34563a6e9a0f44383c26027ab5`
- **Runtime Inference Engine**: ONNX Runtime (CPU)
- **Input Tensor**: `[1, 4]` (Normalized features: `[footprint_area, perimeter, floor_count, urban_density_index]`)
- **Output Tensor**: `[1, 1]` (Estimated building vertical height in meters)

### 3.2 Training & Evaluation
- **Base Dataset**: Urban Morphology & Elevation Benchmarks (OpenBuildingMap & synthetic urban height priors).
- **Evaluation Metrics**:
  - Mean Absolute Error (MAE): `0.84m`
  - Root Mean Squared Error (RMSE): `1.12m`
- **Uncertainty Quantification**:
  - Baseline model uncertainty: $\sigma = \pm 2.50\text{m}$.
  - Uncertainty propagates directly to the provenance metadata to alert downstream cadastral consumers.

---

## 4. Non-Fabrication & Safety Safeguards
1. **No Silent Consensus**: AI models cannot "override" or "smooth" discrepancies between contradictory physical measurements.
2. **Authoritative Bypass**: When an ASPRS Class 2 / surface point cloud or validated DSM is available, the AI inference stage is completely bypassed (`NOT_USED_OBSERVED_EVIDENCE`).
3. **Transparency in Metadata**: Every unit derived using AI models explicitly carries:
   - `ai_status = "ADVISORY_ESTIMATE"`
   - `model_name = "SpaceNet_Building_Detector.onnx"` or `"Height_Regressor_MLP.onnx"`
   - `model_sha256 = ...`
   - `uncertainty_m = 2.50`
   - `requires_statutory_verification = True`
