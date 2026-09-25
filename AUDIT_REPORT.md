# OCR Project Audit Report

**Scope:** Read-only source audit of the checked-out project. No application code was changed and tests were not run. Conclusions below are based on the current source, configuration, and tests; README and design documents are treated as claims to verify, not as proof of runtime behavior.

## Executive Summary

This repository implements OCR and document extraction in a FastAPI service, with a second Gradio entry point. The runtime pipeline is ordinary sequential Python orchestration with a conditional second OCR pass; there is no LangGraph/StateGraph, application workflow graph, LLM prompt, or graph-node implementation in `app/`. The `graphify-out` knowledge graph is generated repository-analysis metadata, while README/design Mermaid diagrams describe a conceptual pipeline.

The best-supported causes of inconsistent results are post-OCR mutation of Arabic text, low-specificity OCR quality routing, image resizing without preserving the coordinate transform, uneven handling of page-format images, Mistral JPEG conversion and response parsing, layout/order heuristics, and the fact that the async API performs CPU/model/network work synchronously. The system does not use an LLM to correct text, so LLM hallucination is not a current runtime cause. Current “structured extraction” is regex/heuristic-based and is not an LLM structured-output call.

## 1. Current Architecture

- **HTTP/API entry:** `app/main.py` constructs FastAPI, installs CORS, request logging, exception handlers, and routers. The main OCR endpoint is `POST /ocr/extract` in `app/api/v1/routers/ocr.py`.
- **Alternate entry:** `app.py` constructs a Gradio UI and attaches the FastAPI routes. It duplicates much of the OCR/classify/extract sequence in `run_gradio_ocr`.
- **Application structure:** `app/domain` contains Pydantic schemas and an abstract OCR engine interface; `app/infrastructure/ocr` contains EasyOCR and Mistral adapters; `app/services` contains preprocessing, layout, classification, extraction, and text correction; `app/api` contains routing/dependencies.
- **Provider selection:** `app/api/dependencies/ocr.py` memoizes engine objects by provider name. Default is EasyOCR; request query parameter `provider` may select Mistral. A Mistral request without a key silently falls back to EasyOCR.
- **Output:** `OCRResponse` in `app/domain/schemas/responses.py` returns text, layout, fields, structured fields, sections, tables, OCR confidence/engine, quality metrics, and stage timings.
- **No persistent data layer:** No database, external document store, OCR-result cache, or job queue is present in the inspected runtime.

## 2. OCR Pipeline

### FastAPI path

`POST /ocr/extract` follows these stages:

1. Resolve the requested OCR engine.
2. Validate filename, declared content type, and declared upload size (`validate_image_metadata`).
3. Read all bytes in `load_image`, enforce actual byte-size, inspect magic bytes, decode with Pillow/EXIF transpose and fallback to OpenCV, then enforce dimensions/pixel count.
4. Analyze blur, brightness, contrast, resolution, and skew (`analyze_image_quality`).
5. Apply adaptive geometry, scale, grayscale, optional illumination correction/denoise/CLAHE/sharpening (`AdaptivePreprocessor.preprocess_adaptive`). Keep primary and geometry-corrected original variants; sometimes also create an enhanced threshold variant.
6. OCR primary. Score detections with a composite confidence/coherence/volume/pattern metric. OCR the geometry-corrected original only if there are no blocks or score is below 0.50; select or merge the two results.
7. Reconstruct reading order and bidi runs, apply Arabic correction, analyze lines/blocks/sections/tables.
8. Detect language and document category with local regex, keyword, geometry, and layout signals.
9. Run generic regex entity extraction plus one specialized extractor, attach field metadata, produce structured fields, then serialize the response.

### Gradio path

`run_gradio_ocr` independently converts input to BGR, analyzes quality, preprocesses, performs **one** OCR pass, then ordering/correction/layout/classification/extraction. It does not execute the FastAPI conditional retry/merge, does not use image metadata, and has a different error/output contract. Thus callers can get different results for the same document depending on entry point.

### Engines

- **EasyOCR:** `EasyOCREngine` loads EasyOCR reader languages `['ar', 'en']`, `gpu=False`, with a singleton/initialization lock. `readtext` uses fixed thresholds and batch size. It filters some short border artifacts, normalizes coordinates using the actual OCR image dimensions, sorts detections, and applies Arabic correction before returning.
- **Mistral OCR:** `MistralOCREngine` JPEG-encodes the image (OpenCV default encoding settings), Base64-embeds it as a data URI, and calls `mistral-ocr-latest` with page-level confidence. It strips Markdown, parses blocks or synthesizes line boxes from page Markdown, applies Arabic correction, and sorts blocks.
- **Prompts/LLMs:** No prompt templates, chat/completions calls, vision LLM calls, or LLM-based text repair were found under application code, tests, or requirements. Mistral is an OCR API call, not a prompted extraction/agent step in this code.

