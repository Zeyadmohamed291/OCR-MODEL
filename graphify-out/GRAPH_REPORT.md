# Graph Report - OCR-MODEL-main  (2026-09-25)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 585 nodes · 1530 edges · 45 communities (22 shown, 23 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 107 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- test_phase2_regressions.py
- test_universal_system.py
- TextBlock
- app.py
- registry.py
- IDCardExtractor
- typing
- test_text_ordering_bidi.py
- core.py
- test_modular_extractors.py
- text_metrics
- .analyze
- organize_reading_order
- extract_text
- build_error_response
- ArabicOCRCorrector
- InvoiceExtractor
- sort_line_bidi_runs
- .extract
- vercel.json
- DriverLicenseExtractor
- pydantic
- .extract
- Request
- BaseModel

## God Nodes (most connected - your core abstractions)
1. `TextBlock` - 39 edges
2. `BaseExtractor` - 33 edges
3. `organize_reading_order()` - 29 edges
4. `UniversalDocumentClassifier` - 27 edges
5. `BoundingBox` - 25 edges
6. `LayoutAnalyzer` - 24 edges
7. `parse_and_validate_date()` - 23 edges
8. `ExtractorRegistry` - 22 edges
9. `AdaptivePreprocessor` - 21 edges
10. `analyze_image_quality()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `test_easyocr_rejects_empty_image()` --uses--> `EasyOCREngine`  [INFERRED]
  tests/test_phase2_regressions.py → app/infrastructure/ocr/easyocr_engine.py
- `test_unknown_document_preserves_full_utility()` --uses--> `UniversalDocumentClassifier`  [INFERRED]
  tests/test_document_understanding.py → app/services/classification/classifier.py
- `test_easyocr_skips_malformed_detections_without_inflating_average_confidence()` --uses--> `EasyOCREngine`  [INFERRED]
  tests/test_phase2_regressions.py → app/infrastructure/ocr/easyocr_engine.py
- `test_mistral_markdown_fallback_keeps_line_breaks_without_fake_geometry()` --uses--> `MistralOCREngine`  [INFERRED]
  tests/test_phase2_regressions.py → app/infrastructure/ocr/mistral_engine.py
- `test_ocr_engine_is_completely_decoupled_from_extractors()` --uses--> `BaseExtractor`  [INFERRED]
  tests/test_modular_extractors.py → app/services/extraction/base.py

## Import Cycles
- None detected.

## Communities (45 total, 23 thin omitted)

### Community 0 - "test_phase2_regressions.py"
Cohesion: 0.05
Nodes (54): health_check(), get, info_endpoint(), get, root_endpoint(), version_endpoint(), document_viewer(), get_sample_image() (+46 more)

### Community 1 - "test_universal_system.py"
Cohesion: 0.06
Nodes (58): DocumentClassifier, Backwards-compatible wrapper delegating to UniversalDocumentClassifier., Any, Backward-compatible classification method returning (category, confidence)., Universal Multi-Signal Document Classifier supporting 17 document types:…, UniversalDocumentClassifier, fastapi_testclient, pil (+50 more)

### Community 2 - "TextBlock"
Cohesion: 0.07
Nodes (45): get_ocr_engine(), get_ocr_engine_by_name(), Returns an OCR Engine instance by provider name ('easy' or 'mistral'). Falls…, Default dependency injection entrypoint for FastAPI routers., AbstractOCREngine, ABC, ndarray, Process the given image and extract text. (+37 more)

### Community 3 - "app.py"
Cohesion: 0.10
Nodes (42): ImageQualityMetrics, Runs the full OCR pipeline on the uploaded image and returns structured results., run_gradio_ocr(), correct_perspective(), deskew_image(), estimate_skew_angle(), ndarray, Rotates image by 90, 180, or 270 degrees clockwise. (+34 more)

### Community 4 - "registry.py"
Cohesion: 0.12
Nodes (24): BankDocumentExtractor, Any, Extractor for Bank Statements, Deposit Slips, and Financial Records., BaseExtractor, ABC, Abstract base class for all document-specific extractors. Each extractor…, GenericExtractor, BaseExtractor (+16 more)

### Community 5 - "IDCardExtractor"
Cohesion: 0.09
Nodes (29): IDCardExtractor, is_address_indicator(), is_valid_egyptian_id(), _normalize_ar(), Any, BaseExtractor, Backwards-compatible wrapper around validate_egyptian_national_id. Returns:…, Modular Extractor for Egyptian National ID cards and generic ID cards. Uses… (+21 more)

### Community 6 - "typing"
Cohesion: 0.17
Nodes (19): Any, Any, compute_mrz_check_digit(), normalize_unicode_digits(), parse_and_validate_date(), Validates standard passport number alphanumeric formats., Calculates ICAO Doc 9303 check digit using weights 7, 3, 1 repeating., Convert Unicode decimal digits to ASCII for validation only. (+11 more)

### Community 7 - "test_text_ordering_bidi.py"
Cohesion: 0.13
Nodes (21): LanguageDetector, Analyzes document text to determine linguistic script and mixture. Supports…, is_bidi_safe(), Verifies that text does not contain forced directional overrides., make_box(), Pure Arabic line: First word on right, second word to its left. Must be ordered…, Pure English line: Must be ordered Left-to-Right: [Invoice, Number, INV-1023]., National ID split into blocks: Must NEVER be reversed. (+13 more)

### Community 8 - "core.py"
Cohesion: 0.25
Nodes (20): DocumentMeta, LayoutBlock, LayoutCell, LayoutInfo, LayoutLine, LayoutSection, LayoutTable, OCRMeta (+12 more)

### Community 9 - "test_modular_extractors.py"
Cohesion: 0.11
Nodes (20): ContractExtractor, Any, Modular Extractor for Contracts and Legal Agreements. Extracts agreement title,…, CVExtractor, Any, Modular Extractor for Resumes and CVs (Curriculum Vitae). Extracts candidate…, PassportExtractor, Modular Extractor for Passports. Supports ICAO Doc 9303 Machine Readable Zone… (+12 more)

### Community 10 - "text_metrics"
Cohesion: 0.16
Nodes (20): aggregate_text_metrics(), _edit_distance(), field_metrics(), Any, Deterministic text and field metrics for labeled OCR evaluations., Return CER, WER and exact match without Unicode or punctuation rewriting., Exact per-field scoring; missing or extra values do not count as correct., Micro-aggregate text metrics over rows with `expected_text`/`actual_text`. (+12 more)

### Community 11 - ".analyze"
Cohesion: 0.22
Nodes (10): Determines the logical reading direction: - 'rtl': Confidently Arabic-only text…, build_structured_field(), normalize_logical_text(), Cleans up whitespace and replaces non-standard space characters WITHOUT ANY…, Builds a StructuredField with automatic language, direction, spatial bounding…, _make_block(), Discovers table rows based on multiple spaced tokens and column alignments.…, Verify fine-grained direction and script classification. (+2 more)

### Community 12 - "organize_reading_order"
Cohesion: 0.21
Nodes (13): Classifies script into 'arabic', 'latin', 'numeric', 'mixed', or 'unknown'., organize_reading_order(), Geometry-aware hierarchical reading order reconstruction. 1. Clusters text…, make_box(), Verify column detection when blocks are horizontally partitioned., Verify invoice extraction extracts table items and attaches source bounding…, Verify that an unknown document still returns text, layout, lines, and detected…, Verify detection of title, header, footer, columns, signatures, and structured… (+5 more)

### Community 13 - "extract_text"
Cohesion: 0.15
Nodes (14): extract_text(), AbstractOCREngine, UploadFile, convert_dict_to_structured_fields(), find_source_bbox(), Any, Transforms extracted key-value dictionary into structured fields with source…, Finds matching layout line bounding box for an extracted value or label. (+6 more)

### Community 14 - "build_error_response"
Cohesion: 0.27
Nodes (12): build_error_response(), create_exception_handlers(), bad_request_handler(), global_exception_handler(), http_exception_handler(), internal_server_error_handler(), payload_too_large_handler(), provider_runtime_error_handler() (+4 more)

### Community 15 - "ArabicOCRCorrector"
Cohesion: 0.24
Nodes (7): ArabicOCRCorrector, Corrects a single OCR line text based on context and positional heuristics., Removes Arabic diacritical marks (harakat/tashkeel)., Processes a list of text lines in sequence, applying contextual and lookahead…, Production-grade Arabic OCR post-processing corrector. Fixes: 1. Distorted…, Intelligent Arabic Domain & OCR Post-Corrector. Specifically targets Arabic OCR…, strip_tashkeel()

### Community 16 - "InvoiceExtractor"
Cohesion: 0.18
Nodes (9): InvoiceExtractor, Any, Modular Extractor for Invoices (commercial, tax, electronic). Extracts invoice…, Any, Checks if subtotal + tax - discount == total within numeric tolerance., validate_invoice_math(), Inconsistent financial totals must be flagged as invalid without altering…, test_invoice_arithmetic_inconsistency_validation() (+1 more)

### Community 17 - "sort_line_bidi_runs"
Cohesion: 0.22
Nodes (10): get_block_bounds(), get_block_center(), get_block_direction(), get_line_direction(), Returns (min_x, min_y, max_x, max_y) for a block., Returns (center_x, center_y) for a block., Returns 'rtl' or 'ltr' for a single block., Determines whether a line's primary reading direction is RTL or LTR. Looks at… (+2 more)

### Community 18 - ".extract"
Cohesion: 0.29
Nodes (4): Any, Extract structured fields from document text and layout. Must never raise…, Registers a field value along with its field-level confidence and validation…, Attempts to find the underlying OCR confidence of a specific text snippet from…

### Community 19 - "vercel.json"
Cohesion: 0.29
Nodes (6): cleanUrls, headers, outputDirectory, rewrites, $schema, trailingSlash

### Community 20 - "DriverLicenseExtractor"
Cohesion: 0.40
Nodes (4): DriverLicenseExtractor, Any, Modular Extractor for Driving Licenses. Extracts license number, holder name,…, test_driver_license_extraction()

### Community 21 - "pydantic"
Cohesion: 0.50
Nodes (3): OCRRequest, BaseModel, pydantic

## Knowledge Gaps
- **6 isolated node(s):** `cleanUrls`, `headers`, `outputDirectory`, `rewrites`, `$schema` (+1 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 207 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TextBlock` connect `TextBlock` to `test_universal_system.py`, `test_text_ordering_bidi.py`, `core.py`, `.analyze`, `organize_reading_order`, `sort_line_bidi_runs`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Why does `organize_reading_order()` connect `organize_reading_order` to `test_universal_system.py`, `TextBlock`, `app.py`, `test_text_ordering_bidi.py`, `core.py`, `.analyze`, `extract_text`, `sort_line_bidi_runs`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `BaseExtractor` connect `registry.py` to `typing`, `test_modular_extractors.py`, `InvoiceExtractor`, `.extract`, `DriverLicenseExtractor`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `TextBlock` (e.g. with `EasyOCREngine` and `MistralOCREngine`) actually correct?**
  _`TextBlock` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `BaseExtractor` (e.g. with `ExtractorRegistry` and `test_ocr_engine_is_completely_decoupled_from_extractors()`) actually correct?**
  _`BaseExtractor` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `organize_reading_order()` (e.g. with `TextBlock` and `LanguageDetector`) actually correct?**
  _`organize_reading_order()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `UniversalDocumentClassifier` (e.g. with `DocumentClassifier` and `test_classify_all_supported_document_types()`) actually correct?**
  _`UniversalDocumentClassifier` has 17 INFERRED edges - model-reasoned connections that need verification._