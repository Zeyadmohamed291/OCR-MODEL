"""Evaluate OCR outputs against a JSONL ground-truth manifest.

Manifest rows: {"id": str, "expected_text": str, "actual_text": str,
                "expected_fields": {..}, "actual_fields": {..}}
Use `--outputs` to score an already-generated JSONL file. Without outputs,
the manifest itself must include actual_text/actual_fields from a prior run.
"""

import argparse
import json
from pathlib import Path

from app.services.ocr.metrics import aggregate_text_metrics, field_metrics, text_metrics


def evaluate(rows):
    results = []
    field_scores = []
    for row in rows:
        text = text_metrics(row.get("expected_text", ""), row.get("actual_text", ""))
        expected_fields = row.get("expected_fields", {})
        actual_fields = row.get("actual_fields", {})
        fields = field_metrics(expected_fields, actual_fields) if expected_fields else None
        results.append({"id": row.get("id"), "text": text, "fields": fields})
        if fields is not None:
            field_scores.append(fields)
    return {
        "samples": len(rows),
        "text": aggregate_text_metrics(rows),
        "field_accuracy": (
            sum(s["correct"] for s in field_scores) / max(sum(s["total"] for s in field_scores), 1)
            if field_scores else None
        ),
        "field_count": sum(s["total"] for s in field_scores),
        "records": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, help="Write report JSON to this path")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = evaluate(rows)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
