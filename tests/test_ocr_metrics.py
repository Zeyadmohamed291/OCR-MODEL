from app.services.ocr.metrics import aggregate_text_metrics, field_metrics, text_metrics


def test_text_metrics_detect_single_digit_error_even_with_high_similarity():
    result = text_metrics("Expected ID: 12345678", "Expected ID: 12345676")
    assert result["exact_match"] is False
    assert result["character_errors"] == 1
    assert result["cer"] > 0
    assert result["wer"] > 0


def test_text_metrics_empty_values_and_unicode_arabic():
    assert text_metrics("", "")["exact_match"] is True
    assert text_metrics("مرحبا", "مرحباً")["exact_match"] is False


def test_field_metrics_are_exact_and_count_missing_fields():
    result = field_metrics({"id": "12345678", "date": "2024-05-15"}, {"id": "12345676"})
    assert result["correct"] == 0
    assert result["total"] == 2
    assert result["fields"]["id"]["correct"] is False
    assert result["fields"]["date"]["actual"] is None


def test_aggregate_text_metrics_micro_aggregate():
    result = aggregate_text_metrics([
        {"expected_text": "cat", "actual_text": "cat"},
        {"expected_text": "dog", "actual_text": "dig"},
    ])
    assert result["samples"] == 2
    assert result["cer"] == 1 / 6
    assert result["exact_match_rate"] == 0.5
