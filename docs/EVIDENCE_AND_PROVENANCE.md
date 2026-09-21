# Evidence Classification, Fusion & Cadastral Provenance

## 1. Epistemological Classification of Evidence
Cadastral records define legal property rights and financial titles. To guarantee legal defensibility, the 3D ULPIN engine rejects synthetic or unverified measurements and enforces strict epistemological taxonomy:

| Evidence Class | Sensor / Source Origin | Uncertainty Range ($\sigma$) | Epistemological Status | Cadastral Legal Status |
| :--- | :--- | :--- | :--- | :--- |
| **`SURVEY_ACCURATE`** | Total Station / DGPS Ground Survey | $\pm 0.05\text{m} - \pm 0.10\text{m}$ | `OBSERVED` | Primary Legal Ground Truth |
| **`LIDAR_OBSERVED`** | Aerial LiDAR (ASPRS Class 2 + $Z_{95}$) | $\pm 0.15\text{m} - \pm 1.57\text{m}$ | `OBSERVED` | Authoritative Physical Evidence |
| **`ELEVATION_RASTER_OBSERVED`** | DSM minus DTM Raster Grid | $\pm 0.40\text{m} - \pm 0.80\text{m}$ | `OBSERVED` | Validated Physical Observation |
| **`PHOTOGRAMMETRY`** | UAV Nadir/Oblique Photogrammetry | $\pm 0.25\text{m} - \pm 0.50\text{m}$ | `OBSERVED` | Secondary Physical Observation |
| **`CAD_BIM_EXTRACTED`** | Approved Municipal As-Built Architectural Plans | $\pm 0.20\text{m} - \pm 0.30\text{m}$ | `DETERMINISTIC` | Approved Engineering Record |
| **`AI_ESTIMATED`** | ONNX Computer Vision / MLP Regressors | $\pm 2.00\text{m} - \pm 3.00\text{m}$ | `AI_ESTIMATED` | Advisory Hypothesis (Non-Authoritative) |
| **`DETERMINISTIC_FALLBACK`** | Floor Count $\times 3.0\text{m}$ Heuristic Rule | $\pm 3.00\text{m}$ | `DETERMINISTIC` | Default Geometric Scaffold |
| **`UNRESOLVED`** | Out-of-bounds / Conflicting Unverified Data | Undefined | `UNRESOLVED` | Rejected / Unusable |
| **`TEST_FIXTURE`** | Controlled Synthetic Verification Datasets | Fixed | `TEST_FIXTURE` | Testing & CI/CD Validation Only |

---

## 2. Multi-Source Evidence Fusion Hierarchy
When a cadastral parcel dossier includes multiple spatial inputs, the `MultiSourceEvidenceFusionEngine` evaluates all candidates according to a rigorous priority ladder:

$$\text{Priority: } \text{Survey} > \text{LiDAR} > \text{DSM/DTM} > \text{Photogrammetry} > \text{CAD/BIM} > \text{AI} > \text{Deterministic}$$

### Decision Rules:
1. **Spatial Overlap Check**: If the candidate file (e.g., LAS point cloud or GeoTIFF) does not intersect the parcel's bounding polygon, it is marked `OUT_OF_COVERAGE` and disqualified.
2. **CRS Validation**: Coordinate reference systems must be known and reprojectable to the statutory cadastral datum.
3. **AI Bypass**: If an `OBSERVED` candidate (LiDAR, DSM, or Survey) has valid spatial coverage, AI model inference is bypassed completely (`ai_status = NOT_USED_OBSERVED_EVIDENCE`).

---

## 3. Statistical Conflict Detection ($2\sigma$ Tolerance)

When two authoritative sources provide height measurements for the same spatial parcel (e.g. Ground Survey $H_{\text{survey}}$ and Aerial LiDAR $H_{\text{lidar}}$), the engine tests for statistical consistency:

$$\Delta H = |H_A - H_B|$$
$$\sigma_{AB} = \sqrt{\sigma_A^2 + \sigma_B^2}$$
$$\text{Tolerance Threshold } \tau = 2 \cdot \sigma_{AB}$$

### Decision Logic:
- **Consistent ($\Delta H \le \tau$)**: The higher-priority source is selected, and the agreement is logged as corroborating evidence.
- **Statistically Incompatible Conflict ($\Delta H > \tau$)**:
  - The system flags `conflict_detected = True`.
  - Severity is assigned based on deviation ratio:
    - **`HIGH`**: $\Delta H > 3 \sigma_{AB}$ or $|\Delta H| > 5.0\text{m}$.
    - **`MEDIUM`**: $2 \sigma_{AB} < \Delta H \le 3 \sigma_{AB}$.
  - Cadastral Flag: `requires_review = True`.
  - **Non-Fabrication Guarantee**: The system **never** takes an unweighted average or fabricates a compromise value. It records both observations into the immutable digital twin and halts automated legal registration until a human cadastral officer reviews the dispute.

---

## 4. Digital Twin Provenance Schema
Every vertical unit created in the digital twin encapsulates an immutable provenance block:

```json
{
  "unit_id": "e2060266-f8d4-4204-aba4-b9ccfde79155",
  "ulpin_3d": "2B4B1E9AC6711J-L07-UL0701-YS",
  "ml_provenance": {
    "height_source": "LIDAR_OBSERVED",
    "epistemological_class": "OBSERVED",
    "selected_evidence": {
      "source_id": "lidar_kerala_palakkad_sample.las",
      "evidence_type": "LIDAR_OBSERVED",
      "measured_height_m": 18.21,
      "uncertainty_m": 1.57,
      "why_selected": "Highest priority authoritative physical measurement with valid spatial coverage"
    },
    "ai_status": "NOT_USED_OBSERVED_EVIDENCE",
    "conflict_detected": true,
    "conflict_severity": "HIGH",
    "requires_review": true,
    "conflict_details": {
      "source_a": "SURVEY_GROUND_STATION",
      "value_a_m": 30.0,
      "uncertainty_a_m": 0.1,
      "source_b": "LIDAR_POINT_CLOUD",
      "value_b_m": 18.21,
      "uncertainty_b_m": 1.57,
      "difference_m": 11.79,
      "threshold_m": 3.15,
      "cadastral_policy_applied": "DOCUMENTED_PRIORITY_WITH_REVIEW_FLAG"
    }
  }
}
```

---

## 5. Cadastral Officer Conflict Resolution Workflow
1. **Notification**: The frontend renders an amber/red banner alerting: `"Statutory Review Required: Observed Evidence Conflict Detected"`.
2. **Inspection**: The officer opens the Provenance Panel to inspect:
   - Ground survey vs point cloud discrepancy.
   - Point cloud ground returns and $Z_{95}$ roof returns.
   - Survey station calibration date.
3. **Resolution**: The officer selects whether to commission a re-survey or accept the ground total station deed, appending a cryptographically signed officer note to the digital twin audit log.
