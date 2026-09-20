"""
Temporal 3D Change & Cadastral Intelligence Test Suite.
SIH 26011 - 3D ULPIN & Vertical Property Mapping System.

Covers all 15 required test scenarios:
1. Unchanged building (IoU = 1.0, score = 0.0, severity = NONE)
2. Footprint expansion (positive area delta, IoU < 1.0)
3. Footprint contraction (negative area delta)
4. Building addition (NEW_BUILDING classification, BUILDING_ADDED event)
5. Building removal (REMOVED_BUILDING classification, BUILDING_REMOVED event)
6. Height change (observed LiDAR delta, uncertainty adjusted)
7. Floor change (added/removed floor level, FLOOR_STRUCTURE_CHANGED event)
8. Basement change (added basement strata, BASEMENT_CHANGED event)
9. Vertical-unit change (added/modified units, VERTICAL_UNIT_CHANGED event)
10. AI-derived change requiring review (AI_ESTIMATED_CHANGE classification)
11. Observed-evidence change (OBSERVED_CHANGE classification)
12. Deterministic reproducibility (multiple passes yield identical scores and events)
13. Invalid geometry handling (graceful handling of malformed GeoJSON)
14. Missing baseline error handling (proper Cadastre exception on missing baseline)
15. Missing current observation error handling (validation error on missing observation)
16. FastAPI integration test (live /api/v1/digital-twin/compare endpoint)
"""

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, mapping

from app.main import app
from app.schemas.temporal_change import (
    DigitalTwinSnapshot,
    TemporalComparisonConfig,
    ChangeType,
    ChangeClassification,
    FootprintChangeClass,
    ChangeSeverity,
    TemporalCompareRequest,
)
from app.services.temporal_change_service import TemporalChangeService
from app.core.exceptions import CadastreException

client = TestClient(app)

# Pune Baseline Building Footprint (EPSG:4326)
PUNE_BASE_COORDS = [
    [73.8560, 18.5200],
    [73.8570, 18.5200],
    [73.8570, 18.5210],
    [73.8560, 18.5210],
    [73.8560, 18.5200],
]

BASE_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [PUNE_BASE_COORDS],
}

BASE_FLOORS = [
    {"level_code": "G00", "level_number": 0, "z_min": 0.0, "z_max": 3.2, "floor_height_m": 3.2, "classification": "GROUND_LEVEL"},
    {"level_code": "L01", "level_number": 1, "z_min": 3.2, "z_max": 6.4, "floor_height_m": 3.2, "classification": "ELEVATED"},
    {"level_code": "L02", "level_number": 2, "z_min": 6.4, "z_max": 9.6, "floor_height_m": 3.2, "classification": "ELEVATED"},
]

BASE_UNITS = [
    {"id": "U-G01", "unit_number": "101", "floor_code": "G00", "z_min": 0.0, "z_max": 3.2, "area_sqm": 85.0, "volume_cu_m": 272.0, "classification": "GROUND_LEVEL"},
    {"id": "U-101", "unit_number": "201", "floor_code": "L01", "z_min": 3.2, "z_max": 6.4, "area_sqm": 85.0, "volume_cu_m": 272.0, "classification": "ELEVATED"},
    {"id": "U-201", "unit_number": "301", "floor_code": "L02", "z_min": 6.4, "z_max": 9.6, "area_sqm": 85.0, "volume_cu_m": 272.0, "classification": "ELEVATED"},
]


def make_baseline_snapshot(entity_id: str = "BLD-PUNE-001") -> DigitalTwinSnapshot:
    return DigitalTwinSnapshot(
        snapshot_id="SNAP-BASE-001",
        entity_id=entity_id,
        entity_type="BUILDING",
        ground_elevation_m=560.0,
        total_height_m=9.6,
        footprint_geojson=BASE_FOOTPRINT,
        floors=BASE_FLOORS,
        units=BASE_UNITS,
        source="REGISTERED_CADASTRAL_TRUTH",
        confidence=1.0,
        uncertainty_m=0.05,
    )