## 3. Graph Architecture and Routing

### Runtime graph finding

There is **no runtime graph framework or explicit graph** in the application: searches found no `StateGraph`, `langgraph`, `add_node`, conditional-edge declarations, node-state type, or graph compile/invoke. The only application routing branches materially affecting OCR are in `extract_text` and engine selection. No loops exist in the OCR orchestration.

### Runtime node-by-node equivalent

Because runtime is sequential rather than a graph, this table maps each pipeline stage to its actual inputs, outputs, state, model work, routing, purpose, and token cost.

| Stage / location | Input and state | Output | Model/API calls and prompt | Routing and purpose | Token cost / waste |
|---|---|---|---|---|---|
| Engine resolution — `app/api/dependencies/ocr.py`, endpoint lines 38–45 | Provider query/config; module `_engines` cache | Cached EasyOCR or Mistral engine | EasyOCR model initialization/download on first use; no prompt | Unknown provider and missing-key Mistral path fall through to EasyOCR | No LLM tokens; provider silently changing may surprise callers |
| Validation/decode — `validator.py`, `loader.py` | `UploadFile`, settings; in-memory bytes | BGR ndarray and `ImageMetadata` | None | Reject metadata/signature/decode/size/dimension failures | No token cost |
| Quality/preprocess — `quality.py`, `preprocessor.py`, `geometry.py` | Image, `ImageQualityMetrics` | Primary, original, optional enhanced images | None | Geometry/contrast/quality-based transform branches; `enhanced` is never OCR-routed | No token cost; extra image allocations/compute |
| Pass A — `extract_text`, `EasyOCREngine.process_image` or Mistral equivalent | Primary image; engine reader/client | `OCRResult` blocks, confidence, raw output | Local neural inference or one OCR API call; no prompt | Always called | Mistral API/image cost is incurred once for every request |
| Quality evaluator — `evaluator.py` | Pass A text/confidences | Composite score and signals | None | Request Pass B if empty or score `< 0.50` | No token cost; can misroute because score is generic heuristic |
| Pass B/select/merge — `extract_text`, `select_or_merge_passes` | Pass A, geometry-corrected original, boxes/text | Chosen/merged `OCRResult` | A second local inference or Mistral OCR API call; no prompt | At most one retry; high-confidence non-overlapping detections from other pass can be appended | Potentially doubles OCR inference/API usage; intentionally conditional, not an LLM-token optimization |
| Reading order/correction/layout — `reading_order.py`, `arabic_corrector.py`, `layout_analyzer.py` | Result blocks and image dimensions | Ordered/mutated blocks; `LayoutInfo`, sections, tables | None | Heuristic line clustering/columns/table detection | No token cost; repeated correction occurs in some provider/request combinations |
| Language/classification — `language_detector.py`, `classifier.py` | Combined text, layout, metadata | Language and category/confidence | None | Classifier category chooses one specialized extractor downstream | No token cost; OCR mistakes can select wrong extractor |
| Extraction/response — `registry.py`, extractor modules, `bidi_formatter.py` | Full combined text, layout, metadata, category | Fields and structured fields / JSON response | None; regex and hand-authored rules | Generic extractor always runs; specialized extractor for category | No token cost; full text and layout state are passed in-process, not to an LLM |

### State and context size

There is no graph state object. Data is passed as Python objects: full image arrays/variants, `OCRResult` including `raw_output`, ordered text blocks, full `LayoutInfo`, full `combined_text`, and metadata. The endpoint retains `variants` and `result.raw_output` until completion. This costs memory but does not create prompt tokens. Mistral raw SDK response is retained for formatted Markdown extraction and not passed to a model again.

### Token optimization strategy

The current graph-specific token strategy requested for inspection is not present because there are no LLM/model text calls. The closest runtime optimization is **conditional second-pass OCR**: primary only by default, one retry on empty/low composite score; initialized engines are memoized; EasyOCR model loads once per process. There is no token counter, prompt-size limiter, model-call cache, or node-level LLM routing. The score threshold and two-pass selector appear designed to save OCR inference/API calls, not LLM tokens.

## 4. Problems Found and Root Causes

Severity describes observed source-level risk, not measured production frequency.

### HIGH — Post-correction can silently replace valid Arabic OCR text

