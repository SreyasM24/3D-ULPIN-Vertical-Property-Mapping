from fastapi.testclient import TestClient
from app.main import app


def test_root_endpoint(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["success"] is True
    assert "name" in json_data["data"]
    assert "version" in json_data["data"]


def test_health_check_endpoint(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["success"] is True
    assert json_data["data"]["status"] == "healthy"
    assert json_data["data"]["database_connected"] is True


def test_openapi_schema_generation():
    schema = app.openapi()
    assert schema is not None
    assert "openapi" in schema
    assert schema["info"]["title"] == "3D ULPIN & Vertical Property Mapping System"
    assert "/api/v1/parcels/" in schema["paths"]
    assert "/api/v1/buildings/" in schema["paths"]
    assert "/api/v1/units/" in schema["paths"]
    assert "/api/v1/spatial/clashes/building/{building_id}" in schema["paths"]


def test_root_health_and_readiness(client: TestClient):
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["data"]["status"] == "healthy"

    resp_ready = client.get("/readiness")
    assert resp_ready.status_code == 200
    assert resp_ready.json()["data"]["status"] == "ready"
    assert resp_ready.json()["data"]["database_connected"] is True


def test_readiness_and_capabilities_api_v1(client: TestClient):
    resp_ready = client.get("/api/v1/readiness")
    assert resp_ready.status_code == 200
    ready_data = resp_ready.json()
    assert ready_data["success"] is True
    assert ready_data["data"]["database_connected"] is True

    resp_caps = client.get("/api/v1/capabilities")
    assert resp_caps.status_code == 200
    caps_data = resp_caps.json()
    assert caps_data["success"] is True
    caps = caps_data["data"]["capabilities"]
    assert caps["cadastre_2d"]["supported"] is True
    assert caps["cadastre_3d"]["supported"] is True
    assert caps["validation_engine"]["supported"] is True
    assert caps["ml_feature_extraction"]["supported"] is True
    assert caps["ml_feature_extraction"]["is_authoritative"] is False
    assert caps["async_orchestration"]["supported"] is True
    assert caps["digital_twin"]["supported"] is True