# -------------------------------------------------------------------------
# Test Case 1: Unchanged Building
# -------------------------------------------------------------------------
def test_unchanged_building():
    """Identical baseline and observation should produce zero change events, IoU=1.0, score=0.0."""
    baseline = make_baseline_snapshot()
    observation = make_baseline_snapshot()
    observation.snapshot_id = "SNAP-OBS-001"
    observation.source = "SURVEY_RESURVEY"

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert report.total_change_events == 0
    assert report.technical_change_score == 0.0
    assert report.change_severity == ChangeSeverity.NONE
    assert report.requires_cadastral_review is False
    assert report.footprint_comparison.iou == 1.0
    assert report.footprint_comparison.classification == FootprintChangeClass.NO_SIGNIFICANT_CHANGE
    assert report.height_comparison.height_delta_m == 0.0
    assert report.floor_comparison.floor_count_delta == 0
    assert report.unit_comparison.unit_count_delta == 0


# -------------------------------------------------------------------------
# Test Case 2: Footprint Expansion
# -------------------------------------------------------------------------
def test_footprint_expansion():
    """Expanding footprint geometry outwards should detect positive area delta and IoU < 1.0."""
    baseline = make_baseline_snapshot()

    # Expand polygon towards east and north
    expanded_coords = [
        [73.8560, 18.5200],
        [73.8575, 18.5200],  # expanded eastward
        [73.8575, 18.5215],  # expanded northward
        [73.8560, 18.5215],
        [73.8560, 18.5200],
    ]
    observation = make_baseline_snapshot()
    observation.footprint_geojson = {"type": "Polygon", "coordinates": [expanded_coords]}
    observation.source = "TEST_FIXTURE_SURVEY"

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert report.footprint_comparison.area_delta_sqm > 0
    assert report.footprint_comparison.iou < 1.0
    assert report.footprint_comparison.is_significant is True
    assert any(e.change_type == ChangeType.FOOTPRINT_CHANGED for e in report.change_events)
    assert report.technical_change_score > 0.0
    assert report.requires_cadastral_review is True


# -------------------------------------------------------------------------
# Test Case 3: Footprint Contraction
# -------------------------------------------------------------------------
def test_footprint_contraction():
    """Contracting footprint geometry inwards should detect negative area delta."""
    baseline = make_baseline_snapshot()

    contracted_coords = [
        [73.8562, 18.5202],
        [73.8568, 18.5202],
        [73.8568, 18.5208],
        [73.8562, 18.5208],
        [73.8562, 18.5202],
    ]
    observation = make_baseline_snapshot()
    observation.footprint_geojson = {"type": "Polygon", "coordinates": [contracted_coords]}
    observation.source = "TEST_FIXTURE_SURVEY"

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert report.footprint_comparison.area_delta_sqm < 0
    assert report.footprint_comparison.iou < 1.0
    assert any(e.change_type == ChangeType.FOOTPRINT_CHANGED for e in report.change_events)


# -------------------------------------------------------------------------
# Test Case 4: Building Addition (NEW_BUILDING)
# -------------------------------------------------------------------------
def test_building_addition():
    """Baseline has no footprint (empty parcel), observation has new building footprint."""
    baseline = make_baseline_snapshot()
    baseline.footprint_geojson = None
    baseline.total_height_m = None

    observation = make_baseline_snapshot()
    observation.source = "OBSERVED_DRONE_SURVEY"

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert report.footprint_comparison.classification == FootprintChangeClass.NEW_BUILDING
    assert any(e.change_type == ChangeType.BUILDING_ADDED for e in report.change_events)
    assert report.requires_cadastral_review is True


# -------------------------------------------------------------------------
# Test Case 5: Building Removal (REMOVED_BUILDING)
# -------------------------------------------------------------------------
def test_building_removal():
    """Baseline has registered footprint, observation detects building was demolished/removed."""
    baseline = make_baseline_snapshot()

    observation = make_baseline_snapshot()
    observation.footprint_geojson = None
    observation.total_height_m = 0.0
    observation.floors = []
    observation.units = []
    observation.source = "OBSERVED_SURVEY"

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert report.footprint_comparison.classification == FootprintChangeClass.REMOVED_BUILDING
    assert any(e.change_type == ChangeType.BUILDING_REMOVED for e in report.change_events)
    assert report.requires_cadastral_review is True


