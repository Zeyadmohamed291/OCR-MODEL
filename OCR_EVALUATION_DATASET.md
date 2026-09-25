# OCR Evaluation Dataset Format

The repository currently has no labeled OCR image/expected-text corpus. Add one sample per JSONL record to a private or consented dataset, then record the actual output from the selected engine/version and preprocessing path.

Recommended record:

```json
{"id":"sample-001","image":"images/sample-001.png","language":"ar-en","document_type":"id_card","expected_text":"...","actual_text":"...","expected_fields":{"national_id":"12345678901234","birth_date":"1990-01-01"},"actual_fields":{"national_id":"12345678901234","birth_date":"1990-01-01"},"provider":"easy","build":"<git revision>","preprocessing":"adaptive-primary"}
```

Run `python scripts/evaluate_ocr.py manifest.jsonl --output report.json` from the repository root. The evaluator reports exact text match, character/word error rates, and exact structured-field accuracy. Keep expected values independently reviewed; do not use OCR output as ground truth. Preserve a stable sample ID and record engine/config/build for before/after comparisons.

For sensitive IDs and financial documents, keep the image set in approved secure storage and do not commit samples to the repository.
