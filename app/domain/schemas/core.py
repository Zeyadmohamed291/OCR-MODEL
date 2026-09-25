from pydantic import BaseModel, Field
from typing import List, Tuple, Any, Optional

class BoundingBox(BaseModel):
    points: List[Tuple[float, float]] = Field(..., min_length=4, max_length=4)
    normalized_points: List[Tuple[float, float]] = Field(..., min_length=4, max_length=4)
    width: float
    height: float
    area: float

class TextBlock(BaseModel):
    box: BoundingBox
    text: str
    # Immutable engine transcription; text may hold an explicitly normalized value.
    raw_text: str = ""
    normalized_text: str = ""
    confidence: float
    line_number: int = 0
    reading_order: int = 0
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    page: int = 1
    detection_order: int = 0
    script: str = "unknown"
    language: str = "unknown"
    direction: str = "ltr"
    line: int = 0
    block: int = 0

class OCRResult(BaseModel):
    blocks: List[TextBlock]
    total_time_ms: float
    average_confidence: float
    image_width: int
    image_height: int
    raw_output: Optional[Any] = None

class ImageMetadata(BaseModel):
    filename: str
    width: int
    height: int
    content_type: str
    size_bytes: int

class ImageQualityMetrics(BaseModel):
    width: int = 0
    height: int = 0
    channels: int = 3
    is_blurry: bool = False
    blur_score: float = 0.0
    brightness: float = 0.0
    contrast: float = 0.0
    resolution_ok: bool = True
    skew_angle: float = 0.0
    detected_orientation: int = 0
    variants_evaluated: List[str] = []
    warnings: List[str] = []

class LayoutLine(BaseModel):
    line_number: int
    text: str
    raw_text: Optional[str] = None
    normalized_text: Optional[str] = None
    language: str = "unknown"
    direction: str = "ltr"
    confidence: float = 0.0
    box: Optional[BoundingBox] = None
    bbox: Optional[List[List[float]]] = None
    reading_order: int = 0

class LayoutBlock(BaseModel):
    block_id: int
    type: str = "paragraph"
    text: str
    raw_text: Optional[str] = None
    normalized_text: Optional[str] = None
    language: str = "unknown"
    direction: str = "ltr"
    confidence: float = 0.0
    box: Optional[BoundingBox] = None
    bbox: Optional[List[List[float]]] = None
    reading_order: int = 0
    lines: List[LayoutLine] = []

class LayoutCell(BaseModel):
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    text: str
    raw_text: Optional[str] = None
    normalized_text: Optional[str] = None
    language: str = "unknown"
    direction: str = "ltr"
    confidence: float = 0.0
    box: Optional[BoundingBox] = None
    bbox: Optional[List[List[float]]] = None

class LayoutTable(BaseModel):
    table_id: int
    rows: int
    cols: int
    direction: str = "ltr"
    headers: List[str] = []
    cells: List[LayoutCell] = []
    raw_data: List[List[str]] = []
    structured_headers: List[LayoutCell] = []
    structured_rows: List[List[LayoutCell]] = []

class StructuredField(BaseModel):
    label: Optional[str] = None
    value: Any
    raw_value: Optional[str] = None
    source_bbox: Optional[List[List[float]]] = None
    language: str = "unknown"
    direction: str = "ltr"
    confidence: float = 1.0
    field_name: Optional[str] = None
    is_valid: bool = True
    validation_note: Optional[str] = None

class LayoutSection(BaseModel):
    title: str
    level: int = 1
    content: str = ""
    confidence: float = 0.9
    bbox: Optional[List[List[float]]] = None
    text: str = ""
    box: Optional[BoundingBox] = None

class LayoutInfo(BaseModel):
    pages: int = 1
    title: Optional[str] = None
    header: Optional[str] = None
    footer: Optional[str] = None
    columns: int = 1
    has_signatures: bool = False
    confidence: float = 0.0
    blocks: List[LayoutBlock] = []
    lines: List[LayoutLine] = []
    tables: List[LayoutTable] = []

class DocumentMeta(BaseModel):
    type: str
    language: str
    confidence: float = 0.0

class OCRMeta(BaseModel):
    confidence: float = 0.0
    engine: str = "easyocr"

class ProcessingMeta(BaseModel):
    processing_time_ms: float = 0.0
    image_loading_time_ms: float = 0.0
    preprocessing_time_ms: float = 0.0
    ocr_time_ms: float = 0.0
    layout_time_ms: float = 0.0
    classification_time_ms: float = 0.0
    extraction_time_ms: float = 0.0
