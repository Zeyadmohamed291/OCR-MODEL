# Workflow and Model-Call Optimization Report

**Scope:** Optimize real runtime work without reducing OCR correctness or inventing a graph. Reviewed `AUDIT_REPORT.md`, `OCR_FIXES.md`, and `OCR_EVALUATION.md` before changes.

## Executive Finding

The deployed application has **no runtime graph framework or LLM prompt workflow**. There is no LangGraph/StateGraph, graph state, chat history, system prompt, completion call, token counter, or LLM-generated structured output in `app/`. The graph-like runtime is a sequential OCR/document pipeline with one bounded conditional second OCR inference. `graphify-out` is static codebase-analysis data and is not the execution graph.

Therefore current LLM prompt-token usage is **zero by source inspection**. Mistral OCR is an external OCR API call that sends an encoded image; it is not a token-prompted text completion in this code. EasyOCR is local inference. Cost/token counts reported by providers are unavailable in the repository and were not guessed.

One unused preprocessing output was safely removed: the Otsu threshold variant was built under quality conditions but never sent to OCR or returned. OCR images, routing thresholds, OCR call count, and downstream extraction are unchanged.

## 1. Previous Graph Flow

There was no explicit graph to preserve or optimize. The previous runtime flow was:

```text
FastAPI request
  → provider resolution / cached engine
  → bounded image read, signature and decode checks
  → quality analysis
  → adaptive preprocessing (geometry, scale, gray, optional illumination/contrast)
  → OCR primary image
  → deterministic composite-quality score
       ├─ empty or score < 0.50 → OCR geometry-corrected original once, choose higher-scoring full pass
       └─ otherwise → keep primary
  → reading order and layout
  → deterministic language and document classification
  → generic regex extraction + one type-specific extractor
  → structured response
```

Gradio follows a separate path with one OCR pass, without the FastAPI retry. No loops are present. The retry bound is two OCR invocations maximum per API request and one per Gradio request.

## 2. Updated Graph Flow

The executed model path and decisions remain the same. Adaptive preprocessing now returns only images consumed downstream:

```text
FastAPI request
  → provider resolution / cached engine
  → bounded image read, signature and decode checks
  → quality analysis
  → adaptive preprocessing → primary + original + compact transform metadata
  → OCR primary image
  → deterministic quality score
       ├─ empty or score < 0.50 → OCR original once, choose higher-scoring full pass
       └─ otherwise → keep primary
  → reading order and layout
  → deterministic language and document classification
  → generic regex extraction + one type-specific extractor
  → structured response
```

The unused `enhanced` thresholded image allocation was removed. It was never an OCR candidate, so no route, model call, or quality decision changed.

## 3. Nodes Changed

Only the preprocessing output construction changed:

- **Changed:** `AdaptivePreprocessor.preprocess_adaptive` no longer performs an extra Otsu threshold and allocates a third image for `variants["enhanced"]` on shadow/very-low-contrast inputs.
- **Unchanged:** primary preprocessing, geometry-corrected original fallback, OCR provider configuration, quality score, retry cutoff, result selection, reading order, classification, extraction, and response formatting.
- **Regression coverage added:** `test_preprocessor_does_not_build_unused_threshold_variant` asserts the output variants contain primary and original but no unconsumed enhanced image.
- **Final verification regression:** Mistral Markdown-only output is represented as one geometry-free text block so the layout ordering step cannot collapse separate source lines into spaces.

## 4. Runtime Node Inventory

There are no LLM graph nodes. This table inventories the actual equivalent stages, their runtime state, model calls, routing, and any waste.

