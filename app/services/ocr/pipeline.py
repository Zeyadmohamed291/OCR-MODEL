"""Synchronous image pipeline shared by all local EasyOCR entry points."""
import time
import logging
from app.core.config import settings
from app.domain.schemas.responses import OCRResponse
from app.domain.schemas.core import DocumentMeta, OCRMeta, ProcessingMeta
from app.services.image_processing.quality import analyze_image_quality
from app.services.layout.reading_order import organize_reading_order
from app.services.layout.layout_analyzer import LayoutAnalyzer
from app.services.language.language_detector import LanguageDetector
from app.services.classification.classifier import UniversalDocumentClassifier
from app.services.extraction.registry import extractor_registry

logger = logging.getLogger("ocr_microservice")


def extract_image(image, metadata, ocr_engine, req_id="local", image_loading_ms=0.0, start_time=None):
    start_time = time.time() if start_time is None else start_time
    # 3. Image Quality Analysis & Adaptive Preprocessing
    t_prep_start = time.time()
    quality_metrics = analyze_image_quality(image)
    from app.services.image_processing.preprocessor import AdaptivePreprocessor
    processed_image, variants = AdaptivePreprocessor.preprocess_adaptive(image, quality_metrics)
    preprocessing_ms = (time.time() - t_prep_start) * 1000.0
    
    # Shared bounded OCR retries and orientation recovery.
    from app.services.ocr.passes import run_ocr_passes
    t_ocr_start = time.time()
    result, selected_transform, variants_evaluated = run_ocr_passes(
        ocr_engine, processed_image, variants, quality_metrics
    )

    # Convert detections from the OCR image coordinate space to original upload
    # pixel coordinates. This is exact for resize-only transforms; geometric
    # warps remain explicitly flagged in quality metadata for consumers.
    if selected_transform and selected_transform.get("width") and selected_transform.get("height"):
        sx = selected_transform["source_width"] / selected_transform["width"]
        sy = selected_transform["source_height"] / selected_transform["height"]
        geometric_frame = bool(selected_transform.get("geometry_corrected"))
        for block in result.blocks:
            # Scaling-only transforms map exactly to original pixels. A
            # perspective/deskew transform has no inverse here, so do not
            # fabricate source-space coordinates; retain OCR-frame points.
            points = list(block.box.points) if geometric_frame else [(x * sx, y * sy) for x, y in block.box.points]
            block.box.points = points
            if not geometric_frame:
                block.box.width *= sx
                block.box.height *= sy
            block.box.area = block.box.width * block.box.height
            if not geometric_frame:
                block.box.normalized_points = [(x / max(image.shape[1], 1), y / max(image.shape[0], 1)) for x, y in points]
                block.x *= sx
                block.y *= sy
                block.width *= sx
                block.height *= sy
        if not geometric_frame:
            result.image_width = image.shape[1]
            result.image_height = image.shape[0]
        else:
            quality_metrics.warnings.append("OCR boxes are in the geometry-corrected image coordinate frame.")
            
    quality_metrics.variants_evaluated = variants_evaluated
    ocr_duration = (time.time() - t_ocr_start) * 1000.0
    
    # 5. Reading Order & Layout Analysis
    t_layout_start = time.time()
    ordered_blocks = organize_reading_order(result.blocks, image_width=result.image_width)
    result.blocks = ordered_blocks
    
    # `text` remains the engine transcription. Preserve it byte-for-byte here;
    # downstream extractors may normalize candidate fields without rewriting OCR.
    
    layout_info, sections, tables = LayoutAnalyzer.analyze(
        ordered_blocks,
        image_width=result.image_width,
        image_height=result.image_height
    )
    combined_text = "\n".join(line.text for line in layout_info.lines) if layout_info.lines else ""
    layout_ms = (time.time() - t_layout_start) * 1000.0
    
    # 6. Language Detection & Classification
    t_class_start = time.time()
    language, lang_conf, lang_dist = LanguageDetector.detect(combined_text)
    doc_type, doc_conf = UniversalDocumentClassifier.classify(
        text=combined_text,
        layout=layout_info,
        metadata=metadata
    )
    classification_ms = (time.time() - t_class_start) * 1000.0
    
    # 7. Generic & Specialized Document Extraction
    t_ext_start = time.time()
    extracted_fields = extractor_registry.extract(
        document_type=doc_type,
        text=combined_text,
        layout=layout_info,
        metadata=metadata.model_dump() if metadata else None
    )
    
    from app.services.layout.bidi_formatter import convert_dict_to_structured_fields
    structured_fields = convert_dict_to_structured_fields(
        extracted_fields,
        confidence=round(result.average_confidence, 2),
        layout=layout_info
    )
    clean_fields = {k: v for k, v in extracted_fields.items() if not k.startswith("_")}
    extraction_ms = (time.time() - t_ext_start) * 1000.0
    
    total_duration = (time.time() - start_time) * 1000.0
    
    # 8. Extract original markdown if available
    formatted_text = None
    if result.raw_output and hasattr(result.raw_output, "pages"):
        page_mds = []
        for page in result.raw_output.pages:
            raw_md = getattr(page, 'markdown', '') or ''
            if raw_md:
                page_mds.append(raw_md)
        if page_mds:
            formatted_text = "\n\n".join(page_mds)
            
    # 9. Build Universal Document Intelligence Response
    response = OCRResponse(
        success=True,
        document=DocumentMeta(
            type=doc_type,
            language=language,
            confidence=doc_conf
        ),
        text=combined_text,
        raw_text="\n".join(line.raw_text or line.text for line in layout_info.lines),
        normalized_text="\n".join(line.normalized_text or line.text for line in layout_info.lines),
        needs_review=not result.blocks or any(b.confidence < settings.CONFIDENCE_THRESHOLD for b in result.blocks),
        uncertain_lines=[line.line_number for line in layout_info.lines if line.confidence < settings.CONFIDENCE_THRESHOLD],
        layout=layout_info,
        fields=clean_fields if clean_fields else None,
        structured_fields=structured_fields,
        sections=sections,
        tables=tables,
        ocr=OCRMeta(
            confidence=round(result.average_confidence, 3),
        engine="easyocr"
        ),
        quality=quality_metrics,
        processing=ProcessingMeta(
            processing_time_ms=round(total_duration, 2),
            image_loading_time_ms=round(image_loading_ms, 2),
            preprocessing_time_ms=round(preprocessing_ms, 2),
            ocr_time_ms=round(ocr_duration, 2),
            layout_time_ms=round(layout_ms, 2),
            classification_time_ms=round(classification_ms, 2),
            extraction_time_ms=round(extraction_ms, 2)
        ),
        document_type=doc_type,
        formatted_text=formatted_text,
        confidence=round(result.average_confidence, 3),
        processing_time_ms=round(total_duration, 2),
        image_width=result.image_width,
        image_height=result.image_height
    )
    
    logger.info(
        f"[{req_id}] Type: {doc_type} (conf: {doc_conf:.2f}, lang: {language}). "
        f"Timings: load={image_loading_ms:.1f}ms, prep={preprocessing_ms:.1f}ms, "
        f"ocr={ocr_duration:.1f}ms, layout={layout_ms:.1f}ms, class={classification_ms:.1f}ms, ext={extraction_ms:.1f}ms. "
        f"Total: {total_duration:.1f}ms. Fields: {len(clean_fields)}"
    )
    return response


def extract_document_pages(contents, mime, filename, engine, req_id="local"):
    from contextlib import closing
    from app.services.image_processing.documents import document_pages
    from app.domain.schemas.core import ImageMetadata
    from app.domain.schemas.responses import DocumentOCRResponse, DocumentPageResponse
    start = time.time()
    pages = []
    # Closing the generator also closes PDF/TIFF resources if OCR raises midway.
    with closing(document_pages(contents, mime)) as images:
        for index, image in enumerate(images, start=1):
            metadata = ImageMetadata(filename=filename, content_type=mime, size_bytes=len(contents),
                                     width=image.shape[1], height=image.shape[0])
            result = extract_image(image, metadata, engine, req_id=f"{req_id}/page-{index}")
            pages.append(DocumentPageResponse(page_number=index, result=result))
    return DocumentOCRResponse(
        page_count=len(pages), pages=pages,
        text="\n\f\n".join(p.result.text for p in pages),
        raw_text="\n\f\n".join(p.result.raw_text for p in pages),
        normalized_text="\n\f\n".join(p.result.normalized_text for p in pages),
        needs_review=any(p.result.needs_review for p in pages),
        processing_time_ms=round((time.time() - start) * 1000, 2),
    )