- **Problem:** Returned text can differ from engine output without preserving a user-visible raw alternative.
- **Root Cause:** Canonical pattern/lookahead substitutions in `ArabicOCRCorrector` rewrite headers, titles, names, and governorates. Corrections are invoked in EasyOCR engine, request route, Gradio route, Mistral engine, and some extractors. For example, a matching top-of-document line can become exactly `جمهورية مصر العربية`; name substitutions include common words such as `محمل` → `محمد`. `raw_text` may retain an earlier value in layout objects, but response `text` is corrected and the EasyOCR engine mutates blocks first.
- **Impact:** Correct names/words can be corrupted; detection confidence still reflects the original model output; same line can be corrected multiple times or with a different context.
- **Location:** `app/services/text_processing/arabic_corrector.py`; `app/infrastructure/ocr/easyocr_engine.py`; `app/infrastructure/ocr/mistral_engine.py`; `app/api/v1/routers/ocr.py`; `app.py`; `app/services/extraction/id_card.py`.
- **Recommended Fix:** Establish immutable raw OCR text and make normalization/correction conservative, field-aware, confidence-aware, and auditable. Add regression examples for true positives and false positives before enabling changes.
- **Risk of Fix:** Disabling broad corrections may reduce recovery of known Egyptian ID header/name errors; requires representative Arabic validation data.

### HIGH — OCR pass routing score is not a measure of transcription correctness

- **Problem:** Incorrect but fluent/high-volume text can avoid a second pass; short or numeric documents can be sent to a second pass unnecessarily.
- **Root Cause:** `evaluate_detection_quality` combines average confidence, ASCII/Arabic alphanumeric ratio, character volume, and a boost for patterns such as dates/IDs/emails. It has no ground truth or semantic consistency check. Numeric patterns can boost an incorrect ID/date; mixed non-Arabic scripts can reduce the coherence score because its meaningful-character regex only counts Arabic range, Latin letters, and ASCII digits.
- **Impact:** Wrong OCR may be accepted as “good”; unnecessary retries increase latency/cost; merging can append inconsistent duplicate text.
- **Location:** `app/services/ocr/evaluator.py`; threshold/branch in `app/api/v1/routers/ocr.py`.
- **Recommended Fix:** Calibrate routing against labeled image/transcription pairs by language, document type, and image quality; keep the conditional second pass and tune its score/features using measured error reduction vs call cost.
- **Risk of Fix:** Calibration data may not cover deployment domains; overly sensitive routing raises cost/latency, while lax routing preserves error.

### HIGH — Preprocessed-image coordinates can be interpreted against original dimensions

- **Problem:** Scale/crop/rotation changes are not consistently represented in output geometry.
- **Root Cause:** `AdaptivePreprocessor` may resize primary image to `MAX_DIM=3200` or upscale it; `EasyOCREngine` reports coordinates/dimensions in the image it receives. The API then calls `organize_reading_order(..., image_width=result.image_width)` and layout analysis with result dimensions, but overall response does not expose original-to-processed transform. More notably, the fallback `original` is geometry-corrected, but OCR result dimensions are those of whichever variant produced the selected result; `quality` metadata remains original dimensions. There is no explicit transform mapping boxes back to upload coordinates.
- **Impact:** Viewer/source boxes can be misaligned with the uploaded image; metadata/boxes may describe different coordinate spaces after scale or perspective warp.
- **Location:** `app/services/image_processing/preprocessor.py`; `app/infrastructure/ocr/easyocr_engine.py`; `app/api/v1/routers/ocr.py`; `app/services/layout/layout_analyzer.py`.
- **Recommended Fix:** Track each variant’s geometric transform and define one documented coordinate space; transform selected/merged boxes consistently before response construction.
- **Risk of Fix:** Perspective warps are not invertible in a simple scale-only path; coordinate migration can affect consumers that rely on current pixel conventions.

### HIGH — Request upload validation does not reject all actual unsupported content types consistently

- **Problem:** Declared-type and actual-signature checks use different format sets.
- **Root Cause:** `settings.ALLOWED_IMAGE_TYPES` excludes TIFF and BMP, while `detect_image_magic_bytes` recognizes them; loader trusts detected MIME and decodes the image. The route calls `validate_image_metadata(file)` without `header_bytes`, so its signature check is not used there; actual magic checking is deferred to loader. Declared content type is checked against the narrower list, but absent/misleading content type can pass to loader for formats it decodes.
- **Impact:** Behavior varies by client MIME header; supported-format policy is unclear; unsupported formats may be accepted if decoder handles them.
- **Location:** `app/core/config.py`; `app/services/image_processing/validator.py`; `app/services/image_processing/loader.py`; `app/api/v1/routers/ocr.py`.
- **Recommended Fix:** Define one explicit supported-format policy and enforce both detected content and decode format against it after bounded read.
- **Risk of Fix:** Tightening accepted formats can reject existing caller uploads; widening allowed types changes API contract.

