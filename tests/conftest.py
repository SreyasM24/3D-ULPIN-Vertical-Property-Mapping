import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

# In-memory SQLite for high-speed, isolated test execution
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
    expire_on_commit=False,
)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provides a clean in-memory database session per test."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden get_db dependency."""
    from app.jobs.executor import JobExecutor

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    JobExecutor.session_factory = TestingSessionLocal
    with TestClient(app) as c:
        yield c
    JobExecutor.session_factory = None
    app.dependency_overrides.clear()


@pytest.fixture
def sample_parcel_geojson():
    """Valid closed polygon: ~100m x 100m plot in Pune, MH."""
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8560, 18.5200],
                [73.8570, 18.5200],
                [73.8570, 18.5210],
                [73.8560, 18.5210],
                [73.8560, 18.5200]
            ]
        ]
    }


@pytest.fixture
def sample_building_geojson():
    """Footprint strictly inside sample_parcel_geojson."""
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8562, 18.5202],
                [73.8568, 18.5202],
                [73.8568, 18.5208],
                [73.8562, 18.5208],
                [73.8562, 18.5202]
            ]
        ]
    }


@pytest.fixture
def sample_unit_geojson():
    """Footprint strictly inside sample_building_geojson."""
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8563, 18.5203],
                [73.8565, 18.5203],
                [73.8565, 18.5205],
                [73.8563, 18.5205],
                [73.8563, 18.5203]
            ]
        ]
    }
