from typing import Any, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.logging import logger, correlation_id_ctx


class CadastreException(Exception):
    """Base exception for all Cadastre domain errors."""
    def __init__(self, message: str, code: str = "CADASTRE_ERROR", details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details


class EntityNotFoundException(CadastreException):
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(
            message=f"{entity_name} with id '{entity_id}' was not found.",
            code="ENTITY_NOT_FOUND",
            details={"entity": entity_name, "id": str(entity_id)}
        )


class DuplicateEntityException(CadastreException):
    def __init__(self, entity_name: str, field: str, value: Any):
        super().__init__(
            message=f"{entity_name} with {field} '{value}' already exists.",
            code="DUPLICATE_ENTITY",
            details={"entity": entity_name, "field": field, "value": str(value)}
        )


class SpatialClashException(CadastreException):
    """Raised when 3D spatial collision/overlap is detected between vertical units."""
    def __init__(self, message: str, clashes: Optional[Any] = None):
        super().__init__(
            message=message,
            code="SPATIAL_CLASH_DETECTED",
            details={"clashes": clashes or []}
        )


class SpatialContainmentException(CadastreException):
    """Raised when a unit footprint is not contained within its parent boundary."""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=message,
            code="SPATIAL_CONTAINMENT_VIOLATION",
            details=details
        )


class InvalidGeometryException(CadastreException):
    """Raised when coordinates or polygons are topologically invalid."""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=message,
            code="INVALID_GEOMETRY",
            details=details
        )


class ULPINGenerationError(CadastreException):
    """Raised when ULPIN generation or verification fails."""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=message,
            code="ULPIN_GENERATION_FAILED",
            details=details
        )



async def cadastre_exception_handler(request: Request, exc: CadastreException) -> JSONResponse:
    """Formats domain exceptions into standard error responses."""
    status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(exc, EntityNotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, DuplicateEntityException):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, (SpatialClashException, SpatialContainmentException)):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    req_id = correlation_id_ctx.get()
    logger.warning(f"Domain error [{exc.code}] (req:{req_id}): {exc.message}")
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id} if req_id else None
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Formats Pydantic request validation errors."""
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(x) for x in err.get("loc", []))
        errors.append({
            "field": loc,
            "message": err.get("msg", ""),
            "type": err.get("type", "")
        })
    req_id = correlation_id_ctx.get()
    logger.warning(f"Validation error on {request.url.path} (req:{req_id}): {errors}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request payload validation failed.",
                "details": errors,
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id} if req_id else None
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions. Never exposes tracebacks or internal internals."""
    req_id = correlation_id_ctx.get()
    logger.exception(f"Unhandled server error on {request.url.path} (req:{req_id}): {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred while processing the request.",
                "details": None,
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id} if req_id else None
    )
