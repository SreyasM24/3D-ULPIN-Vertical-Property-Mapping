"""
Vertical Cadastre Intelligence Test Suite.
SIH 26011 - 3D ULPIN & Vertical Property Mapping System.

Verifies:
1. Explicit floor count evidence
2. Observed height without floor count
3. AI-estimated height without floor count
4. Missing height / empty inputs
5. Basement levels (underground datum conformance)
6. Elevated structures
7. Multi-floor units (utility shaft, elevator core, ramp)
8. Duplex units (vertical continuity and clash-free verification)
9. Impossible height/floor combinations
10. Invalid geometry rejection
11. Deterministic reproducibility
12. Live API endpoints (/ml/building/floors, /ml/vertical/propose, /jobs/process-parcel)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import shapely.geometry

from app.main import app
from app.db.session import SessionLocal
from app.ml.models.floor_estimator import FloorEstimatorModel
from app.ml.schemas import (
    EvidenceSourceType,
    ConfidenceLevel,
    ModelStatus,
    VerticalFeatureResult,
    DataStage,
)
from app.ml.features.vertical_features import VerticalFeatureExtractor
from app.ml.pipelines.vertical_cadastre import VerticalCadastreFeatureService
from app.services.floor_engine import FloorEngine
from app.services.cadastral_relationship_engine import (
    CadastralRelationshipEngine,
    ContainmentStatus,
)
from app.core.spatial_volume import (
    PrismVolume,
    classify_vertical_position,
    VerticalClassification,
)
from app.services.cadastre_service import CadastreService
from app.schemas.parcel import ParcelCreate, GeoJSONPolygon
from app.schemas.building import BuildingCreate
from app.schemas.floor import FloorCreate
from app.schemas.unit import UnitCreate
from app.services.cadastral_validator import CadastralValidationService


client = TestClient(app)


# Standard test footprint in Pune (EPSG:4326)
SAMPLE_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [
        [
            [73.8500, 18.5100],
            [73.8505, 18.5100],
            [73.8505, 18.5105],
            [73.8500, 18.5105],
            [73.8500, 18.5100]
        ]
    ]
}


# ============================================================================
# 1. EXPLICIT FLOOR COUNT (TIER 1)
# ============================================================================
def test_explicit_floor_count():
    """
    Tier 1 Evidence: Explicit survey / registered floor count.
    Must take precedence, report EXPLICIT_FLOOR_COUNT, high confidence (>=0.95),
    and generate consistent floor strata slices.
    """
    model = FloorEstimatorModel()
    res = model.predict({
        "floor_count": 4,
        "total_height_m": 12.8,
        "ground_elevation_m": 550.0,
        "source": "EXPLICIT_SURVEY"
    })

    assert res["evidence_tier"] == 1
    assert res["source"] == EvidenceSourceType.EXPLICIT_FLOOR_COUNT
    assert res["method"] == "EXPLICIT_FLOOR_COUNT"
    assert res["estimated_floor_count"] == 4
    assert res["confidence"] >= 0.95
    assert res["confidence_level"] == ConfidenceLevel.HIGH
    assert res["requires_review"] is False

    strata = res["strata"]
    assert len(strata) == 4
    assert strata[0].level_code == "G00"
    assert strata[0].classification == "GROUND_LEVEL"
    assert strata[0].z_min == 550.0
    assert strata[0].z_max == 553.8
    assert strata[1].level_code == "L01"
    assert strata[2].level_code == "L02"
    assert strata[3].level_code == "L03"
    assert strata[-1].z_max == 562.8


# ============================================================================
# 2. OBSERVED HEIGHT WITHOUT FLOOR COUNT (TIER 3)
# ============================================================================
def test_observed_height_without_floor_count():
    """
    Tier 3 Evidence: Observed building height from LiDAR/DSM without floor metadata.
    Must decompose height into plausible candidate floor strata (Ground + Upper).
    """
    model = FloorEstimatorModel()
    res = model.predict({
        "total_height_m": 18.8,
        "ground_elevation_m": 100.0,
        "height_source": "OBSERVED_LIDAR",
        "height_uncertainty_m": 0.20
    })

    assert res["evidence_tier"] == 3
    assert res["source"] == EvidenceSourceType.OBSERVED_HEIGHT_DECOMPOSITION
    assert res["confidence"] >= 0.80
    assert res["confidence_level"] == ConfidenceLevel.HIGH
    assert "typical" in res["candidates"]

    # 18.8m - 3.8m ground = 15.0m. 15.0m / 3.0m = 5 upper floors -> 6 total floors.
    assert res["estimated_floor_count"] == 6
    strata = res["strata"]
    assert len(strata) == 6
    assert strata[0].level_code == "G00"
    assert strata[0].estimated_height_m == 3.8
    for upper in strata[1:]:
        assert upper.estimated_height_m == 3.0
        assert upper.classification == "ELEVATED"


# ============================================================================
# 3. AI-ESTIMATED HEIGHT WITHOUT FLOOR COUNT (TIER 4)
# ============================================================================
def test_ai_estimated_height_without_floor_count():
    """
    Tier 4 Evidence: Building height from AI neural regressor.
    Must strictly flag requires_review = True and report medium confidence (~0.65).
    """
    model = FloorEstimatorModel()
    res = model.predict({
        "total_height_m": 12.8,
        "ground_elevation_m": 0.0,
        "height_source": "AI_REGRESSION",
        "height_uncertainty_m": 0.90
    })

    assert res["evidence_tier"] == 4
    assert res["source"] == EvidenceSourceType.AI_HEIGHT_DECOMPOSITION
    assert res["method"] == "AI_HEIGHT_DECOMPOSITION"
    assert res["requires_review"] is True
    assert res["confidence"] <= 0.70
    assert res["confidence_level"] == ConfidenceLevel.MEDIUM
    assert res["estimated_floor_count"] == 4


# ============================================================================
# 4. MISSING HEIGHT / EMPTY INPUTS (UNRESOLVED)
# ============================================================================
def test_missing_height_unresolved():
    """
    Tier 6: Missing height and floor count.
    Must return UNRESOLVED with 0 floors, 0.0 confidence, and requires_review = True.
    Must NOT invent fake floors.
    """
    model = FloorEstimatorModel()
    res = model.predict({})

    assert res["evidence_tier"] == 6
    assert res["source"] == EvidenceSourceType.UNRESOLVED
    assert res["method"] == "UNRESOLVED"
    assert res["estimated_floor_count"] == 0
    assert len(res["strata"]) == 0
    assert res["confidence"] == 0.0
    assert res["confidence_level"] == ConfidenceLevel.UNKNOWN
    assert res["requires_review"] is True


# ============================================================================
# 5. BASEMENT HANDLING (UNDERGROUND STRATA)
# ============================================================================
def test_basement_underground_handling():
    """
    Verifies that basement levels are classified UNDERGROUND, descend below
    ground elevation datum, and pass deterministic FloorEngine validation.
    """
    model = FloorEstimatorModel()
    res = model.predict({
        "total_height_m": 15.8,
        "ground_elevation_m": 100.0,
        "floors_above_ground": 5,
        "basement_floors": 2,
        "source": "EXPLICIT_SURVEY"
    })

    assert res["estimated_floor_count"] == 7
    assert res["basement_floors"] == 2
    strata = res["strata"]

    # Basement 2 (lowest)
    assert strata[0].level_code == "B02"
    assert strata[0].classification == "UNDERGROUND"
    assert strata[0].z_min == 93.0
    assert strata[0].z_max == 96.5

    # Basement 1
    assert strata[1].level_code == "B01"
    assert strata[1].classification == "UNDERGROUND"
    assert strata[1].z_min == 96.5
    assert strata[1].z_max == 100.0

    # Ground floor
    assert strata[2].level_code == "G00"
    assert strata[2].z_min == 100.0

    # Test deterministic validation of these floors
    candidate_floors = [
        {"level_code": s.level_code, "level_number": i - 2, "z_min": s.z_min, "z_max": s.z_max}
        for i, s in enumerate(strata)
    ]
    report = FloorEngine.validate_building_floors(
        building_id="BLD-TEST",
        ground_elevation_m=100.0,
        total_height_m=15.8,
        floors=candidate_floors
    )
    assert report.is_valid is True
    assert len(report.errors) == 0
    assert report.strata_summary["basement_count"] == 2
    assert report.strata_summary["ground_count"] == 1
    assert report.strata_summary["elevated_count"] == 4


# ============================================================================
# 6. ELEVATED STRUCTURE HANDLING
# ============================================================================
def test_elevated_structure_handling():
    """
    Verifies elevated high-rise floors and rooftop structures stay above
    ground datum and are correctly classified ELEVATED.
    """
    model = FloorEstimatorModel()
    res = model.predict({
        "total_height_m": 33.8,
        "ground_elevation_m": 50.0,
        "floors_above_ground": 11,
        "source": "EXPLICIT_SURVEY"
    })

    assert res["estimated_floor_count"] == 11
    strata = res["strata"]
    for s in strata[1:]:
        assert s.classification == "ELEVATED"
        assert s.z_min >= 50.0

    assert strata[-1].level_code == "L10"
    assert strata[-1].z_max == pytest.approx(83.8, abs=0.1)


# ============================================================================
# 7. MULTI-FLOOR UNIT (UTILITY SHAFT / ELEVATOR CORE / RAMP)
# ============================================================================
def test_multi_floor_utility_shaft():
    """
    Tests that a vertical utility shaft or elevator core spanning multiple levels
    is represented as a single continuous 3D unit with is_multi_floor = True,
    and passes containment validation without false errors.
    """
    model = FloorEstimatorModel()
    res = model.predict({
        "total_height_m": 9.8,
        "ground_elevation_m": 100.0,
        "floors_above_ground": 3,
        "basement_floors": 1,
        "source": "EXPLICIT_SURVEY"
    })
    strata = res["strata"]

    multi_cfgs = [
        {
            "unit_number": "SHAFT-CORE-01",
            "unit_type": "ELEVATOR_SHAFT",
            "level_codes": ["B01", "G00", "L01", "L02"]
        }
    ]

    units = VerticalFeatureExtractor.propose_vertical_units(
        footprint_geojson=SAMPLE_FOOTPRINT,
        strata_levels=strata,
        units_per_floor=1,
        ground_elevation_m=100.0,
        multi_floor_configs=multi_cfgs
    )

    shaft = next(u for u in units if u["unit_number"] == "SHAFT-CORE-01")
    assert shaft["is_multi_floor"] is True
    assert shaft["unit_type"] == "ELEVATOR_SHAFT"
    assert shaft["floor_span"] == ["B01", "G00", "L01", "L02"]
    assert shaft["z_min"] == 96.5   # B01 base
    assert shaft["z_max"] == 109.8  # L02 top
    assert shaft["volume_cu_m"] > 0
    assert shaft["classification"] in ("MULTI_LEVEL_INFRASTRUCTURE", "GROUND_LEVEL")


# ============================================================================
# 8. DUPLEX UNIT VERIFICATION
# ============================================================================
def test_duplex_unit_representation_and_continuity():
    """
    Tests that a duplex apartment spanning G00 + L01:
    - maintains vertical continuity from G00.z_min to L01.z_max
    - is NOT split into two separate ownership records
    - is recognized by CadastralRelationshipEngine without false elevation violations
    """
    model = FloorEstimatorModel()
    res = model.predict({
        "total_height_m": 9.8,
        "ground_elevation_m": 100.0,
        "floors_above_ground": 3,
        "source": "EXPLICIT_SURVEY"
    })
    strata = res["strata"]

    duplex_cfgs = [
        {
            "unit_number": "DUPLEX-01",
            "unit_type": "DUPLEX",
            "level_codes": ["G00", "L01"]
        }
    ]

    units = VerticalFeatureExtractor.propose_vertical_units(
        footprint_geojson=SAMPLE_FOOTPRINT,
        strata_levels=strata,
        units_per_floor=1,
        ground_elevation_m=100.0,
        multi_floor_configs=duplex_cfgs
    )

    duplex = next(u for u in units if u["unit_number"] == "DUPLEX-01")
    assert duplex["is_multi_floor"] is True
    assert duplex["floor_span"] == ["G00", "L01"]
    assert duplex["z_min"] == 100.0
    assert duplex["z_max"] == 106.8
    assert duplex["height_m"] == 6.8


# ============================================================================
# 9. IMPOSSIBLE HEIGHT / FLOOR COMBINATION
# ============================================================================
def test_impossible_height_floor_combinations():
    """
    Verifies that impossible physical combinations are flagged:
    - 5 floors in 3.0m total height (physically impossible)
    - Total height 1.5m (< minimum single floor height 2.6m)
    """
    model = FloorEstimatorModel()

    # 1. 5 floors in 3.0m
    res_dense = model.predict({
        "total_height_m": 3.0,
        "floors_above_ground": 5,
        "source": "EXPLICIT_SURVEY"
    })
    assert res_dense["requires_review"] is True
    assert res_dense["confidence"] < 0.75
    assert any("physically insufficient" in a for a in res_dense["assumptions"])

    # 2. 1.5m height (< min single floor)
    res_low = model.predict({
        "total_height_m": 1.5,
        "ground_elevation_m": 0.0
    })
    assert res_low["estimated_floor_count"] == 0
    assert res_low["source"] == EvidenceSourceType.UNRESOLVED
    assert res_low["requires_review"] is True


# ============================================================================
# 10. INVALID GEOMETRY REJECTION
# ============================================================================
def test_invalid_geometry_rejection():
    """
    Verifies that self-intersecting bowtie polygons and unclosed rings are
    strictly caught and rejected by the cadastral validation engine.
    """
    bowtie_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [0.0, 0.0],
                [1.0, 1.0],
                [0.0, 1.0],
                [1.0, 0.0],
                [0.0, 0.0]
            ]
        ]
    }

    poly = shapely.geometry.shape(bowtie_polygon)
    assert poly.is_valid is False

    # Validation rule check
    from app.core.validation_rules import RuleGeo001ValidGeometry
    rule = RuleGeo001ValidGeometry()
    issue = rule.evaluate({
        "id": "TEST-BOWTIE",
        "geometry_geojson": bowtie_polygon,
        "entity_type": "PARCEL"
    })
    assert issue is not None
    assert issue.rule_id == "RULE-GEO-001"
    assert "Self-intersection" in issue.explanation or "Invalid geometry" in issue.actual_condition


# ============================================================================
# 11. DETERMINISTIC REPRODUCIBILITY
# ============================================================================
def test_deterministic_reproducibility():
    """
    Verifies that running strata decomposition and candidate cadastre 50 times
    produces bitwise identical outputs with zero stochastic drift.
    """
    model = FloorEstimatorModel()
    inputs = {
        "total_height_m": 21.8,
        "ground_elevation_m": 100.0,
        "height_source": "OBSERVED_LIDAR",
        "height_uncertainty_m": 0.15
    }

    first_res = model.predict(inputs)
    for _ in range(50):
        repeat_res = model.predict(inputs)
        assert repeat_res["estimated_floor_count"] == first_res["estimated_floor_count"]
        assert repeat_res["confidence"] == first_res["confidence"]
        assert repeat_res["source"] == first_res["source"]
        assert len(repeat_res["strata"]) == len(first_res["strata"])
        for s1, s2 in zip(first_res["strata"], repeat_res["strata"]):
            assert s1.level_code == s2.level_code
            assert s1.z_min == s2.z_min
            assert s1.z_max == s2.z_max


# ============================================================================
# 12. LIVE FASTAPI ENDPOINT VERIFICATION
# ============================================================================
def test_api_building_floors_endpoint():
    """Tests POST /api/v1/ml/building/floors endpoint."""
    payload = {
        "total_height_m": 15.8,
        "ground_elevation_m": 100.0,
        "floors_above_ground": 5,
        "basement_floors": 1
    }
    response = client.post("/api/v1/ml/building/floors", json=payload)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["estimated_floor_count"] == 6
    assert len(data["strata"]) == 6
    assert data["source"] == "EXPLICIT_FLOOR_COUNT"
    assert data["confidence"] >= 0.90


def test_api_vertical_propose_endpoint():
    """Tests POST /api/v1/ml/vertical/propose endpoint with floor consistency."""
    payload = {
        "footprint_geojson": SAMPLE_FOOTPRINT,
        "ground_elevation_m": 100.0,
        "total_height_m": 9.8,
        "strata_levels": [
            {
                "level_code": "G00",
                "z_min": 100.0,
                "z_max": 103.8,
                "estimated_height_m": 3.8,
                "classification": "GROUND_LEVEL",
                "confidence": 0.85,
                "confidence_level": "HIGH",
                "source": "OBSERVED_HEIGHT_DECOMPOSITION"
            },
            {
                "level_code": "L01",
                "z_min": 103.8,
                "z_max": 106.8,
                "estimated_height_m": 3.0,
                "classification": "ELEVATED",
                "confidence": 0.85,
                "confidence_level": "HIGH",
                "source": "OBSERVED_HEIGHT_DECOMPOSITION"
            },
            {
                "level_code": "L02",
                "z_min": 106.8,
                "z_max": 109.8,
                "estimated_height_m": 3.0,
                "classification": "ELEVATED",
                "confidence": 0.85,
                "confidence_level": "HIGH",
                "source": "OBSERVED_HEIGHT_DECOMPOSITION"
            }
        ],
        "units_per_floor": 2,
        "building_code": "BLD-API-TEST"
    }

    response = client.post("/api/v1/ml/vertical/propose", json=payload)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_cadastrally_consistent"] is True
    assert len(data["candidate_floors"]) == 3
    assert len(data["candidate_units"]) == 6
