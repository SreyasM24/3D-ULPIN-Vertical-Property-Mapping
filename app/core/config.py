from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application
    APP_NAME: str = "3D ULPIN & Vertical Property Mapping System"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    VERSION: str = "0.1.0"
    
    # 3D ULPIN Prototype metadata
    ULPIN_SPEC_STATUS: str = "PROTOTYPE"  # Prototype schema aligned with SIH 26011 problem statement
    
    # Host & Port
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database: SQLite default for local zero-config execution; PostGIS/PostgreSQL compatible
    DATABASE_URL: str = "sqlite:///./cadastre_3d.db"
    DB_ECHO: bool = False

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "https://3d-ulpin-git-main-sreyas-projects2.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_JSON_FORMAT: bool = False

    # ML & 3D Feature Estimation Defaults
    DEFAULT_FLOOR_HEIGHT_M: float = 3.0
    DEFAULT_BASEMENT_HEIGHT_M: float = 3.5
    DEFAULT_GROUND_FLOOR_HEIGHT_M: float = 3.8
    MAX_REASONABLE_BUILDING_HEIGHT_M: float = 350.0
    MIN_REASONABLE_FLOOR_HEIGHT_M: float = 2.2
    POINT_CLOUD_DECIMATION_SAMPLE: int = 10000


settings = Settings()