### HIGH — Synchronous OCR and preprocessing block the async event loop

- **Problem:** `async def extract_text` performs CPU-heavy OpenCV, EasyOCR, layout/classification, and synchronous Mistral SDK calls inline.
- **Root Cause:** Only upload read is awaited. Inference is synchronous and no threadpool, process pool, async provider client, queue, or per-worker concurrency limiter is present.
- **Impact:** A long OCR call can delay unrelated requests on the same event loop; concurrent requests can cause CPU/RAM oversubscription and poor tail latency.
- **Location:** `app/api/v1/routers/ocr.py`; `app/infrastructure/ocr/easyocr_engine.py`; `app/infrastructure/ocr/mistral_engine.py`; `app/services/image_processing/preprocessor.py`; `Dockerfile` (`WEB_CONCURRENCY=1` default).
- **Recommended Fix:** Measure workload and isolate blocking work with bounded concurrency appropriate to CPU/memory; use provider timeouts and explicit overload behavior.
- **Risk of Fix:** Threaded Torch/OpenCV calls may contend for native threads; extra workers duplicate model memory; provider SDK timeout behavior must be checked against installed version.

### HIGH — Mistral path changes image pixels and fabricates fallback geometry

- **Problem:** Remote OCR quality and reported geometry may diverge from original input.
- **Root Cause:** Every Mistral input is JPEG-encoded with default quality regardless of source; block coordinates are treated as pixel coordinates without unit/scale conversion; page confidence is assigned to each block; when page blocks are unavailable, Markdown lines are given uniform full-width horizontal bands unrelated to actual text locations.
- **Impact:** JPEG artifacts can hurt small text/Arabic dots; coordinates may be wrong if API uses another coordinate convention; fabricated boxes make layout/source-bbox outputs appear more precise than they are.
- **Location:** `app/infrastructure/ocr/mistral_engine.py` (encoding lines 90–112, block parsing and Markdown fallback).
- **Recommended Fix:** Validate SDK response coordinate units/version against fixtures, preserve original image fidelity or choose encoding deliberately, and mark unavailable geometry as unavailable instead of synthetic line boxes.
- **Risk of Fix:** Provider response schema can evolve; retaining PNG or high-quality JPEG increases network payload and latency.

### HIGH — Readiness and provider cache are inaccurate/racy under concurrent requests

- **Problem:** Health can report `engine_ready=True` for a Mistral engine that does not initialize local OCR weights; concurrent first-time provider requests can initialize multiple Mistral clients.
- **Root Cause:** `_engine_instance` is set when any provider is cached, and health uses only that global flag. `_engines` lookup/creation is unsynchronized; EasyOCR has its own initialization lock but Mistral does not.
- **Impact:** Health may not indicate OCR readiness; duplicate initialization or inconsistent cached provider state can occur under races.
- **Location:** `app/api/dependencies/ocr.py`; `app/api/v1/routers/health.py`.
- **Recommended Fix:** Report provider-specific readiness and synchronize engine registry initialization; distinguish initialized client from successful provider health.
- **Risk of Fix:** Readiness checks may add startup/probe work or trigger external provider requests if designed as active checks.

### MEDIUM — Preprocessing quality signals and active transformations are misaligned

- **Problem:** Some advertised quality corrections do not run, and blur/noise branches may use the wrong signal.
- **Root Cause:** `analyze_image_quality` computes skew but not orientation; `rotate_cardinal` is never called in API or Gradio flow. Perspective and deskew are active. In `preprocess_adaptive`, bilateral denoise is enabled when `quality.blur_score > 300` (a high Laplacian variance typically indicates sharp/high-frequency content) or shadow gradient, while sharpening is enabled for detected blur. Upscaling uses minimum side `<750` only if max side `<1400`, which can substantially enlarge panoramas/crops and does not use DPI metadata. The “enhanced” Otsu variant is created but never OCRed.
- **Impact:** Rotated pages remain rotated; sharp/noisy pages may be smoothed, blurred pages may be sharpened without real recoverable detail; extra image allocations are unused.
- **Location:** `app/services/image_processing/quality.py`; `geometry.py`; `preprocessor.py`; `app/api/v1/routers/ocr.py`.
- **Recommended Fix:** Validate every metric/branch on a labeled image set; wire explicit orientation correction only when reliable; route the enhanced variant conditionally only if measured benefit justifies an extra pass; remove or adjust inactive paths after benchmarking.
- **Risk of Fix:** Threshold tuning is document/source dependent; auto-rotation can rotate correctly oriented content incorrectly.

