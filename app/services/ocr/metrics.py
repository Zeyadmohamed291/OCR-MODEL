"""Deterministic text and field metrics for labeled OCR evaluations."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    """Levenshtein distance using O(min(n, m)) memory."""
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for i, ref_item in enumerate(reference, start=1):
        current = [i]
        for j, hyp_item in enumerate(hypothesis, start=1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ref_item != hyp_item),
            ))
        previous = current
    return previous[-1]


def text_metrics(expected: str, actual: str) -> dict[str, Any]:
    """Return CER, WER and exact match without Unicode or punctuation rewriting."""
    expected = expected or ""
    actual = actual or ""
    char_errors = _edit_distance(list(expected), list(actual))
    ref_words = expected.split()
    hyp_words = actual.split()
    word_errors = _edit_distance(ref_words, hyp_words)
    return {
        "cer": char_errors / max(len(expected), 1),
        "wer": word_errors / max(len(ref_words), 1),
        "exact_match": expected == actual,
        "character_errors": char_errors,
        "word_errors": word_errors,
        "expected_characters": len(expected),
        "expected_words": len(ref_words),
    }


def field_metrics(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> dict[str, Any]:
    """Exact per-field scoring; missing or extra values do not count as correct."""
    keys = sorted(set(expected) | set(actual))
    if not keys:
        return {"accuracy": 1.0, "correct": 0, "total": 0, "fields": {}}
    fields = {
        key: {
            "expected": expected.get(key),
            "actual": actual.get(key),
            "correct": key in expected and key in actual and expected[key] == actual[key],
        }
        for key in keys
    }
    correct = sum(item["correct"] for item in fields.values())
    return {"accuracy": correct / len(keys), "correct": correct, "total": len(keys), "fields": fields}


def aggregate_text_metrics(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Micro-aggregate text metrics over rows with `expected_text`/`actual_text`."""
    rows = list(records)
    if not rows:
        return {"samples": 0, "cer": None, "wer": None, "exact_match_rate": None}
    char_errors = word_errors = chars = words = exact = 0
    for row in rows:
        metrics = text_metrics(str(row.get("expected_text") or ""), str(row.get("actual_text") or ""))
        char_errors += metrics["character_errors"]
        word_errors += metrics["word_errors"]
        chars += metrics["expected_characters"]
        words += metrics["expected_words"]
        exact += int(metrics["exact_match"])
    return {
        "samples": len(rows),
        "cer": char_errors / max(chars, 1),
        "wer": word_errors / max(words, 1),
        "exact_match_rate": exact / len(rows),
    }
