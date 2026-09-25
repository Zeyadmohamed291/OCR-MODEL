import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    InvalidImageError,
    UnsupportedFormatError,
    ValidationFailureError,
    ModelLoadingError,
    OCRFailureError,
    ConfigurationError,
    PayloadTooLargeError
)
from app.domain.schemas.responses import ErrorResponse, ErrorDetail

logger = logging.getLogger("ocr_microservice")

def build_error_response(code: str, message: str, status_code: int, details: str = None) -> JSONResponse:
    """
    Constructs a structured JSON error response that never leaks Python stack traces to API clients.
    """
    payload = {
        "success": False,
        "error": {
            "code": code,
            "message": message
        }
    }
    if details:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


def create_exception_handlers(app):
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        req_id = getattr(request.state, "request_id", "unknown")
        logger.warning(f"[{req_id}] Validation Error: {exc.errors()}")
        return build_error_response(
            code="VALIDATION_ERROR",
            message="Invalid request input parameters.",
            status_code=422
        )

    @app.exception_handler(InvalidImageError)
    @app.exception_handler(ValidationFailureError)
    async def bad_request_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", "unknown")
        logger.warning(f"[{req_id}] Bad Request: {str(exc)}")
        return build_error_response(
            code="INVALID_IMAGE",
            message=str(exc),
            status_code=400
        )

    @app.exception_handler(PayloadTooLargeError)
    async def payload_too_large_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", "unknown")
        logger.warning(f"[{req_id}] Payload Too Large: {str(exc)}")
        return build_error_response(
            code="PAYLOAD_TOO_LARGE",
            message=str(exc),
            status_code=413
        )

    @app.exception_handler(UnsupportedFormatError)
    async def unsupported_media_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", "unknown")
        logger.warning(f"[{req_id}] Unsupported Media Type: {str(exc)}")
        return build_error_response(
            code="UNSUPPORTED_MEDIA_TYPE",
            message=str(exc),
            status_code=415
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        req_id = getattr(request.state, "request_id", "unknown")
        logger.warning(f"[{req_id}] HTTP Exception: {exc.status_code} - {exc.detail}")
        
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            413: "PAYLOAD_TOO_LARGE",
            415: "UNSUPPORTED_MEDIA_TYPE",
            422: "VALIDATION_ERROR",
            429: "TOO_MANY_REQUESTS",
            500: "INTERNAL_SERVER_ERROR",
            503: "SERVICE_UNAVAILABLE"
        }
        code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        return build_error_response(
            code=code,
            message=str(exc.detail),
            status_code=exc.status_code
        )

    @app.exception_handler(ModelLoadingError)
    @app.exception_handler(ConfigurationError)
    @app.exception_handler(OCRFailureError)
    async def internal_server_error_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", "unknown")
        logger.error(f"[{req_id}] Service Failure: {str(exc)}", exc_info=True)
        return build_error_response(
            code="OCR_PROCESSING_ERROR",
            message="Unable to process the image due to an internal service failure.",
            status_code=500
        )

    @app.exception_handler(RuntimeError)
    async def ocr_runtime_error_handler(request: Request, exc: RuntimeError):
        req_id = getattr(request.state, "request_id", "unknown")
        logger.error(f"[{req_id}] OCR processing failure: {type(exc).__name__}", exc_info=True)
        return build_error_response(
            code="OCR_PROCESSING_ERROR",
            message="The OCR engine failed to process the input.",
            status_code=503
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", "unknown")
        logger.critical(f"[{req_id}] Unexpected Critical Error: {str(exc)}", exc_info=True)
        return build_error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred while processing the request.",
            status_code=500
        )
