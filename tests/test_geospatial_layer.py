import pytest
from shapely.geometry import Polygon, MultiPolygon
from app.core.crs import (
    WGS84_CRS,
    validate_wgs84_coordinates,
    get_utm_epsg_for_point,
    project_geometry,
    unproject_geometry,
)
from app.core.exceptions import InvalidGeometryException
from app.services.geometry_normalization import GeometryNormalizationService
from app.services.spatial_engine import (
    compute_projected_spatial_metrics,
    evaluate_building_containment,
    compute_volumetric_bounds,
)
from app.services.geojson_serializer import CadastralGeoJSONSerializer
from app.models.parcel import LandParcel
from app.models.building import Building
from app.models.unit import VerticalUnit


# ---------------------------------------------------------------------------
# 1. CRS & Transformation Tests
# ---------------------------------------------------------------------------

def test_wgs84_coordinate_validation():
    # Valid
    validate_wgs84_coordinates(73.856, 18.520)
    validate_wgs84_coordinates(-180.0, -90.0)
    validate_wgs84_coordinates(180.0, 90.0)

    # Invalid longitude
    with pytest.raises(InvalidGeometryException, match="Longitude"):
        validate_wgs84_coordinates(181.0, 18.52)

    # Invalid latitude
    with pytest.raises(InvalidGeometryException, match="Latitude"):
        validate_wgs84_coordinates(73.856, 91.0)


def test_dynamic_utm_zone_selection():
    # Pune, India: 73.856 E, 18.52 N -> UTM Zone 43N (EPSG:32643)
    epsg = get_utm_epsg_for_point(18.520, 73.856)
    assert epsg == "EPSG:32643"

    # London, UK: 0.12 W, 51.5 N -> UTM Zone 30N (EPSG:32630)
    epsg_uk = get_utm_epsg_for_point(51.5, -0.12)
    assert epsg_uk == "EPSG:32630"

    # Sydney, Australia: 151.2 E, -33.8 S -> UTM Zone 56S (EPSG:32756)
    epsg_syd = get_utm_epsg_for_point(-33.8, 151.2)
    assert epsg_syd == "EPSG:32756"


def test_geometry_projection_and_unprojection():
    # 100m x 100m square in Pune
    poly_wgs84 = Polygon([
        (73.8560, 18.5200),
        (73.8570, 18.5200),
        (73.8570, 18.5210),
        (73.8560, 18.5210),
        (73.8560, 18.5200),
    ])
    projected, epsg = project_geometry(poly_wgs84)
    assert epsg == "EPSG:32643"
    assert projected.area > 0

    # Unproject back to WGS84
    roundtrip = unproject_geometry(projected, src_crs=epsg, dst_crs=WGS84_CRS)
    assert abs(roundtrip.centroid.x - poly_wgs84.centroid.x) < 1e-6
    assert abs(roundtrip.centroid.y - poly_wgs84.centroid.y) < 1e-6


# ---------------------------------------------------------------------------
# 2. Geometry Normalization & Repair Tests
# ---------------------------------------------------------------------------

def test_ring_closure_auto_repair():
    unclosed_ring = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8560, 18.5200],
                [73.8570, 18.5200],
                [73.8570, 18.5210],
                [73.8560, 18.5210],
                # Missing closing [73.8560, 18.5200]
            ]
        ]
    }
    res = GeometryNormalizationService.normalize_geojson(unclosed_ring)
    assert res.is_valid is True
    assert res.was_repaired is True
    assert "RING_CLOSED" in res.repair_actions
    assert res.geometry.exterior.is_closed is True
    assert res.geometry.exterior.coords[0][:2] == res.geometry.exterior.coords[-1][:2]


def test_duplicate_vertex_deduplication():
    duplicate_vertices = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8560, 18.5200],
                [73.8560, 18.5200],  # Consecutive duplicate
                [73.8570, 18.5200],
                [73.8570, 18.5210],
                [73.8570, 18.5210],  # Consecutive duplicate
                [73.8560, 18.5210],
                [73.8560, 18.5200],
            ]
        ]
    }
    res = GeometryNormalizationService.normalize_geojson(duplicate_vertices)
    assert res.is_valid is True
    assert res.was_repaired is True
    assert "DUPLICATE_VERTICES_REMOVED" in res.repair_actions
    # Deduplicated coordinates: 4 vertices + 1 closed = 5 coords
    assert len(res.geometry.exterior.coords) == 5


