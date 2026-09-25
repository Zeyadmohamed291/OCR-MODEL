# OCR Evaluation Report

**Evaluation date:** 2026-09-25  
**Scope:** Verify Phase 2 OCR fixes, inspect and run the existing suite, add regression coverage and reusable OCR metrics.  
**Result:** Accuracy improvement is **not established**. The test runtime lacks project dependencies and there is no labeled OCR image dataset.

## 1. Tests Run

| Command/check | Result |
|---|---|
| `python -m pytest -q` | **Blocked before collection:** `No module named pytest`. |
| Runtime import probe for FastAPI/OpenCV | **Blocked:** active Python 3.12.13 lacks `fastapi` and `cv2`. |
| `python -m compileall -q app tests scripts` | Passed (syntax compilation only). |
| AST parse of new evaluator and regression tests | Passed. |
| Dependency-free evaluator check with one incorrect ID digit | Passed: CER nonzero, exact match false, exact ID field accuracy 0. |
| Image fixture inventory in `tests/` | No PNG/JPEG/WebP/TIFF OCR image fixtures found. |

The test suite was not collected, so the pytest counts are **0 passed, 0 failed, 0 skipped, 0 broken / 111 not run**. This is an environment block, not evidence that the tests pass. The current test tree contains 111 test functions by AST source count. No individual test can honestly be classified as passing, failing, skipped, or broken until pytest collection runs.

## 2. Tests Added

- `tests/test_ocr_metrics.py` adds 4 tests for CER/WER/exact match, Unicode text, strict structured-field matching, and micro-aggregation.
- `tests/test_phase2_regressions.py` adds 5 tests for empty OCR input, malformed EasyOCR detections and confidence, Arabic-Indic ID/date validation, MIME/signature rejection, and preservation of Mistral Markdown line breaks when spatial geometry is unavailable.
- Existing Phase 2 additions remain in `test_ocr_optimization.py`, `test_preprocessing_pipeline.py`, `test_extraction.py`, and `test_production_hardening.py`: raw Arabic text preservation, clean-image no-smoothing, Unicode digit validation, and MIME mismatch rejection.
- `OCR_EVALUATION_DATASET.md` documents how to add independently reviewed labeled samples.

These tests are regression-oriented and assert specific behavior. They are **not counted as passed** because the test runner and dependencies are unavailable here.

## 3. Passing Tests

- **Pytest tests:** None confirmed; test collection did not start.
- **Non-pytest checks:** The metrics evaluator’s direct ID mismatch/field accuracy check passed; Python compilation and AST syntax checks passed. These checks do not exercise OpenCV, EasyOCR, FastAPI, upload decoding, or OCR output.

## 4. Failing Tests

- **Confirmed pytest failures:** None observed because pytest could not collect or execute tests.
- **Known failure/blocker:** Test command fails immediately due to missing pytest; runtime imports separately fail due to missing FastAPI/OpenCV.
- **Unverified risks:** Phase 2 introduced behavior changes that may affect assertions or runtime paths. They remain unverified, not “passing.”

## 5. OCR Metrics

No production OCR result was generated during this evaluation. There is no ground-truth image/transcription dataset in the project test tree. Therefore the following are **not measured**:

| Metric | Result |
|---|---|
| OCR CER / WER / exact-match rate | Not measured; no labeled image samples and OCR runtime unavailable. |
| Structured field accuracy (IDs, dates, amounts, etc.) | Not measured on OCR output; only the metric implementation was checked with a synthetic one-digit mismatch. |
| Failed extraction rate | Not measured. |
| Retry rate / OCR call count | Not measured; no API/model runs or telemetry corpus. |
| Latency | Not measured. |

The evaluator is available at `scripts/evaluate_ocr.py`; it reports micro-aggregated CER/WER/exact-match and exact field accuracy from JSONL rows. It deliberately does not normalize punctuation, digits, case, or Arabic Unicode so changes remain visible. Field metrics count absent and unexpected fields as incorrect.

## 6. Before/After Comparison

| Comparison | Result |
|---|---|
| Before vs after CER/WER | Not available: no saved baseline OCR outputs or labeled samples. |
| Before vs after structured-field accuracy | Not available: no baseline predictions paired with ground truth. |
| Before vs after latency/calls | Not available: neither path was executed against the OCR engine. |
| Source-level behavior | Phase 2 removes automatic Arabic corrections, changes preprocessing branch conditions, and changes retry selection. These are code changes, not measured accuracy gains. |

No accuracy-improvement claim is made. The next valid comparison needs the same fixed images, ground truth, provider/model weights, and build-specific outputs from before and after Phase 2.

## 7. Remaining Failure Cases

- Runtime correctness for preprocessing and image decode is unverified without OpenCV/Pillow/FastAPI test dependencies.
- Real OCR quality for high-quality, low-resolution, blurred, noisy, skewed, low-contrast, cropped, and mixed Arabic/English documents is unmeasured.
- No cardinal-orientation classifier was added; pixel-rotated images without EXIF remain a known limitation.
- No provider timeout or API failure fixture was added/run; Mistral SDK behavior and malformed response handling need mocked SDK tests and installed-version verification.
- Invalid JSON is not a current OCR parser path: Mistral SDK returns typed response objects, and no JSON-generating LLM is used. A malformed provider response test is more relevant than arbitrary JSON parsing.
- Current retry score is heuristic and not calibrated against CER or field accuracy. Retry rate, model call count, and benefit remain unknown.
- Exact field output can still be wrong even when a format validator accepts it; only visual ground truth can verify IDs/names/dates.

## 8. Recommended Additional Test Samples

Build a secure, consented, independently transcribed corpus with stable IDs and source metadata. Include:

- Clean high-resolution Arabic, English, and mixed-script documents with printed and handwritten examples separated.
- Paired source scans and controlled variants for downsampling, blur, sensor noise, low contrast, skew, 90°/180°/270° rotation, shadows, JPEG compression, and realistic crops.
- Small Arabic dots/diacritics, thin strokes, punctuation, currency symbols, Latin identifiers embedded in RTL lines, and Arabic-Indic/Persian digits.
- ID/passport/invoice/date/email/phone samples with exact field ground truth; score ID/number/date exact accuracy separately from overall CER/WER.
- Tables and multi-column layouts with cell/row/reading-order annotations.
- Empty/corrupt/truncated images, oversized byte bodies, unsupported signatures, and MIME mismatches.
- Mocked Mistral fixtures for empty pages, malformed page lists, missing blocks, invalid coordinates, timeouts, 429/5xx, and API exceptions.
- Fixed baseline and post-fix runs recording engine/provider, model version, preprocessing variants, OCR call count, retry decision, latency, raw OCR text, and extracted fields.

Before accepting an accuracy change, report paired CER/WER and exact critical-field accuracy with sample counts and breakdowns by language, degradation, and document type. Review every critical-field error regardless of document-level text similarity.
