# Graph Report - OCR-MODEL-main  (2026-09-25)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 536 nodes · 1478 edges · 32 communities (11 shown, 21 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 142 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- test_modular_extractors.py
- TextBlock
- routers/ocr.py
- BoundingBox
- test_universal_system.py
- app.py
- IDCardExtractor
- .extract
- vercel.json
- LoggingMiddleware
- pydantic
- .extract

## God Nodes (most connected - your core abstractions)
1. `UniversalDocumentClassifier` - 49 edges
2. `TextBlock` - 39 edges
3. `BaseExtractor` - 35 edges
4. `organize_reading_order()` - 29 edges
5. `extract_text()` - 28 edges
6. `LayoutAnalyzer` - 26 edges
7. `BoundingBox` - 25 edges
8. `ExtractorRegistry` - 22 edges
9. `AdaptivePreprocessor` - 19 edges
10. `analyze_image_quality()` - 19 edges

## Surprising Connections (you probably didn't know these)
- `run_gradio_ocr()` --uses--> `LayoutAnalyzer`  [INFERRED]
  app.py → app/services/layout/layout_analyzer.py
- `run_gradio_ocr()` --uses--> `ArabicOCRCorrector`  [INFERRED]
  app.py → app/services/text_processing/arabic_corrector.py
- `run_gradio_ocr()` --uses--> `UniversalDocumentClassifier`  [INFERRED]
  app.py → app/services/classification/classifier.py
- `test_unknown_document_preserves_full_utility()` --uses--> `UniversalDocumentClassifier`  [INFERRED]
  tests/test_document_understanding.py → app/services/classification/classifier.py
- `test_ocr_engine_is_completely_decoupled_from_extractors()` --uses--> `BaseExtractor`  [INFERRED]
  tests/test_modular_extractors.py → app/services/extraction/base.py

## Import Cycles
- None detected.

## Communities (32 total, 21 thin omitted)

### Community 0 - "test_modular_extractors.py"
Cohesion: 0.05
Nodes (77): BankDocumentExtractor, Any, Extractor for Bank Statements, Deposit Slips, and Financial Records., BaseExtractor, ABC, Abstract base class for all document-specific extractors. Each extractor…, ContractExtractor, Any (+69 more)

### Community 1 - "TextBlock"
Cohesion: 0.06
Nodes (76): ImageMetadata, LayoutBlock, LayoutCell, LayoutInfo, LayoutLine, LayoutSection, LayoutTable, BaseModel (+68 more)

### Community 2 - "routers/ocr.py"
Cohesion: 0.05
Nodes (68): health_check(), get, extract_text(), Request, UploadFile, info_endpoint(), get, root_endpoint() (+60 more)

### Community 3 - "BoundingBox"
Cohesion: 0.06
Nodes (50): get_ocr_engine(), get_ocr_engine_by_name(), Returns an OCR Engine instance by provider name ('easy' or 'mistral'). Falls…, Default dependency injection entrypoint for FastAPI routers., ModelLoadingError, AbstractOCREngine, ABC, ndarray (+42 more)

### Community 4 - "test_universal_system.py"
Cohesion: 0.07
Nodes (54): DocumentClassifier, Backwards-compatible wrapper delegating to UniversalDocumentClassifier., Any, Backward-compatible classification method returning (category, confidence)., Universal Multi-Signal Document Classifier supporting 17 document types:…, UniversalDocumentClassifier, fastapi_testclient, pytest (+46 more)

### Community 5 - "app.py"
Cohesion: 0.09
Nodes (43): JSONFormatter, setup_logging(), ImageQualityMetrics, Runs the full OCR pipeline on the uploaded image and returns structured results., run_gradio_ocr(), correct_perspective(), deskew_image(), estimate_skew_angle() (+35 more)

### Community 6 - "IDCardExtractor"
Cohesion: 0.12
Nodes (20): IDCardExtractor, is_address_indicator(), _normalize_ar(), Any, Modular Extractor for Egyptian National ID cards and generic ID cards. Uses…, Maintains complete backwards compatibility for legacy callers., extract_id_fields(), Backwards-compatible wrapper delegating to app.services.extraction.id_card (+12 more)

### Community 7 - ".extract"
Cohesion: 0.29
Nodes (4): Any, Extract structured fields from document text and layout. Must never raise…, Registers a field value along with its field-level confidence and validation…, Attempts to find the underlying OCR confidence of a specific text snippet from…

### Community 8 - "vercel.json"
Cohesion: 0.29
Nodes (6): cleanUrls, headers, outputDirectory, rewrites, $schema, trailingSlash

### Community 9 - "LoggingMiddleware"
Cohesion: 0.50
Nodes (3): LoggingMiddleware, Request, BaseHTTPMiddleware

### Community 10 - "pydantic"
Cohesion: 0.50
Nodes (3): OCRRequest, BaseModel, pydantic

## Knowledge Gaps
- **6 isolated node(s):** `cleanUrls`, `headers`, `outputDirectory`, `rewrites`, `$schema` (+1 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 186 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `UniversalDocumentClassifier` connect `test_universal_system.py` to `TextBlock`, `routers/ocr.py`, `app.py`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Why does `TextBlock` connect `TextBlock` to `BoundingBox`, `test_universal_system.py`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `extract_text()` connect `routers/ocr.py` to `TextBlock`, `BoundingBox`, `test_universal_system.py`, `app.py`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `UniversalDocumentClassifier` (e.g. with `extract_text()` and `DocumentClassifier`) actually correct?**
  _`UniversalDocumentClassifier` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `TextBlock` (e.g. with `EasyOCREngine` and `MistralOCREngine`) actually correct?**
  _`TextBlock` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `BaseExtractor` (e.g. with `ExtractorRegistry` and `test_ocr_engine_is_completely_decoupled_from_extractors()`) actually correct?**
  _`BaseExtractor` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `organize_reading_order()` (e.g. with `TextBlock` and `LanguageDetector`) actually correct?**
  _`organize_reading_order()` has 2 INFERRED edges - model-reasoned connections that need verification._