### MEDIUM — Reading order and layout heuristics can mix columns and degrade tables

- **Problem:** Multi-column reading order and table reconstruction are approximate.
- **Root Cause:** `organize_reading_order` clusters by vertical overlap and bidi runs without column segmentation. `LayoutAnalyzer` joins same-line blocks in returned order; its table detector splits text on two literal spaces, even though line text is joined with single spaces, and creates a table from all potential rows without spatial column alignment or row grouping. Classifier uses layout signals, so these errors can also change routing to extractors.
- **Impact:** Reading order can interleave columns; cell boundaries/data can be missing or incorrectly grouped; classification and structured fields can be wrong.
- **Location:** `app/services/layout/reading_order.py`; `app/services/layout/layout_analyzer.py`; `app/services/classification/classifier.py`.
- **Recommended Fix:** Treat columns and tables as geometry/layout tasks using block coordinates; validate against multi-column/table fixtures across RTL/LTR before changing heuristics.
- **Risk of Fix:** Better layout models or geometric heuristics add compute and can alter output ordering relied on by clients.

### MEDIUM — Post-processing runs repeatedly and confidence is not updated

- **Problem:** Text normalization can be applied multiple times while confidence remains tied to raw OCR.
- **Root Cause:** EasyOCR and Mistral engines run Arabic correction; API and Gradio run contextual correction again; API then calls `correct_line` on layout-line text again. TextBlock `raw_text` is captured by reading order after engine corrections, so it is not guaranteed to be raw engine text. Mistral assigns page confidence to every block; block-average calculations therefore do not reflect line-level confidence.
- **Impact:** Corrections are difficult to audit; false corrections survive as high-confidence results; returned confidence can overstate field accuracy.
- **Location:** OCR engine modules; `reading_order.py`; endpoint; Arabic corrector; Mistral parser.
- **Recommended Fix:** Keep raw/normalized/corrected values distinct, apply each transformation at one stage, and propagate confidence provenance at field/block level.
- **Risk of Fix:** Response schema/API consumers may depend on existing text fields and confidence semantics.

### MEDIUM — Extraction and structured field metadata can imply stronger validation than occurred

- **Problem:** Some values are regex-extracted or heuristic-derived but marked valid with fixed high confidence; raw field metadata is partly omitted from the API response.
- **Root Cause:** Generic extractor marks amounts and URLs valid based primarily on pattern matching; some specialized extractors use fixed confidence. The endpoint strips `_field_confidences` and `_field_metadata` from `fields`; `structured_fields` keeps selected values but `source_bbox` lookup often uses corrected extracted values against layout text and may fail. `OCRResponse.field_details` is declared but not populated.
- **Impact:** Consumers may treat syntactic plausibility as verified correctness; auditability/source traceability is limited.
- **Location:** `app/services/extraction/generic.py`; specialized extractor modules; `app/services/layout/bidi_formatter.py`; `app/api/v1/routers/ocr.py`; `app/domain/schemas/responses.py`.
- **Recommended Fix:** Define validation semantics separately from pattern matches, expose provenance/field metadata intentionally, and make missing source geometry explicit.
- **Risk of Fix:** API response changes may break clients or expose more document content than intended.

### MEDIUM — Date and numeric localization handling is incomplete

- **Problem:** Arabic-Indic/Persian numerals are detected in language logic but not consistently normalized by date/ID/amount validators and regex extractors.
- **Root Cause:** `LanguageDetector` recognizes Arabic-Indic digits, but `parse_and_validate_date`, `validate_egyptian_national_id`, generic amount/date patterns, and many specialized regexes use ASCII digits. ID extraction has some local normalization paths but coverage is inconsistent.
- **Impact:** Correct OCR digits can fail validation/extraction, particularly Arabic-script dates, IDs, and financial values.
- **Location:** `app/services/language/language_detector.py`; `app/services/extraction/validation.py`; `app/services/extraction/generic.py`; specialized extractors.
- **Recommended Fix:** Normalize Unicode decimal digits at clearly defined extraction boundaries while preserving the original OCR text and locale semantics; add mixed-script fixtures.
- **Risk of Fix:** Digit normalization must not confuse visually similar letters or erase meaningful script distinctions.

### MEDIUM — Provider failures, timeouts, and retries are not normalized

