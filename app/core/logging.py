import logging
import sys
from contextvars import ContextVar
from typing import Optional
from app.core.config import settings

# Context variable for request / correlation ID
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Injects the current correlation/request ID into every log record."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = correlation_id_ctx.get() or "system"
        return True


def setup_logging() -> logging.Logger:
    """Configures application-wide logging with request ID injection."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicate log outputs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationIdFilter())

    if settings.LOG_JSON_FORMAT:
        log_format = (
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"request_id": "%(request_id)s", "logger": "%(name)s", "message": "%(message)s"}'
        )
    else:
        log_format = (
            "[%(asctime)s] [%(levelname)s] [req:%(request_id)s] %(name)s: %(message)s"
        )

    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Silence excessively verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DB_ECHO else logging.WARNING
    )

    logger = logging.getLogger("sihps2")
    return logger


logger = setup_logging()