def test_multipolygon_normalization():
    # MultiPolygon with 2 disjoint polygons
    mp = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[73.856, 18.520], [73.857, 18.520], [73.857, 18.521], [73.856, 18.521], [73.856, 18.520]]],
            [[[73.858, 18.520], [73.859, 18.520], [73.859, 18.521], [73.858, 18.521], [73.858, 18.520]]],
        ]
    }
    res = GeometryNormalizationService.normalize_geojson(mp, allow_multipolygon=True)
    assert res.is_valid is True
    assert isinstance(res.geometry, MultiPolygon)
    assert len(res.geometry.geoms) == 2


def test_self_intersecting_bowtie_polygon():
    # Bowtie / figure-8 polygon (self-intersection)
    bowtie = {
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
    res = GeometryNormalizationService.normalize_geojson(bowtie)
    assert res.is_valid is True
    assert res.was_repaired is True
    assert any("MAKE_VALID_APPLIED" in act for act in res.repair_actions)


# ---------------------------------------------------------------------------
# 3. Spatial Calculations & Building Containment Tests
# ---------------------------------------------------------------------------

def test_projected_spatial_metrics(sample_parcel_geojson):
    metrics = compute_projected_spatial_metrics(sample_parcel_geojson)
    assert metrics["area_sqm"] > 0
    assert metrics["perimeter_m"] > 0
    assert metrics["projected_crs"] == "EPSG:32643"
    assert len(metrics["bbox"]) == 4
    # Area of ~0.001 deg x 0.001 deg in Pune is ~11,000 to 12,000 m²
    assert 10000.0 < metrics["area_sqm"] < 13000.0


def test_building_containment_states(sample_parcel_geojson, sample_building_geojson):
    # 1. Strictly Contained
    res_contained = evaluate_building_containment(sample_building_geojson, sample_parcel_geojson)
    assert res_contained["status"] == "CONTAINED"
    assert res_contained["is_contained"] is True
    assert res_contained["excess_area_sqm"] == 0.0

    # 2. Partially Outside
    partial_outside_building = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8565, 18.5205],
                [73.8575, 18.5205],  # Extends past parcel's 73.8570 eastern boundary
                [73.8575, 18.5215],
                [73.8565, 18.5215],
                [73.8565, 18.5205]
            ]
        ]
    }
    res_partial = evaluate_building_containment(partial_outside_building, sample_parcel_geojson)
    assert res_partial["status"] == "PARTIALLY_OUTSIDE"
    assert res_partial["is_contained"] is False
    assert res_partial["excess_area_sqm"] > 0
    assert res_partial["excess_percentage"] > 0

    # 3. Completely Outside
    completely_outside_building = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8600, 18.5300],
                [73.8610, 18.5300],
                [73.8610, 18.5310],
                [73.8600, 18.5310],
                [73.8600, 18.5300]
            ]
        ]
    }
    res_outside = evaluate_building_containment(completely_outside_building, sample_parcel_geojson)
    assert res_outside["status"] == "COMPLETELY_OUTSIDE"
    assert res_outside["is_contained"] is False
    assert res_outside["excess_percentage"] == 100.0


# ---------------------------------------------------------------------------
# 4. 3D Volumetric Calculations & GeoJSON Serialization
# ---------------------------------------------------------------------------

def test_volumetric_bounds_and_prism(sample_unit_geojson):
    res = compute_volumetric_bounds(sample_unit_geojson, z_min=560.0, z_max=563.0)
    assert res["height_m"] == 3.0
    assert res["area_sqm"] > 0
    assert res["volume_cu_m"] == round(res["area_sqm"] * 3.0, 2)
    assert res["projected_crs"] == "EPSG:32643"
    assert res["prism"].representation_type == "EXTRUDED_PRISM_LOD1"


def test_geojson_serializer(sample_parcel_geojson):
    parcel = LandParcel(
        id="test-parcel-uuid",
        ulpin="14CH78901234AB",
        state_code="MH",
        district_code="PUN",
        village_code="411001",
        survey_number="123",
        subdivision_number="1",
        area_sqm=11520.5,
        centroid_lat=18.5205,
        centroid_lon=73.8565,
        base_elevation_m=560.0,
        geometry_geojson=sample_parcel_geojson,
        spatial_metadata={"source_crs": "EPSG:4326"},
        status="ACTIVE"
    )
    feature = CadastralGeoJSONSerializer.serialize_parcel(parcel)
    assert feature["type"] == "Feature"
    assert feature["id"] == "test-parcel-uuid"
    assert feature["properties"]["ulpin"] == "14CH78901234AB"
    assert feature["properties"]["area_sqm"] == 11520.5
