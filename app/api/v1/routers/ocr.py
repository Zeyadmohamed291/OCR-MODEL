import time
from fastapi import APIRouter, File, UploadFile, Depends, Request
from starlette.concurrency import run_in_threadpool
from app.domain.schemas.responses import OCRResponse, ErrorResponse, DocumentOCRResponse
from app.domain.interfaces.ocr_engine import AbstractOCREngine
from app.api.dependencies.ocr import get_ocr_engine
from app.services.image_processing.loader import load_image
from app.services.ocr.pipeline import extract_image

router = APIRouter(tags=["OCR Extraction"], responses={
    400: {"model": ErrorResponse}, 413: {"model": ErrorResponse},
    415: {"model": ErrorResponse}, 500: {"model": ErrorResponse},
})


@router.post("/extract", response_model=OCRResponse, summary="Extract text and structured fields from an image")
async def extract_text(request: Request, file: UploadFile = File(...),
                       ocr_engine: AbstractOCREngine = Depends(get_ocr_engine)):
    start = time.time()
    image, metadata = await load_image(file)
    load_ms = (time.time() - start) * 1000
    return await run_in_threadpool(extract_image, image, metadata, ocr_engine,
                                  getattr(request.state, "request_id", "unknown"), load_ms, start)


@router.post("/document", response_model=DocumentOCRResponse,
             summary="Extract all PDF/TIFF/image pages with local EasyOCR")
async def extract_document(request: Request, file: UploadFile = File(...),
                           ocr_engine: AbstractOCREngine = Depends(get_ocr_engine)):
    from app.services.image_processing.loader import read_upload, validate_content
    from app.services.ocr.pipeline import extract_document_pages
    contents = await read_upload(file)
    mime = validate_content(contents, file.content_type, allow_pdf=True)
    return await run_in_threadpool(extract_document_pages, contents, mime,
                                  file.filename or "unknown", ocr_engine,
                                  getattr(request.state, "request_id", "unknown"))