| Node / function | Input | Output | State used | Model call | Prompt | Routing logic | Purpose | Token usage / waste |
|---|---|---|---|---|---|---|---|---|
| Provider selection — `get_ocr_engine_by_name` | Provider query/config | Cached engine object | Process-local `_engines` registry | None at selection; first use initializes local weights or Mistral client | None | `mistral` plus configured key selects Mistral; other paths select EasyOCR | Resolve engine and reuse initialization | Zero LLM tokens; engine memoization already avoids reloads |
| Upload validation/decode — `load_image` | Multipart upload and settings | BGR image + metadata or typed error | Request-local bytes/chunks | None | None | Bounded bytes, allowlisted signature, declared MIME agreement, decoder and pixel limits | Reject invalid inputs before inference | Zero tokens; unavoidable input processing |
| Quality analysis — `analyze_image_quality` | Decoded image | Blur/brightness/contrast/skew/resolution metrics | Request-local image | None | None | Metrics guide adaptive transforms; no model route from quality alone | Assess input condition | Zero tokens; one pass over image data |
| Adaptive preprocessing — `preprocess_adaptive` | Image and quality metrics | Primary image, geometry-corrected original, transform metadata | Request-local image/arrays | None | None | Resize, illumination, contrast and geometry operations are conditional | Prepare default image and one fallback image | Zero tokens. Removed unused Otsu variant/array; primary and fallback remain |
| OCR primary — `extract_text` → engine `process_image` | Primary image | `OCRResult` blocks, confidence and provider raw response | Request-local engine/result | One local EasyOCR inference **or** one Mistral OCR API call | No text prompt; Mistral sends image data URI and model identifier | Always runs | Zero prompt tokens. One required OCR call |
| OCR quality evaluation — `evaluate_detection_quality` | OCR blocks/text/confidences | Composite score/signals | Pass A result only | None | None | Score `<0.50` or no blocks enables one fallback OCR call | Cheap deterministic OCR-result gate | Zero tokens. No full conversation/context exists |
| Conditional fallback — second `process_image` call | Geometry-corrected original image | Alternate complete result | Pass A and B result live for comparison | Zero or one additional OCR inference/API call | No text prompt | Runs only for empty/low-score primary; selects higher score as a full result | Recovery opportunity without unconditional expensive routing | Bounded maximum of two OCR calls/API calls per FastAPI request; no retry loop |
| Reading order/layout — `organize_reading_order`, `LayoutAnalyzer.analyze` | Selected OCR blocks + image dimensions | Ordered blocks, lines, layout, sections, tables | Selected result | None | None | Deterministic geometry/text rules | Convert detections into document structure | Zero tokens; geometry and full text are local Python objects |
| Language/classification — `LanguageDetector`, `UniversalDocumentClassifier` | Combined text, layout, metadata | Language and document type/confidence | Combined text and layout | None | None | Rules/signals select downstream extractor | Choose extraction strategy | Zero tokens; no LLM escalation |
| Extraction — `ExtractorRegistry.extract` | Full combined text, layout, metadata and type | Generic fields plus one specialized extractor’s fields | Request-local extraction data | None | None | Generic always runs; one type-specific extractor runs if mapped | Extract/validate known fields deterministically | Zero tokens. Full text is passed because extractors may search arbitrary fields; no model context is sent |
| Response — `OCRResponse` assembly | Text/layout/fields/metadata/timings | JSON response | Request-local result and raw provider output | None | None | Optional Mistral Markdown is exposed as `formatted_text` | Return full OCR/document result | Zero tokens. Output size is API payload, not model context |

For every stage, the input/output/state above is actual source behavior. There is no “entire previous graph state” or conversation history being sent to a model.

## 5. Routing Improvements

- Preserved the conditional second pass at the existing `<0.50` score / empty result condition. No labeled OCR set exists to justify changing that threshold.
- Preserved the strict maximum of one fallback pass. There are no retry loops or unbounded escalation paths.
- Fallback selection compares complete pass scores and keeps one complete result. It does not merge incompatible coordinate frames.
- No “high confidence means finish before extraction” shortcut was added: extraction/classification outputs are part of the public response and are required even when OCR confidence is high.
- No stronger model escalation was added. There is no demonstrated accuracy/cost evidence that would justify a new provider call.

## 6. Token Optimizations

- No text LLM requests exist; prompt-token savings are not applicable. Source-inspected LLM prompt/token count before and after is **0 → 0**.
- No system prompt, document text, chat history, or verbose model response is duplicated in a completion call.
- Structured output is produced with Pydantic and deterministic extractors, not LLM JSON generation.
- The preprocessor no longer computes an unused Otsu image. This saves local image work/memory, not tokens.

## 7. Model-Call Reductions

