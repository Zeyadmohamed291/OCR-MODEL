from fastapi import APIRouter
from app.domain.schemas.responses import HealthResponse
from app.core.config import settings
import app.api.dependencies.ocr as ocr_dep

router = APIRouter(tags=["Health"])

@router.get("/health", response_model=HealthResponse)
async def health_check():
    engine_ready = ocr_dep.is_ocr_engine_initialized()
    
    return HealthResponse(
        status="ok",
        engine_ready=engine_ready,
        version=settings.PROJECT_VERSION
    )