- **Problem:** Remote provider calls have no explicit application timeout/retry/backoff/circuit breaker; raw exceptions are inconsistently wrapped.
- **Root Cause:** Mistral SDK call is synchronous; exceptions become generic `RuntimeError`; these do not map to the custom OCR error handler and reach global 500 handling. There is no retry policy for transient 429/5xx/network errors. EasyOCR initialization downloads model weights at runtime when absent.
- **Impact:** Requests can hang or fail with generic errors; transient failures are not retried; network/model-download availability affects local provider startup.
- **Location:** `app/infrastructure/ocr/mistral_engine.py`; `app/api/dependencies/ocr.py`; `app/infrastructure/ocr/easyocr_engine.py`; `app/core/exception_handlers.py`.
- **Recommended Fix:** Set explicit bounded deadlines and classify provider errors; use limited idempotent retries only for transient conditions; make model download policy/deployment readiness explicit.
- **Risk of Fix:** Retries increase cost and latency; SDK timeout/retry defaults vary by dependency version.

### MEDIUM — Actual upload size limit is enforced only after full buffering

- **Problem:** The loader reads the entire multipart file into memory before enforcing `MAX_UPLOAD_SIZE_MB`.
- **Root Cause:** `contents = await file.read()` precedes byte-count validation. Declared `file.size` validation may catch some requests, but the source does not guarantee it is supplied.
- **Impact:** Oversized uploads can consume memory before rejection; concurrent uploads multiply peak memory. Decoded arrays and image variants add further memory.
- **Location:** `app/services/image_processing/loader.py`; `app/services/image_processing/validator.py`; `app/core/config.py`.
- **Recommended Fix:** Enforce request/body limits at proxy/server and read uploads in bounded chunks before decoding; account for decoded pixels and variant allocations in concurrency limits.
- **Risk of Fix:** Chunked upload handling and upstream limits need coordinated deployment configuration.

### MEDIUM — Logging can expose operational details and is not process-safe by design

- **Problem:** Exceptions are logged with full traceback and exception messages; persistent local file logging is unconditional.
- **Root Cause:** JSON formatter emits `exc_info`; loader debug includes decoder exception messages; Mistral failures log provider exception text. Application logs go to `logs/app.log`; docs emphasize sensitive ID/financial documents, and future exceptions could include sensitive payload details. Multiple processes would write the same file without a multiprocess-safe handler/rotation.
- **Impact:** Secrets or document-derived data in exception messages could leak to logs; log files can grow without rotation and concurrent workers can interleave writes.
- **Location:** `app/core/logging.py`; `app/core/exception_handlers.py`; image loader; Mistral engine; Dockerfile.
- **Recommended Fix:** Keep logs metadata-only, redact provider errors/secrets, define retention/rotation and container logging policy, and avoid shared-file logging across workers.
- **Risk of Fix:** Redaction can remove details needed for incident debugging; structured safe diagnostics should replace raw exception text.

### MEDIUM — CORS policy is permissive for a service handling sensitive documents

- **Problem:** All origins/methods/headers are allowed while credentials are enabled.
- **Root Cause:** `app/main.py` configures `allow_origins=["*"]` and `allow_credentials=True`.
- **Impact:** Any browser origin can access credentialed cross-origin APIs if browser/client authentication is later added; current source has no authentication/authorization layer.
- **Location:** `app/main.py` CORS middleware.
- **Recommended Fix:** Restrict origins and methods to deployment needs and add an explicit authentication/authorization boundary if service is exposed beyond trusted networks.
- **Risk of Fix:** Incorrect origin configuration can block legitimate dashboard/API clients.

### LOW — Enhanced OCR variant and several configuration fields are dead or misleading

- **Problem:** Some configuration or preprocessing outputs imply behavior that does not occur.
- **Root Cause:** `CONFIDENCE_THRESHOLD` and `MODEL_DIR` are not used by the EasyOCR constructor (it hardcodes `models/easyocr`); `preprocess_for_ocr` is imported by the endpoint but unused; `variants["enhanced"]` is created but never passed to OCR; detection `median confidence` is described but not calculated. README architecture advertises orientation handling and validation controls not active in the path.
- **Impact:** Operators may believe settings are honored; unused paths add maintenance/compute cost; documentation does not accurately describe behavior.
- **Location:** `app/core/config.py`; `app/infrastructure/ocr/easyocr_engine.py`; `app/api/v1/routers/ocr.py`; `app/services/ocr/evaluator.py`; README.
- **Recommended Fix:** Reconcile runtime, configuration, and docs; remove dead imports/metrics or wire them after measured need.
- **Risk of Fix:** Removing undocumented compatibility surfaces may affect deployment scripts or external users relying on assumed settings.