- **Before vs after source path:** OCR call count is unchanged: FastAPI **1 primary + at most 1 conditional fallback**; Gradio **1**. The Otsu variant had no consumer, so it never caused an OCR call.
- **Measured calls:** Not measured. No OCR runtime dependencies or provider credentials are available in this environment.
- **Actual reduction delivered:** No OCR/API model calls were removed, because doing so without data could reduce recovery accuracy. One unused preprocessing operation/image allocation was removed.

## 8. Graph State Reductions

- No graph state existed, so graph state size is not applicable.
- Request-local processing still retains image variants and selected OCR result as needed. Mistral `raw_output` is used later to populate `formatted_text`; dropping it could alter the response and was not done.
- No OCR text/history is sent as repeated LLM context because the application has no LLM text-processing stage.

## 9. Caching Improvements

- Engine/model initialization is already cached per process (`_engines`; EasyOCR singleton). No change made.
- No cross-request image/OCR-result cache was introduced. A safe cache would need tenant/privacy boundaries, complete key material (image bytes, provider/model revision, preprocessing/config version), bounded memory/TTL, and invalidation. None exists here, and there is no measured duplicate-input rate to justify the risk.
- Preprocessing occurs once per request in each entry point. There was no repeated preprocessing stage inside the FastAPI pipeline to cache.

## 10. Retry Improvements

- Existing bound retained: maximum 2 API OCR calls and maximum 1 Gradio OCR call per request. No loops.
- Retry remains gated by empty or score `<0.50`; no threshold changed because OCR_EVALUATION reports no ground-truth metrics.
- The second result is compared once with the first and does not trigger another attempt. Failures surface through the existing provider error paths.
- Before/after retry rate is **not measured**.

## 11. Before/After Measurements

| Measurement | Before | After | Evidence / limitation |
|---|---:|---:|---|
| LLM completion calls | 0 by source inspection | 0 by source inspection | No completion client/dependency/call path in `app/` |
| Prompt tokens | 0 by source inspection | 0 by source inspection | No prompts/text-model calls |
| OCR inference/API calls | 1–2 FastAPI; 1 Gradio | Same | Routing source unchanged; no runtime call instrumentation available |
| OCR model-call reduction | — | 0 | No safe call removal justified |
| Runtime node count | No explicit graph | No explicit graph | Sequential pipeline unchanged |
| Unused Otsu image variants | 0 or 1 conditional extra variant | 0 | Source inspection: threshold operation and allocation removed |
| Latency / CPU time | Not measured | Not measured | `pytest`, FastAPI, OpenCV, EasyOCR, and Mistral runtime not available |
| Peak memory | Not measured | Not measured | No runtime profiling environment |
| OCR accuracy / field accuracy | Not measured | Not measured | No labeled images or baseline OCR outputs; OCR_EVALUATION.md documents this |

The only defensible before/after statement is structural: a branch that generated an unused thresholded image was removed. No milliseconds, tokens, call-rate, or OCR accuracy deltas are fabricated.

## 12. Verification

- Added a targeted test asserting the unused `enhanced` variant is absent.
- `python -m pytest -q` was rerun and remains blocked immediately: active Python has no `pytest` module. Earlier environment probing found no FastAPI/OpenCV imports either; therefore runtime regression tests cannot run in this environment.
- `python -m compileall -q app tests scripts` completed successfully.
- AST syntax parsing completed for all 80 Python source/test/script files.
- No OCR engine or external Mistral API request was executed.

## 13. Remaining Optimization Opportunities

1. Add per-request counters for provider calls, selected variant, retry decision, and node-equivalent stages; keep document text/image bytes out of telemetry.
2. Install the pinned project runtime in CI and profile preprocessing/model latency, peak memory, and concurrent requests.
3. Build the secure labeled corpus described in `OCR_EVALUATION.md`; only then calibrate the `<0.50` retry gate against field accuracy and incremental retry benefit.
4. Measure exact/hash duplicate rates before considering a privacy-scoped, bounded OCR result cache with model/config-aware keys.
5. Evaluate replacing synchronous Mistral calls with supported deadlines/async handling and bounded concurrency; this is reliability/latency work, not token reduction.
6. Profile retained Mistral raw response size. If it is material, preserve the exact `formatted_text` API behavior while storing only the needed Markdown rather than the full SDK object.
7. Keep deterministic validators/extractors for IDs, dates, amounts, and emails. Do not add LLM correction/extraction unless an evaluated case cannot be handled reliably without it.
