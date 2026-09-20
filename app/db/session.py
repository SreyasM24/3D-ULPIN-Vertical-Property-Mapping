from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.core.logging import logger
from app.db.base import Base

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    connect_args=connect_args,
    future=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a transactional database session."""
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Initializes database tables from Base metadata and ensures schema columns exist."""
    # Ensure all models are imported prior to create_all
    import app.models  # noqa: F401
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)

    # Lightweight idempotent column synchronization for local development/sqlite
    from sqlalchemy import text
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE vertical_units ADD COLUMN is_multi_floor BOOLEAN DEFAULT 0",
            "ALTER TABLE vertical_units ADD COLUMN floor_span JSON",
            "ALTER TABLE processing_jobs ADD COLUMN request_id VARCHAR(64)",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass

    logger.info("Database schema initialized successfully.")
