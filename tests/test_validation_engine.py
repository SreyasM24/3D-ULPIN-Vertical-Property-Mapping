"""
Comprehensive Test Suite for Advanced Cadastral Topology and Validation Engine (SIH 26011).
Tests deterministic rules, 3D clash analysis, strata consistency, multi-floor units,
quality scoring, audit history persistence, and REST endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.validation_rules import (
    ValidationRuleRegistry,
    RuleCategory,
    RuleSeverity,
)
from app.services.clash_analysis_engine import AdvancedClashEngine
from app.schemas.validation import ClashClassification, QualityGrade
from app.services.cadastral_quality_scorer import CadastralQualityScorer
from app.services.cadastral_validator import CadastralValidationService
from app.models.parcel import LandParcel
from app.models.building import Building
from app.models.floor import FloorLevel
from app.models.unit import VerticalUnit


# ============================================================================
# 1. RULE REGISTRY & DISCOVERY
# ============================================================================

def test_validation_rule_registry_listing():
    """Verifies that all 20+ stable rules are registered and discoverable."""
    rules = ValidationRuleRegistry.list_rules()
    assert len(rules) >= 18
    rule_ids = {r.rule_id for r in rules}

    # Verify key rules across categories
    assert "RULE-GEO-001" in rule_ids
    assert "RULE-GEO-002" in rule_ids
    assert "RULE-GEO-003" in rule_ids
    assert "RULE-HIER-001" in rule_ids
    assert "RULE-HIER-003" in rule_ids
    assert "RULE-HIER-005" in rule_ids
    assert "RULE-FLR-001" in rule_ids
    assert "RULE-FLR-002" in rule_ids
    assert "RULE-FLR-006" in rule_ids
    assert "RULE-TOPO-001" in rule_ids
    assert "RULE-TOPO-003" in rule_ids
    assert "RULE-UNIT-001" in rule_ids
    assert "RULE-UNIT-002" in rule_ids
    assert "RULE-UNIT-003" in rule_ids
    assert "RULE-INF-001" in rule_ids


def test_api_list_validation_rules(client: TestClient):
    """GET /api/v1/validation/rules returns the catalog of rules."""
    resp = client.get("/api/v1/validation/rules")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    assert len(data) >= 18
    first = data[0]
    assert "rule_id" in first
    assert "category" in first
    assert "severity" in first
    assert "description" in first


# ============================================================================
# 2. INDEPENDENT GEOMETRY RULES
# ============================================================================

def test_rule_geo_001_self_intersection():
    """Bowtie self-intersecting polygon triggers RULE-GEO-001 ERROR."""
    rule = ValidationRuleRegistry.get_rule("RULE-GEO-001")
    bowtie_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8560, 18.5200],
                [73.8570, 18.5210],
                [73.8570, 18.5200],
                [73.8560, 18.5210],
                [73.8560, 18.5200]
            ]
        ]
    }
    issue = rule.evaluate({
        "id": "test-geo-1",
        "entity_type": "PARCEL",
        "geometry_geojson": bowtie_polygon
    })
    assert issue is not None
    assert issue.rule_id == "RULE-GEO-001"
    assert issue.severity == RuleSeverity.ERROR
    assert "self-intersection" in issue.actual_condition.lower()


def test_rule_geo_002_unclosed_ring():
    """Unclosed linear ring triggers RULE-GEO-002 ERROR."""
    rule = ValidationRuleRegistry.get_rule("RULE-GEO-002")
    unclosed_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8560, 18.5200],
                [73.8570, 18.5200],
                [73.8570, 18.5210],
                [73.8560, 18.5210]  # Missing closure
            ]
        ]
    }
    issue = rule.evaluate({
        "id": "test-geo-2",
        "entity_type": "PARCEL",
        "geometry_geojson": unclosed_polygon
    })
    assert issue is not None
    assert issue.rule_id == "RULE-GEO-002"
    assert issue.severity == RuleSeverity.ERROR


def test_rule_geo_003_zero_area():
    """Degenerate zero-area line/point polygon triggers RULE-GEO-003 ERROR."""
    rule = ValidationRuleRegistry.get_rule("RULE-GEO-003")
    zero_area_poly = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8560, 18.5200],
                [73.8560, 18.5200],
                [73.8560, 18.5200],
                [73.8560, 18.5200]
            ]
        ]
    }
    issue = rule.evaluate({
        "id": "test-geo-3",
        "entity_type": "UNIT",
        "footprint_geojson": zero_area_poly
    })
    assert issue is not None
    assert issue.rule_id == "RULE-GEO-003"


# ============================================================================
# 3. HIERARCHY RULES & MULTI-FLOOR ENTITIES
# ============================================================================

def test_rule_hier_001_building_spill(sample_parcel_geojson):
    """Building footprint spilling outside parcel triggers RULE-HIER-001 ERROR."""
    rule = ValidationRuleRegistry.get_rule("RULE-HIER-001")
    spilling_building = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8565, 18.5205],
                [73.8580, 18.5205],  # Extends far past parcel 73.8570
                [73.8580, 18.5215],
                [73.8565, 18.5215],
                [73.8565, 18.5205]
            ]
        ]
    }
    issue = rule.evaluate({
        "id": "bld-spill",
        "building_code": "BLD-SPILL",
        "footprint_geojson": spilling_building,
        "parcel_geometry_geojson": sample_parcel_geojson
    })
    assert issue is not None
    assert issue.rule_id == "RULE-HIER-001"
    assert issue.severity == RuleSeverity.ERROR
    assert issue.measured_values["excess_area_sqm"] > 0


def test_rule_hier_005_multi_floor_duplex_not_flagged():
    """
    Legitimate multi-floor unit (e.g. DUPLEX spanning L01 and L02)
    is NOT incorrectly flagged as a vertical strata violation.
    """
    rule = ValidationRuleRegistry.get_rule("RULE-HIER-005")

    # Standard unit exceeding floor bounds -> ERROR
    standard_issue = rule.evaluate({
        "id": "unit-apt",
        "unit_number": "101",
        "unit_type": "APARTMENT",
        "z_min": 100.0,
        "z_max": 106.0,  # Floor only goes up to 103.0
        "floor_z_min": 100.0,
        "floor_z_max": 103.0,
        "is_multi_floor": False
    })
    assert standard_issue is not None
    assert standard_issue.rule_id == "RULE-HIER-005"

    # Duplex unit designated as multi-floor -> NO ERROR
    duplex_issue = rule.evaluate({
        "id": "unit-duplex",
        "unit_number": "DUPLEX-01",
        "unit_type": "DUPLEX",
        "z_min": 100.0,
        "z_max": 106.0,
        "floor_z_min": 100.0,
        "floor_z_max": 103.0,
        "is_multi_floor": True
    })
    assert duplex_issue is None


# ============================================================================
# 4. FLOOR STRATA TOPOLOGY RULES
# ============================================================================

def test_floor_strata_overlap_and_gaps():
    """Detects vertical overlap and vertical gaps between floors."""
    rule_overlap = ValidationRuleRegistry.get_rule("RULE-FLR-001")
    rule_gap = ValidationRuleRegistry.get_rule("RULE-FLR-002")
    rule_dupe = ValidationRuleRegistry.get_rule("RULE-FLR-003")

    # 1. Overlapping floors
    overlapping_floors = [
        {"level_code": "L01", "level_number": 1, "z_min": 100.0, "z_max": 104.0},
        {"level_code": "L02", "level_number": 2, "z_min": 103.0, "z_max": 107.0}  # Overlaps by 1.0m
    ]
    iss_ov = rule_overlap.evaluate({"id": "b1", "building_code": "BLD-1", "floors": overlapping_floors})
    assert iss_ov is not None
    assert iss_ov.rule_id == "RULE-FLR-001"
    assert iss_ov.measured_values["overlap_m"] == 1.0

    # 2. Floor with large unexplained vertical gap (> 0.5m)
    gapped_floors = [
        {"level_code": "L01", "level_number": 1, "z_min": 100.0, "z_max": 103.0},
        {"level_code": "L02", "level_number": 2, "z_min": 105.0, "z_max": 108.0}  # 2.0m gap
    ]
    iss_gap = rule_gap.evaluate({"id": "b1", "building_code": "BLD-1", "floors": gapped_floors})
    assert iss_gap is not None
    assert iss_gap.rule_id == "RULE-FLR-002"
    assert iss_gap.severity == RuleSeverity.WARNING

    # 3. Duplicate floor code
    dupe_floors = [
        {"level_code": "L01", "level_number": 1, "z_min": 100.0, "z_max": 103.0},
        {"level_code": "L01", "level_number": 2, "z_min": 103.0, "z_max": 106.0}
    ]
    iss_dupe = rule_dupe.evaluate({"id": "b1", "building_code": "BLD-1", "floors": dupe_floors})
    assert iss_dupe is not None
    assert iss_dupe.rule_id == "RULE-FLR-003"


def test_rule_flr_006_basement_datum_consistency():
    """Basement ceiling breaching above ground level triggers RULE-FLR-006 ERROR."""
    rule = ValidationRuleRegistry.get_rule("RULE-FLR-006")
    issue = rule.evaluate({
        "id": "fl-b01",
        "level_code": "B01",
        "level_number": -1,
        "level_type": "BASEMENT",
        "z_min": 97.0,
        "z_max": 103.0,  # Ground is 100.0, breaching by 3.0m
        "ground_elevation_m": 100.0
    })
    assert issue is not None
    assert issue.rule_id == "RULE-FLR-006"
    assert issue.severity == RuleSeverity.ERROR


# ============================================================================
# 5. ADVANCED 3D CLASH CLASSIFICATION
# ============================================================================

def test_clash_engine_private_property_vs_common_area(sample_unit_geojson):
    """
    Verifies that clash analysis classifies private collisions as CRITICAL,
    common area overlap as INFO, and near-boundary touches as WARNING.
    """
    # 1. Two private apartments intersecting
    units_private = [
        {
            "id": "apt-1",
            "unit_number": "101",
            "unit_type": "APARTMENT",
            "footprint_geojson": sample_unit_geojson,
            "z_min": 10.0,
            "z_max": 13.0
        },
        {
            "id": "apt-2",
            "unit_number": "102",
            "unit_type": "APARTMENT",
            "footprint_geojson": sample_unit_geojson,
            "z_min": 11.0,
            "z_max": 14.0
        }
    ]
    clashes_crit = AdvancedClashEngine.analyze_unit_clashes(units_private)
    assert len(clashes_crit) == 1
    assert clashes_crit[0].classification == ClashClassification.CRITICAL
    assert clashes_crit[0].vertical_overlap_m == 2.0
    assert clashes_crit[0].estimated_overlap_volume_cu_m > 0

    # 2. Private unit and common area utility / shaft
    units_common = [
        {
            "id": "apt-1",
            "unit_number": "101",
            "unit_type": "APARTMENT",
            "footprint_geojson": sample_unit_geojson,
            "z_min": 10.0,
            "z_max": 13.0
        },
        {
            "id": "shaft-1",
            "unit_number": "SHAFT-A",
            "unit_type": "UTILITY",
            "footprint_geojson": sample_unit_geojson,
            "z_min": 10.0,
            "z_max": 20.0
        }
    ]
    clashes_comm = AdvancedClashEngine.analyze_unit_clashes(units_common)
    assert len(clashes_comm) == 1
    assert clashes_comm[0].classification == ClashClassification.UNKNOWN_REQUIRES_REVIEW


def test_underground_tunnel_coexistence_vs_collision(sample_unit_geojson):
    """
    Underground tunnel below apartment volume = NO CLASH (valid coexistence).
    Tunnel intersecting basement property volume = CLASSIFIED CONFLICT.
    """
    # Tunnel completely beneath apartment:
    # Apartment: [100.0, 103.0]
    # Tunnel: [85.0, 90.0]
    units_coexist = [
        {
            "id": "apt-1",
            "unit_number": "101",
            "unit_type": "APARTMENT",
            "footprint_geojson": sample_unit_geojson,
            "z_min": 100.0,
            "z_max": 103.0
        },
        {
            "id": "tunnel-1",
            "unit_number": "METRO-TUNNEL",
            "unit_type": "TUNNEL",
            "footprint_geojson": sample_unit_geojson,
            "z_min": 85.0,
            "z_max": 90.0
        }
    ]
    clashes_coexist = AdvancedClashEngine.analyze_unit_clashes(units_coexist)
    assert len(clashes_coexist) == 0  # Valid coexistence, no vertical overlap!

    # Tunnel physically intersecting basement parking [88.0, 92.0]
    units_intersect = [
        {
            "id": "basement-pkg",
            "unit_number": "PKG-B02",
            "unit_type": "PARKING",
            "footprint_geojson": sample_unit_geojson,
            "z_min": 88.0,
            "z_max": 92.0
        },
        {
            "id": "tunnel-1",
            "unit_number": "METRO-TUNNEL",
            "unit_type": "TUNNEL",
            "footprint_geojson": sample_unit_geojson,
            "z_min": 85.0,
            "z_max": 90.0
        }
    ]
    clashes_intersect = AdvancedClashEngine.analyze_unit_clashes(units_intersect)
    assert len(clashes_intersect) == 1
    assert clashes_intersect[0].vertical_overlap_m == 2.0
    assert clashes_intersect[0].overlap_elevation_range == [88.0, 90.0]


# ============================================================================
# 6. EXPLAINABLE QUALITY SCORER
# ============================================================================

def test_quality_scorer_calculations():
    """Tests 0-100 deterministic scoring, explainable deductions, and neutral grades."""
    # 1. Clean data with full metadata -> 100 pts / HIGH_CONFIDENCE
    score_clean = CadastralQualityScorer.calculate_score(
        issues=[],
        has_crs_metadata=True,
        has_ulpin=True,
        has_survey_number=True,
        has_spatial_metadata=True
    )
    assert score_clean.total_score == 100.0
    assert score_clean.grade == QualityGrade.HIGH_CONFIDENCE
    assert len(score_clean.deductions) == 0

    # 2. Data with missing metadata
    score_no_meta = CadastralQualityScorer.calculate_score(
        issues=[],
        has_crs_metadata=False,  # -8 pts
        has_ulpin=False,         # -4 pts
        has_survey_number=False, # -3 pts
        has_spatial_metadata=False # -3 pts
    )
    assert score_no_meta.total_score == 82.0
    assert score_no_meta.grade == QualityGrade.GOOD_QUALITY
    assert len(score_no_meta.deductions) == 4

    # 3. Data with critical geometry error
    critical_issue = ValidationRuleRegistry.get_rule("RULE-GEO-001").evaluate({
        "id": "bad-geom",
        "entity_type": "PARCEL",
        "geometry_geojson": {
            "type": "Polygon",
            "coordinates": [[[73.8, 18.5], [73.9, 18.6], [73.9, 18.5], [73.8, 18.6], [73.8, 18.5]]]
        }
    })
    score_bad = CadastralQualityScorer.calculate_score(
        issues=[critical_issue],
        has_crs_metadata=True,
        has_ulpin=True,
        has_survey_number=True,
        has_spatial_metadata=True
    )
    assert score_bad.geometry_validity == 12.5  # 25 - 12.5
    assert score_bad.total_score == 87.5
    assert score_bad.grade == QualityGrade.GOOD_QUALITY


# ============================================================================
# 7. END-TO-END VALIDATION WORKFLOW & APIS
# ============================================================================

def test_full_parcel_validation_workflow(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson,
    sample_unit_geojson
):
    """
    Creates complete hierarchy (Parcel -> Building -> Floor -> Unit)
    and verifies POST /api/v1/validation/parcel/{id} executes all rules,
    returns an explainable report, and persists a validation run record.
    """
    # 1. Create Parcel
    p_resp = client.post("/api/v1/parcels/", json={
        "state_code": "MH",
        "district_code": "PUN",
        "village_code": "VIL01",
        "survey_number": "SRV-VAL-01",
        "geometry_geojson": sample_parcel_geojson,
        "base_elevation_m": 100.0,
        "spatial_metadata": {"crs": "EPSG:4326"}
    })
    assert p_resp.status_code == 201
    parcel_id = p_resp.json()["data"]["id"]

    # 2. Create Building
    b_resp = client.post("/api/v1/buildings/", json={
        "parcel_id": parcel_id,
        "building_name": "Validation Test Tower",
        "building_code": "VTT-01",
        "structure_type": "RESIDENTIAL",
        "floors_above_ground": 2,
        "basement_floors": 0,
        "total_height_m": 8.0,
        "ground_elevation_m": 100.0,
        "footprint_geojson": sample_building_geojson
    })
    assert b_resp.status_code == 201
    building_id = b_resp.json()["data"]["id"]

    # 3. Create Floors (L01 and L02)
    fl1_resp = client.post("/api/v1/floors/", json={
        "building_id": building_id,
        "level_number": 1,
        "level_code": "L01",
        "level_type": "TYPICAL_FLOOR",
        "z_min": 100.0,
        "z_max": 103.5
    })
    assert fl1_resp.status_code == 201
    floor1_id = fl1_resp.json()["data"]["id"]

    fl2_resp = client.post("/api/v1/floors/", json={
        "building_id": building_id,
        "level_number": 2,
        "level_code": "L02",
        "level_type": "TYPICAL_FLOOR",
        "z_min": 103.5,
        "z_max": 107.0
    })
    assert fl2_resp.status_code == 201

    # 4. Create Vertical Unit
    u_resp = client.post("/api/v1/units/", json={
        "floor_id": floor1_id,
        "unit_number": "101",
        "unit_code": "U-101",
        "unit_type": "APARTMENT",
        "footprint_geojson": sample_unit_geojson,
        "z_min": 100.0,
        "z_max": 103.5
    })
    assert u_resp.status_code == 201
    unit_id = u_resp.json()["data"]["id"]

    # 5. Execute Validation API
    val_resp = client.post(f"/api/v1/validation/parcel/{parcel_id}?persist=true")
    assert val_resp.status_code == 200
    report = val_resp.json()["data"]

    assert report["is_valid"] is True
    assert report["parcel_id"] == parcel_id
    assert report["total_rules_executed"] >= 15
    assert report["quality_score"]["total_score"] >= 90.0
    assert report["quality_score"]["grade"] == QualityGrade.HIGH_CONFIDENCE.value
    assert len(report["issues"]) == 0
    assert "validation_run_id" in report
    run_id = report["validation_run_id"]

    # 6. Retrieve Report by Run ID
    rep_get = client.get(f"/api/v1/validation/report/{run_id}")
    assert rep_get.status_code == 200
    assert rep_get.json()["data"]["validation_run_id"] == run_id

    # 7. Retrieve Validation History for Parcel
    hist_resp = client.get(f"/api/v1/validation/history/{parcel_id}")
    assert hist_resp.status_code == 200
    hist = hist_resp.json()["data"]
    assert len(hist) >= 1
    assert hist[0]["target_entity_id"] == parcel_id
    assert hist[0]["quality_grade"] == QualityGrade.HIGH_CONFIDENCE.value

    # 8. Test Individual Building & Unit Validation APIs
    b_val = client.post(f"/api/v1/validation/building/{building_id}")
    assert b_val.status_code == 200
    assert b_val.json()["data"]["is_valid"] is True

    u_val = client.post(f"/api/v1/validation/unit/{unit_id}")
    assert u_val.status_code == 200
    assert u_val.json()["data"]["is_valid"] is True


def test_deterministic_repeated_validation(client: TestClient, sample_parcel_geojson):
    """Verifies that running validation repeatedly produces identical deterministic results."""
    p_resp = client.post("/api/v1/parcels/", json={
        "state_code": "MH",
        "district_code": "PUN",
        "village_code": "VIL02",
        "survey_number": "SRV-REP-01",
        "geometry_geojson": sample_parcel_geojson,
        "base_elevation_m": 50.0,
        "spatial_metadata": {"crs": "EPSG:4326"}
    })
    parcel_id = p_resp.json()["data"]["id"]

    val1 = client.post(f"/api/v1/validation/parcel/{parcel_id}?persist=false").json()["data"]
    val2 = client.post(f"/api/v1/validation/parcel/{parcel_id}?persist=false").json()["data"]

    assert val1["is_valid"] == val2["is_valid"]
    assert val1["quality_score"]["total_score"] == val2["quality_score"]["total_score"]
    assert val1["total_rules_executed"] == val2["total_rules_executed"]
    assert len(val1["issues"]) == len(val2["issues"])
