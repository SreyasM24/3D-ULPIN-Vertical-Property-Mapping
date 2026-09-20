import pytest
from app.services.spatial_engine import (
    geojson_to_shapely,
    compute_centroid,
    compute_geodesic_area_sqm,
    compute_volumetric_bounds,
    check_containment,
    detect_3d_clashes,
)
from app.core.exceptions import InvalidGeometryException


def test_compute_area_and_centroid(sample_parcel_geojson):
    poly = geojson_to_shapely(sample_parcel_geojson)
    lat, lon = compute_centroid(poly)
    assert 18.5200 <= lat <= 18.5210
    assert 73.8560 <= lon <= 73.8570

    area = compute_geodesic_area_sqm(poly)
    assert area > 0


def test_compute_volumetric_bounds(sample_unit_geojson):
    z_min = 10.0
    z_max = 13.0
    res = compute_volumetric_bounds(sample_unit_geojson, z_min, z_max)
    assert res["height_m"] == 3.0
    assert res["area_sqm"] > 0
    assert res["volume_cu_m"] == round(res["area_sqm"] * 3.0, 2)


def test_check_containment(sample_parcel_geojson, sample_building_geojson):
    # Building is inside Parcel
    is_contained, excess = check_containment(sample_building_geojson, sample_parcel_geojson)
    assert is_contained is True
    assert excess == 0.0

    # Parcel is NOT inside building
    is_contained_rev, excess_rev = check_containment(sample_parcel_geojson, sample_building_geojson)
    assert is_contained_rev is False
    assert excess_rev > 0


def test_detect_3d_clashes_overlapping_units(sample_unit_geojson):
    unit1 = {
        "id": "u1",
        "ulpin_3d": "TEST-L01-U101-AA",
        "unit_number": "101",
        "footprint_geojson": sample_unit_geojson,
        "z_min": 10.0,
        "z_max": 13.0
    }
    # Unit 2 overlaps spatially and vertically
    unit2 = {
        "id": "u2",
        "ulpin_3d": "TEST-L01-U102-BB",
        "unit_number": "102",
        "footprint_geojson": sample_unit_geojson,
        "z_min": 11.5,
        "z_max": 14.5
    }

    clashes = detect_3d_clashes([unit1, unit2])
    assert len(clashes) == 1
    clash = clashes[0]
    assert clash["vertical_overlap_m"] == 1.5
    assert clash["overlap_volume_cu_m"] > 0
    assert clash["severity"] == "ERROR"


def test_detect_3d_clashes_vertically_separated_units(sample_unit_geojson):
    # Same 2D footprint, but Floor 1 vs Floor 2 (no vertical clash)
    floor1_unit = {
        "id": "u1",
        "ulpin_3d": "TEST-L01-U101-AA",
        "unit_number": "101",
        "footprint_geojson": sample_unit_geojson,
        "z_min": 10.0,
        "z_max": 13.0
    }
    floor2_unit = {
        "id": "u2",
        "ulpin_3d": "TEST-L02-U201-CC",
        "unit_number": "201",
        "footprint_geojson": sample_unit_geojson,
        "z_min": 13.0,
        "z_max": 16.0
    }

    clashes = detect_3d_clashes([floor1_unit, floor2_unit])
    assert len(clashes) == 0


def test_invalid_polygon_rejection():
    # Unclosed polygon ring
    unclosed = {
        "type": "Polygon",
        "coordinates": [
            [[73.0, 18.0], [73.1, 18.0], [73.1, 18.1]]
        ]
    }
    with pytest.raises(InvalidGeometryException):
        geojson_to_shapely(unclosed)
