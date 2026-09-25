# OCR Correctness Fixes

## 1. OCR Issues Fixed

- Removed automatic Arabic text substitution from OCR engines and API/Gradio response paths. Raw engine transcription is now carried on each `TextBlock` (`raw_text`) while downstream layout/extraction consumes the same unmodified text.
- Corrected preprocessing branches that applied bilateral smoothing to sharp images and sharpening to blurred images. Clean high-contrast scans now retain their grayscale pixels without denoise, threshold, or sharpening; adaptive illumination/contrast work remains conditional.
- Avoided gratuitous upscaling of narrow/cropped content by scaling only images whose longest side is below 900 px. Existing maximum-size downscaling remains.
- Added explicit resize transform metadata. Exact resize-only detection boxes are mapped to source-image dimensions; when perspective/deskew changes geometry, boxes are retained in the transformed frame and that fact is reported rather than pretending the inverse transform is exact.
- Kept the conditional second OCR pass but stopped merging blocks from different coordinate frames. The complete result with the higher existing quality score wins.
- Improved Arabic-Indic and Persian digit treatment in OCR quality scoring and validation. Dates, Egyptian IDs, and generic date/amount parsing normalize Unicode decimal digits for validation/extraction without changing OCR source text.
- Enforced bounded upload reads, unified detected signature with the configured MIME allowlist, and rejected declared/detected MIME mismatches. TIFF/BMP signatures alone no longer imply they are supported.
- Added input/detection validation to EasyOCR and response/coordinate validation to Mistral parsing. Empty input and malformed detections are rejected or skipped rather than causing confusing downstream values.
- Mistral Markdown-only fallback no longer invents full-width line bounding boxes; it preserves the full text and line breaks in one block with empty/zero geometry because the provider response has no spatial evidence.
- Removed creation of an Otsu-thresholded `enhanced` image variant that no runtime path OCRed or consumed.
- Increased Mistral JPEG encoding quality to 98 to reduce avoidable damage to small text and Arabic dots.
- Mapped generic provider `RuntimeError` failures to a structured 503 response without returning provider exception text to the client.

## 2. Root Cause of Each Issue

| Issue | Root cause |
|---|---|
| Arabic names/header text silently changed | Heuristic patterns in `ArabicOCRCorrector` rewrote source transcription inside engines and again in API/UI processing. |
| Sharp input was smoothed; blurry input was sharpened | Preprocessor used high Laplacian variance as a denoise trigger and treated sharpening as a blur remedy. |
| Small crops enlarged aggressively | Upscale branch used minimum side `<750` even when the long edge was much larger. |
| OCR boxes could be reported in the wrong frame | Resize/geometry transforms were not tracked when mapping model coordinates into response layout. |
| Retry merge could mix coordinate systems | Selector appended non-overlapping boxes from OCR runs on differently scaled images. |
| Arabic-script numbers scored/validated inconsistently | Quality scoring and several extractors/validators did not consistently normalize Unicode decimal digits. |
| Upload size and file type inconsistencies | Actual size was checked after whole-file read; MIME allowlist, signatures, and decoder acceptance differed. |
| Malformed engine results could fail or poison confidence | EasyOCR tuple/box/confidence values and Mistral pages/blocks/coordinates were assumed valid. |
| Some remote OCR degradation | Mistral image conversion used OpenCV’s default JPEG quality. |
| Provider error became generic 500 | Mistral exceptions were wrapped as `RuntimeError` without a structured provider handler. |

## 3. Files Changed

- `app/api/v1/routers/ocr.py`
- `app/app.py` (Gradio entry point)
- `app/core/exception_handlers.py`
- `app/domain/schemas/core.py`
- `app/infrastructure/ocr/easyocr_engine.py`
- `app/infrastructure/ocr/mistral_engine.py`
- `app/services/extraction/generic.py`
- `app/services/extraction/id_card.py`
- `app/services/extraction/validation.py`
- `app/services/image_processing/loader.py`
- `app/services/image_processing/preprocessor.py`
- `app/services/image_processing/quality.py`
- `app/services/image_processing/validator.py`
- `app/services/ocr/evaluator.py`
- `tests/test_extraction.py`
- `tests/test_ocr_optimization.py`
- `tests/test_preprocessing_pipeline.py`
- `tests/test_production_hardening.py`

## 4. Logic Changed