# -------------------------------------------------------------------------
# Test Case 6: Height Change (Observed LiDAR)
# -------------------------------------------------------------------------
def test_height_change_observed():
    """Observed vertical elevation delta detects vertical modification."""
    baseline = make_baseline_snapshot()
    baseline.total_height_m = 9.6

    observation = make_baseline_snapshot()
    observation.total_height_m = 13.5  # +3.9m vertical extension
    observation.source = "OBSERVED_LIDAR_SURVEY"

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert report.height_comparison.height_delta_m == 3.9
    assert report.height_comparison.is_significant is True
    assert any(e.change_type == ChangeType.HEIGHT_CHANGED for e in report.change_events)
    assert report.change_events[0].change_classification == ChangeClassification.OBSERVED_CHANGE


# -------------------------------------------------------------------------
# Test Case 7: Floor Structure Change
# -------------------------------------------------------------------------
def test_floor_change_added_floor():
    """Adding a new floor level in observation should produce floor count delta +1."""
    baseline = make_baseline_snapshot()

    observation = make_baseline_snapshot()
    observation.floors = list(BASE_FLOORS) + [
        {"level_code": "L03", "level_number": 3, "z_min": 9.6, "z_max": 12.8, "floor_height_m": 3.2, "classification": "ELEVATED"}
    ]
    observation.total_height_m = 12.8

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert report.floor_comparison.floor_count_delta == 1
    assert "L03" in report.floor_comparison.added_floors
    assert any(e.change_type == ChangeType.FLOOR_STRUCTURE_CHANGED for e in report.change_events)


# -------------------------------------------------------------------------
# Test Case 8: Basement Change
# -------------------------------------------------------------------------
def test_basement_change():
    """Adding an underground basement strata level should detect basement delta."""
    baseline = make_baseline_snapshot()

    observation = make_baseline_snapshot()
    observation.floors = [
        {"level_code": "B01", "level_number": -1, "z_min": -3.5, "z_max": 0.0, "floor_height_m": 3.5, "classification": "UNDERGROUND"}
    ] + list(BASE_FLOORS)

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert report.floor_comparison.basement_delta == 1
    assert any(e.change_type == ChangeType.BASEMENT_CHANGED for e in report.change_events)


# -------------------------------------------------------------------------
# Test Case 9: Vertical Unit Change
# -------------------------------------------------------------------------
def test_vertical_unit_change():
    """Adding or modifying vertical cadastral units detects unit delta."""
    baseline = make_baseline_snapshot()

    observation = make_baseline_snapshot()
    observation.units = list(BASE_UNITS) + [
        {"id": "U-NEW", "unit_number": "302", "floor_code": "L02", "z_min": 6.4, "z_max": 9.6, "area_sqm": 60.0, "volume_cu_m": 192.0, "classification": "ELEVATED"}
    ]

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert report.unit_comparison.unit_count_delta == 1
    assert "302" in report.unit_comparison.added_units
    assert any(e.change_type == ChangeType.VERTICAL_UNIT_CHANGED for e in report.change_events)


# -------------------------------------------------------------------------
# Test Case 10: AI-Derived Change Requiring Review
# -------------------------------------------------------------------------
def test_ai_derived_change_requires_review():
    """AI-proposed changes must be classified as AI_ESTIMATED_CHANGE and require review."""
    baseline = make_baseline_snapshot()

    observation = make_baseline_snapshot()
    observation.total_height_m = 15.0
    observation.source = "AI_ESTIMATED_REGRESSION_MODEL"

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    height_events = [e for e in report.change_events if e.change_type == ChangeType.HEIGHT_CHANGED]
    assert len(height_events) > 0
    assert height_events[0].change_classification == ChangeClassification.AI_ESTIMATED_CHANGE
    assert report.requires_cadastral_review is True


# -------------------------------------------------------------------------
# Test Case 11: Observed Evidence Change
# -------------------------------------------------------------------------
def test_observed_evidence_change():
    """Physical survey or LiDAR observations must be classified as OBSERVED_CHANGE."""
    baseline = make_baseline_snapshot()

    observation = make_baseline_snapshot()
    observation.total_height_m = 12.8
    observation.source = "OBSERVED_LIDAR_POINT_CLOUD"

    report = TemporalChangeService.compare_digital_twins(baseline, observation)

    height_events = [e for e in report.change_events if e.change_type == ChangeType.HEIGHT_CHANGED]
    assert len(height_events) > 0
    assert height_events[0].change_classification == ChangeClassification.OBSERVED_CHANGE


