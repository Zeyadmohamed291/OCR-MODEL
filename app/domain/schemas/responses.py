from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from app.domain.schemas.core import (
    DocumentMeta, LayoutInfo, LayoutSection, LayoutTable, OCRMeta,
    ProcessingMeta, ImageQualityMetrics, StructuredField
)

class HealthResponse(BaseModel):
    status: str
    engine_ready: bool
    version: str
    
class VersionResponse(BaseModel):
    version: str

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None

class ErrorResponse(BaseModel):
    success: bool = False
    error: Any  # Union[ErrorDetail, str, Dict[str, Any]]
    details: Optional[Any] = None

class IDFields(BaseModel):
    national_id: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    governorate_code: Optional[str] = None

class OCRResponse(BaseModel):
    success: bool = True
    
    # Universal Document Intelligence format
    document: Optional[DocumentMeta] = None
    text: str
    raw_text: str = ""
    normalized_text: str = ""
    needs_review: bool = False
    uncertain_lines: List[int] = Field(default_factory=list)
    layout: Optional[LayoutInfo] = None
    fields: Optional[Dict[str, Any]] = None
    field_details: Optional[Dict[str, Dict[str, Any]]] = None
    structured_fields: List[StructuredField] = Field(default_factory=list)
    sections: List[LayoutSection] = Field(default_factory=list)
    tables: List[LayoutTable] = Field(default_factory=list)
    ocr: Optional[OCRMeta] = None
    quality: Optional[ImageQualityMetrics] = None
    processing: Optional[ProcessingMeta] = None
    
    # Backward compatibility attributes
    document_type: str = "unknown"
    formatted_text: Optional[str] = None
    confidence: float = 0.0
    processing_time_ms: float = 0.0
    image_width: int = 0
    image_height: int = 0


class DocumentPageResponse(BaseModel):
    page_number: int
    result: OCRResponse


class DocumentOCRResponse(BaseModel):
    success: bool = True
    page_count: int
    text: str
    raw_text: str
    normalized_text: str
    needs_review: bool
    pages: List[DocumentPageResponse] = Field(default_factory=list)
    processing_time_ms: float