- OCR engine outputs are no longer canonicalized with Arabic regex rules. `TextBlock.raw_text` is populated from the exact engine string; `text` remains that source transcription through reading order, layout assembly, API output, and Gradio output.
- Preprocessing still applies perspective correction/deskew when existing geometry functions detect those conditions, and still applies illumination correction/CLAHE under low-quality conditions. It no longer smooths based only on a sharpness score or sharpens blur. Orientation is not guessed from aspect ratio because that cannot reliably distinguish portrait documents from 90°/270° rotations; EXIF transpose remains the reliable existing orientation mechanism.
- Scale-only transformations carry source/processed dimensions and have box coordinates scaled back. Geometric warps are explicitly flagged in quality warnings; without an inverse transform, the service retains transformed-frame coordinates instead of fabricating original-frame boxes.
- The API still performs a second OCR pass only for empty/low-score primary results. It compares whole-pass scores and returns one complete pass; it does not create a third call or add LLM/vision prompting.
- File reads stop at the configured byte limit plus one byte before decoding. Actual magic bytes must be in the configured allowlist and, when supplied, agree with the declared MIME type.
- EasyOCR malformed detections are skipped with bounded diagnostic logging. Mistral malformed page/block/coordinate data returns a controlled provider failure or skips the bad block.
- Validation-only Unicode digit conversion is centralized in `normalize_unicode_digits`; source OCR text is not rewritten.

## 5. Why the Fix Should Improve Accuracy

- Preserving exact model output prevents heuristic corrections from inventing or changing names, IDs, dates, or other text. Unreadable content remains uncertain/incorrectly recognized as the engine produced it rather than being “repaired” into a plausible but unsupported answer.
- Avoiding unconditional smoothing/sharpening reduces damage to Arabic dots, fine strokes, and small digits. Low-contrast/uneven-light adaptations remain conditional, preserving clean input.
- Avoiding large upscales of crop-like inputs and recording transform dimensions reduces interpolation artifacts and makes returned geometry more honest.
- Choosing one OCR pass avoids mixing incompatible box frames while retaining the original conditional retry policy and call budget.
- Unicode decimal normalization makes valid Arabic/Persian-script dates and Egyptian ID digits eligible for deterministic validation without changing the displayed OCR string.
- Bounded input reads and malformed-response checks prevent corrupted/unsupported input and invalid engine payloads from becoming silent downstream extraction errors.

## 6. Risks

- Removing Arabic canonical corrections can reduce recovery for documents where EasyOCR severely mangles known Egyptian official headers or names. This is intentional for correctness/hallucination control; any future correction should be opt-in, preserve raw text, and expose provenance.
- The existing composite OCR quality score remains heuristic and is not calibrated against labeled CER/WER. It can still miss fluent-looking errors or trigger an unnecessary second OCR call.
- For perspective-corrected or deskewed images, returned boxes are explicitly in the transformed image frame; exact mapping back to the upload still requires retaining/inverting the geometric transform.
- Simple Unicode decimal normalization does not solve OCR confusions between digits and letters, locale-specific date ambiguity, or separated/split digit groups beyond existing ID-card heuristics.
- Mistral SDK response coordinate units remain dependent on provider schema; validation prevents malformed values, but fixture-based integration verification is still needed.
- Preprocessing thresholds remain fixed heuristics; no representative real-world Arabic/English evaluation set was available to tune them.

## 7. Remaining OCR Limitations

- No cardinal-orientation classifier is added. EXIF orientation is corrected on decode, and skew correction remains active, but a pixel image rotated by 90° without EXIF metadata may remain sideways. A reliable orientation model or OCR-based orientation signal needs evaluation before use.
- No cropping/region-of-interest detection or table-specific OCR pass is added; tiny text and complex multi-column/table documents remain susceptible to detection/reading-order errors.
- No LLM/vision correction is used. Therefore there are no prompts or LLM hallucinations to guard against in the current runtime. If a future model is introduced, preserve immutable OCR evidence, require strict schema validation, and reject unsupported field guesses.
- The remaining specialized extractors may normalize/derive fields from OCR text. These structured values can still be wrong even when the raw OCR string is preserved; validation confidence is not equivalent to visual verification.
- The Gradio and FastAPI entry points still have different retry behavior (one pass vs conditional two-pass).

## Regression Tests Added

- Exact Arabic OCR text survives EasyOCR adapter output (`tests/test_ocr_optimization.py`).
- Clean sharp images take the no-smoothing path (`tests/test_preprocessing_pipeline.py`).
- Arabic-Indic ID/date digits validate deterministically (`tests/test_extraction.py`).
- Detected image signature must match the declared MIME type (`tests/test_production_hardening.py`).

## Verification

- `python -m compileall -q app tests` completed successfully.
- An AST syntax parse of all changed application and test Python files completed successfully.
- Pytest could not run: the active `python` environment has no `pytest` module. Runtime imports could not be checked because the active environment also lacks `cv2`. No claim is made that runtime tests passed.
