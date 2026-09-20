import io
import zipfile
import shapefile
from fastapi.testclient import TestClient

from app.services.ingestion.geojson_adapter import GeoJSONIngestionAdapter
from app.services.ingestion.shapefile_adapter import ShapefileIngestionAdapter
from app.services.ingestion.metadata_adapters import (
    LiDARMetadataAdapter,
    DEMDSMMetadataAdapter,
    DroneImageryMetadataAdapter,
    FloorPlanMetadataAdapter,
)


def test_geojson_adapter_feature_collection(sample_parcel_geojson):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "parcel_1",
                "geometry": sample_parcel_geojson,
                "properties": {"survey_no": "101", "owner": "Govt of Maharashtra"}
            }
        ]
    }
    adapter = GeoJSONIngestionAdapter(source_name="Test Cadastre FC")
    result = adapter.ingest(fc)

    assert result.success is True
    assert result.provenance.feature_count == 1
    assert result.provenance.source_type == "GEOJSON"
    assert result.provenance.source_file_hash is not None
    feat = result.features[0]
    assert feat.source_id == "parcel_1"
    assert feat.area_sqm > 0
    assert feat.projected_crs == "EPSG:32643"


def test_geojson_adapter_auto_repair_ring():
    unclosed_geojson = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.856, 18.520],
                [73.857, 18.520],
                [73.857, 18.521],
                [73.856, 18.521]
                # unclosed
            ]
        ]
    }
    adapter = GeoJSONIngestionAdapter(source_name="Unclosed Polygon")
    result = adapter.ingest(unclosed_geojson)

    assert result.success is True
    assert result.features[0].was_repaired is True
    assert "RING_CLOSED" in result.features[0].repair_actions


def test_geojson_adapter_invalid_input():
    adapter = GeoJSONIngestionAdapter(source_name="Invalid Doc")
    result = adapter.ingest({"type": "Point", "coordinates": [73.85, 18.52]})
    assert result.success is False
    assert len(result.errors) > 0


def test_shapefile_adapter_in_memory_zip(sample_parcel_geojson):
    # Create an in-memory Shapefile using pyshp
    shp_buffer = io.BytesIO()
    shx_buffer = io.BytesIO()
    dbf_buffer = io.BytesIO()

    with shapefile.Writer(shp=shp_buffer, shx=shx_buffer, dbf=dbf_buffer) as w:
        w.field("SURVEY_NO", "C", size=50)
        w.field("AREA_CAT", "C", size=20)
        coords = sample_parcel_geojson["coordinates"][0]
        w.poly([coords])
        w.record(SURVEY_NO="204/A", AREA_CAT="URBAN")

    # Pack into a zip archive
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("cadastre.shp", shp_buffer.getvalue())
        z.writestr("cadastre.shx", shx_buffer.getvalue())
        z.writestr("cadastre.dbf", dbf_buffer.getvalue())

    zip_bytes = zip_buffer.getvalue()

    adapter = ShapefileIngestionAdapter(source_name="Zipped Shapefile Test")
    result = adapter.ingest(zip_bytes)

    assert result.success is True
    assert result.provenance.source_type == "SHAPEFILE"
    assert len(result.features) == 1
    feat = result.features[0]
    assert feat.attributes["SURVEY_NO"] == "204/A"
    assert feat.area_sqm > 0
    assert feat.projected_crs == "EPSG:32643"


def test_lidar_metadata_adapter():
    payload = {
        "file_name": "pune_urban_flight_01.laz",
        "las_version": "1.4",
        "point_count": 25000000,
        "horizontal_crs": "EPSG:32643",
        "vertical_datum": "EGM96",
        "bounds_bbox": [375000.0, 2048000.0, 540.0, 378000.0, 2051000.0, 680.0],
        "sensor_model": "Riegl VUX-1LR",
        "flight_date": "2026-03-01"
    }
    adapter = LiDARMetadataAdapter(source_name=payload["file_name"])
    res = adapter.ingest(payload)
    assert res.success is True
    assert res.provenance.processing_status == "METADATA_EXTRACTED"
    assert res.provenance.metadata_attributes["point_count"] == 25000000