### LOW — Multi-page document support is not implemented end to end

- **Problem:** API is image-oriented and output layout hardcodes one page in the local layout analyzer.
- **Root Cause:** Magic bytes/loader are image-specific; PDF is not accepted/decoded. Mistral may return multiple pages, but local `LayoutAnalyzer` emits `pages=1`, and EasyOCR blocks use `page=1`.
- **Impact:** PDFs and multi-page documents are unsupported or incompletely represented despite broad “document” language.
- **Location:** `app/services/image_processing/validator.py`; `loader.py`; `layout_analyzer.py`; `easyocr_engine.py`; `mistral_engine.py`.
- **Recommended Fix:** State supported input scope explicitly, or design a page-aware document ingestion/processing API with per-page metadata and limits.
- **Risk of Fix:** PDF/page support increases parsing surface, memory, runtime, and attack surface.

### LOW — Test coverage emphasizes synthetic logic, not OCR accuracy against labeled documents

- **Problem:** Tests cover many heuristics and synthetic images but do not establish real-world character accuracy or the quality score’s routing calibration.
- **Root Cause:** Most fixtures are constructed strings or OpenCV-generated English synthetic images; tests assert preprocessing output shape/safety and extractor behavior. No labeled image corpus, character/word error rate evaluation, Arabic font/quality matrix, Mistral response fixtures, or concurrency/load tests were found.
- **Impact:** Thresholds and corrections can regress real Arabic, tables, small text, and mixed-script inputs without test failures.
- **Location:** `tests/`; `scripts/validate_ocr.py`; `scripts/debug_ocr.py`.
- **Recommended Fix:** Build a consented representative evaluation set; report CER/WER and field accuracy by language/layout/quality; add deterministic provider-response fixtures and concurrency/load checks.
- **Risk of Fix:** Evaluation data collection has privacy/licensing costs; metric improvements may trade off by document type.

## 5. Production Risks

| Area | Finding | Severity |
|---|---|---|
| Exceptions | API has custom structured handlers, but generic provider failures and arbitrary exceptions map to 500; no request-level OCR recovery beyond one quality-triggered alternate image pass. | MEDIUM |
| Timeouts | No explicit OCR/Mistral processing deadline; keep-alive timeout is not a processing timeout. | HIGH |
| Malformed responses | Mistral parser uses `getattr` fallbacks and assumes page/block fields are iterable/coordinate-compatible; malformed SDK responses can throw or yield misleading geometry. | MEDIUM |
| Corrupted files | Magic bytes, decode checks, dimension and pixel caps are present; validator is invoked without header bytes, with signature enforcement later in loader. | LOW/MEDIUM |
| Unsupported formats | PDF absent; TIFF/BMP signature recognition does not match configured MIME allowlist. | MEDIUM |
| Large files | Declared size and pixel/dimension limits exist, but actual byte count is checked after full body buffering; preprocessing creates multiple arrays. | MEDIUM |
| Async/concurrency | Async endpoint blocks synchronously; engine registry Mistral initialization is not locked; no per-worker inference semaphore. | HIGH |
| Memory | Entire upload bytes, decoded image, transformed variants, OCR raw output/layout are simultaneously live; container default 3 GB memory/2 CPUs. | MEDIUM |
| Temporary files | Upload images stay in memory; logs and EasyOCR model files persist on disk. No per-request temp files in current loader. | LOW |
| Secrets | Mistral key comes from Pydantic settings and `.env` is gitignored; no secret is hardcoded. Raw provider exception logging could still expose sensitive information. | MEDIUM |
| Unsafe logging | Request path/timings are logged; no image/text is intentionally logged, but exception strings/tracebacks are unredacted. | MEDIUM |
| Prompt injection | No LLM prompts exist in runtime, so prompt injection is not a current model-call path. If future LLM extraction is added, OCR text must be treated as untrusted data. | LOW (current) |
| Caching | Engine objects/model initialization cached in process; no OCR result cache. Global provider registry and health indicator have races/semantics issues. | MEDIUM |
| Configuration | `.env.example` documents provider/key; configured `MODEL_DIR` and `CONFIDENCE_THRESHOLD` do not fully control runtime. Runtime EasyOCR downloads weights if missing. | MEDIUM |

## 6. Files and Functions Involved