# -------------------------------------------------------------------------
# Test Case 12: Deterministic Reproducibility
# -------------------------------------------------------------------------
def test_deterministic_reproducibility():
    """Running comparison multiple times on identical data yields identical metrics and scores."""
    baseline = make_baseline_snapshot()

    expanded_coords = [
        [73.8560, 18.5200],
        [73.8572, 18.5200],
        [73.8572, 18.5212],
        [73.8560, 18.5212],
        [73.8560, 18.5200],
    ]
    observation = make_baseline_snapshot()
    observation.footprint_geojson = {"type": "Polygon", "coordinates": [expanded_coords]}
    observation.total_height_m = 14.0

    r1 = TemporalChangeService.compare_digital_twins(baseline, observation)
    r2 = TemporalChangeService.compare_digital_twins(baseline, observation)

    assert r1.technical_change_score == r2.technical_change_score
    assert r1.change_severity == r2.change_severity
    assert r1.total_change_events == r2.total_change_events
    assert r1.footprint_comparison.iou == r2.footprint_comparison.iou
    assert r1.footprint_comparison.area_delta_sqm == r2.footprint_comparison.area_delta_sqm
    assert r1.height_comparison.height_delta_m == r2.height_comparison.height_delta_m


# -------------------------------------------------------------------------
# Test Case 13: Invalid Geometry Handling
# -------------------------------------------------------------------------
def test_invalid_geometry_handling():
    """Malformed or invalid geometry should be gracefully handled without unhandled crashes."""
    baseline = make_baseline_snapshot()

    # Degenerate unclosed or invalid polygon
    invalid_geojson = {
        "type": "Polygon",
        "coordinates": [[[73.8560, 18.5200], [73.8560, 18.5200]]],
    }

    observation = make_baseline_snapshot()
    observation.footprint_geojson = invalid_geojson

    # Does not throw unhandled exception
    report = TemporalChangeService.compare_digital_twins(baseline, observation)
    assert report is not None
    assert isinstance(report.technical_change_score, float)


# -------------------------------------------------------------------------
# Test Case 14: Missing Baseline Error Handling
# -------------------------------------------------------------------------
def test_missing_baseline_error_handling():
    """API endpoint /digital-twin/compare without baseline raises 400 Bad Request."""
    obs_snap = make_baseline_snapshot().model_dump()
    payload = {
        "new_observation": obs_snap,
    }

    response = client.post("/api/v1/digital-twin/compare", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "MISSING_BASELINE"


# -------------------------------------------------------------------------
# Test Case 15: Missing Observation Error Handling
# -------------------------------------------------------------------------
def test_missing_observation_error_handling():
    """API endpoint /digital-twin/compare without new_observation payload is rejected with 422."""
    payload = {
        "parcel_id": "test-parcel-id",
    }

    response = client.post("/api/v1/digital-twin/compare", json=payload)
    assert response.status_code == 422


# -------------------------------------------------------------------------
# Test Case 16: Live FastAPI Endpoint Integration
# -------------------------------------------------------------------------
def test_fastapi_compare_endpoint_live():
    """Valid POST /api/v1/digital-twin/compare returns 200 OK with fully structured report."""
    baseline_snap = make_baseline_snapshot().model_dump()
    obs_snap = make_baseline_snapshot().model_dump()
    obs_snap["source"] = "TEST_FIXTURE_OBSERVATION"
    obs_snap["total_height_m"] = 12.8

    payload = {
        "baseline_snapshot": baseline_snap,
        "new_observation": obs_snap,
        "config": {
            "is_test_fixture": True,
        }
    }

    response = client.post("/api/v1/digital-twin/compare", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    data = res["data"]
    assert "comparison_id" in data
    assert data["is_test_fixture"] is True
    assert data["height_comparison"]["height_delta_m"] == 3.2
    assert "legal_disclaimer" in data
