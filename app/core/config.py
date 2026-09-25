from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "OCR Microservice"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = "Offline Arabic/English OCR Microservice"
    
    # OCR Parameters
    MODEL_DIR: str = "models/easyocr"
    CONFIDENCE_THRESHOLD: float = 0.5
    OCR_RETRY_CONFIDENCE: float = Field(default=0.60, ge=0.0, le=1.0)
    OCR_ORIENTATION_CONFIDENCE: float = Field(default=0.30, ge=0.0, le=1.0)
    OCR_CANVAS_SIZE: int = Field(default=3200, ge=640, le=4096)
    OCR_WIDTH_THRESHOLD: float = Field(default=0.5, ge=0.0, le=1.0)
    DOCUMENT_MAX_PAGES: int = Field(default=20, ge=1, le=100)
    DOCUMENT_DPI: int = Field(default=200, ge=72, le=300)
    
    # Upload Parameters
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_IMAGE_TYPES: List[str] = ["image/jpeg", "image/jpg", "image/png", "image/webp", "image/tiff", "image/bmp"]
    
    # Logging
    LOGGING_LEVEL: str = "INFO"
    
    model_config = SettingsConfigDict(
        # .env file is optional — gracefully ignored if not present (e.g. on HF Spaces)
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # ignore unexpected env vars (e.g. HF injected vars)
    )

settings = Settings()