- **Application lifecycle / API:** `app/main.py:lifespan`, `app/api/v1/routers/ocr.py:extract_text`, `app.py:run_gradio_ocr`.
- **Upload/security:** `app/services/image_processing/validator.py:validate_image_metadata`, `detect_image_magic_bytes`; `loader.py:load_image`.
- **Quality and geometry:** `quality.py:analyze_image_quality`; `preprocessor.py:AdaptivePreprocessor.preprocess_adaptive`; `geometry.py:estimate_skew_angle`, `deskew_image`, `rotate_cardinal`, `correct_perspective`.
- **OCR models/adapters:** `app/api/dependencies/ocr.py:get_ocr_engine_by_name`; `easyocr_engine.py:EasyOCREngine.process_image`; `mistral_engine.py:MistralOCREngine.process_image`, `_strip_markdown`.
- **Pass evaluation/routing:** `app/services/ocr/evaluator.py:evaluate_detection_quality`, `select_or_merge_passes`; endpoint conditional around Pass B.
- **Text/layout:** `arabic_corrector.py:correct_line`, `correct_text_block_lines`; `reading_order.py:organize_reading_order`; `layout_analyzer.py:LayoutAnalyzer.analyze`, `_detect_tables`; `bidi_formatter.py`.
- **Understanding/extraction:** `language_detector.py`; `classification/classifier.py:UniversalDocumentClassifier.classify_with_signals`; `extraction/registry.py:ExtractorRegistry.extract`; `extraction/validation.py`; specialized extractors.
- **Schemas/observability:** `domain/schemas/core.py`; `responses.py:OCRResponse`; `core/logging.py`; `core/exception_handlers.py`; `api/v1/routers/health.py`.
- **Configuration/deployment:** `app/core/config.py`; `.env.example`; `requirements.txt`; `Dockerfile`; `docker-compose.yml`; `vercel.json`; `run_server.py`.
- **Tests:** `tests/test_ocr_optimization.py`; `test_preprocessing_pipeline.py`; `test_production_hardening.py`; `test_text_ordering_bidi.py`; `test_document_understanding.py`; `test_modular_extractors.py`; `test_universal_system.py`; `test_extraction.py`.

## 7. Recommended Fixes and Priority Order

1. **HIGH — Protect source text and correction provenance.** Stop treating heuristic canonicalization as ground truth; preserve immutable raw OCR and quantify correction false positives.
2. **HIGH — Calibrate multi-pass routing.** Retain the cost-saving conditional pass, but tune the trigger/selection with labeled accuracy and call-cost measurements by input class.
3. **HIGH — Define image coordinate invariants.** Track scale/perspective transforms and return/document one coordinate space for every OCR result.
4. **HIGH — Bound blocking work.** Add measured, bounded OCR concurrency and explicit provider deadlines/overload handling so async endpoints remain responsive.
5. **HIGH — Normalize Mistral image/response behavior.** Verify coordinate units, preserve image fidelity intentionally, remove misleading synthetic geometry, normalize provider errors.
6. **HIGH — Make provider readiness/cache truthful and race-safe.** Separate per-provider initialized/healthy states and synchronize lazy construction.
7. **MEDIUM — Align upload format and size controls.** Enforce actual byte limits before whole-file buffering and unify allowed MIME types with decoder/signature policy.
8. **MEDIUM — Validate preprocessing thresholds and orientation.** Test bilateral/CLAHE/sharpening/resize branches on representative low-quality Arabic, small-font, table, and mixed-language scans; OCR enhanced variant only when benefit is proven.
9. **MEDIUM — Improve geometry-driven layout for columns/tables.** Do not infer grid columns from double spaces alone; evaluate reading order and table cell accuracy on realistic layouts.
10. **MEDIUM — Consolidate post-processing/confidence and validation metadata.** Correct exactly once, retain raw/corrected variants, use calibrated confidence semantics, and expose source provenance consistently.
11. **MEDIUM — Normalize Unicode digits and numeric formats.** Preserve raw script while normalizing input to validators/extractors.
12. **MEDIUM — Harden logs, CORS, and provider failure policy.** Add redaction/retention, deployment-origin policy, and explicit transient-failure handling.
13. **LOW — Reconcile docs/configuration and scope.** Update unsupported/misleading orientation/offline/provider claims, wire or remove dead settings/variants, and state image-only/page support clearly.
14. **LOW — Add a labeled OCR evaluation corpus and operational tests.** Measure CER/WER and field accuracy; add Mistral parsing, timeout, memory, and concurrency coverage.

## 8. Audit Limitations

- No production images, logs, deployment environment, or measured failure examples were provided, so the frequency and exact customer impact of each code-level risk cannot be quantified.
- The repository contains `graphify-8`, a separate graph-analysis tool source tree. Its own `AGENTS.md` applies to that subtree; the OCR runtime audit does not treat it as part of the deployed application.
- No tests or live provider calls were run in this read-only audit phase.