def test_dem_metadata_adapter():
    payload = {
        "raster_name": "pune_dsm_025m.tif",
        "model_type": "DSM",
        "spatial_resolution_m": 0.25,
        "horizontal_crs": "EPSG:32643",
        "vertical_datum": "WGS84_ELLIPSOID",
        "elevation_min_m": 540.5,
        "elevation_max_m": 690.2,
        "bounds_bbox": [73.85, 18.51, 73.87, 18.53]
    }
    adapter = DEMDSMMetadataAdapter(source_name=payload["raster_name"])
    res = adapter.ingest(payload)
    assert res.success is True
    assert res.provenance.processing_status == "METADATA_EXTRACTED"


def test_drone_and_floorplan_metadata_adapters():
    # Drone
    drone_payload = {
        "mission_name": "Ward_4_Survey",
        "operator_organization": "Empanelled Drone Agency",
        "drone_model": "DJI Matrice 300 RTK",
        "camera_sensor": "Zenmuse P1",
        "flight_altitude_agl_m": 100.0,
        "ground_sampling_distance_cm": 2.0,
        "total_images": 520,
        "rtk_cors_used": True,
        "survey_date": "2026-03-10"
    }
    d_res = DroneImageryMetadataAdapter(source_name="Ward_4").ingest(drone_payload)
    assert d_res.success is True
    assert d_res.provenance.metadata_attributes["ground_sampling_distance_cm"] == 2.0

    # Floor Plan
    fp_payload = {
        "building_code": "TWR-B",
        "level_code": "L02",
        "drawing_number": "ARCH-TWRB-FL02",
        "source_format": "IFC",
        "scale": "1:100",
        "georeferenced": True,
        "datum_elevation_m": 566.0,
        "floor_height_m": 3.0
    }
    f_res = FloorPlanMetadataAdapter(source_name="TWR-B_L02").ingest(fp_payload)
    assert f_res.success is True
    assert f_res.provenance.metadata_attributes["floor_height_m"] == 3.0


# ---------------------------------------------------------------------------
# API Endpoints Integration Tests
# ---------------------------------------------------------------------------

def test_api_normalize_geometry(client: TestClient):
    unclosed_ring = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.856, 18.520],
                [73.857, 18.520],
                [73.857, 18.521],
                [73.856, 18.521]
            ]
        ]
    }
    res = client.post("/api/v1/spatial/normalize-geometry", json={
        "geometry": unclosed_ring,
        "snap_decimals": 7
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["is_valid"] is True
    assert data["was_repaired"] is True
    assert "RING_CLOSED" in data["repair_actions"]
    assert data["metrics"]["area_sqm"] > 0
    assert data["metrics"]["projected_crs"] == "EPSG:32643"


def test_api_validate_building_containment(
    client: TestClient,
    sample_parcel_geojson,
    sample_building_geojson
):
    res = client.post("/api/v1/spatial/validate-building-containment", json={
        "building_geometry": sample_building_geojson,
        "parcel_geometry": sample_parcel_geojson,
        "tolerance_sqm": 0.05
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "CONTAINED"
    assert data["is_contained"] is True
    assert data["excess_area_sqm"] == 0.0


def test_api_ingest_geojson(client: TestClient, sample_parcel_geojson):
    payload = {
        "source_name": "Test Municipal Parcels",
        "source_crs": "EPSG:4326",
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": sample_parcel_geojson,
                    "properties": {"survey_no": "99"}
                }
            ]
        }
    }
    res = client.post("/api/v1/ingestion/geojson", json=payload)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["success"] is True
    assert data["provenance"]["feature_count"] == 1
    assert data["features"][0]["area_sqm"] > 0
