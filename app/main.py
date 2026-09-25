from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.core.config import settings
from app.core.logging import setup_logging, LoggingMiddleware
from app.core.exception_handlers import create_exception_handlers
from app.api.v1.routers import health, root, ocr, viewer
from app.api.dependencies.ocr import get_ocr_engine

# Ensure required directories exist
os.makedirs("logs", exist_ok=True)
os.makedirs(settings.MODEL_DIR, exist_ok=True)

# Initialize structured logging
logger = setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    logger.info(f"Checking model directory configuration: {settings.MODEL_DIR}")
    
    # On Hugging Face Spaces, skip pre-loading to avoid startup timeout.
    # Models will be loaded lazily on the first OCR request instead.
    # On local/Docker, pre-load to avoid first-request latency.
    is_hf_space = os.environ.get("SPACE_ID") is not None
    if not is_hf_space:
        try:
            logger.info("Triggering initial load of OCR Engine models...")
            get_ocr_engine()
            logger.info("OCR Engine initialized successfully on startup.")
        except Exception as e:
            logger.error(f"Failed to initialize OCR Engine during startup: {e}")
            # Server stays up to serve /health, but OCR will fail gracefully with 500
    else:
        logger.info("Running on Hugging Face Spaces — OCR engine will load on first request (lazy init).")
        
    yield
    logger.info("Application shutting down...")



# FastAPI Application Definition with comprehensive Swagger Metadata
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION + "\\n\\nThis API provides offline, CPU-bound Optical Character Recognition for Arabic and English.",
    version=settings.PROJECT_VERSION,
    lifespan=lifespan,
    contact={
        "name": "OCR API Support",
    },
    responses={
        400: {"description": "Bad Request"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not Found"},
        413: {"description": "Payload Too Large"},
        415: {"description": "Unsupported Media Type"},
        422: {"description": "Validation Error"},
        429: {"description": "Too Many Requests"},
        500: {"description": "Internal Server Error"},
        503: {"description": "Service Unavailable"}
    }
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Custom Logging and Timing Middleware
app.add_middleware(LoggingMiddleware)

# Setup Global Exception Handlers
create_exception_handlers(app)

# Include API Routers
app.include_router(root.router)
app.include_router(health.router)
app.include_router(ocr.router, prefix="/ocr")
app.include_router(viewer.router)
