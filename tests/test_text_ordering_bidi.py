import pytest
from app.domain.schemas.core import TextBlock, BoundingBox
from app.services.language.language_detector import LanguageDetector
from app.services.layout.reading_order import organize_reading_order
from app.services.layout.layout_analyzer import LayoutAnalyzer
from app.services.layout.bidi_formatter import (
    normalize_logical_text, is_bidi_safe, build_structured_field, convert_dict_to_structured_fields
)

def make_box(x1, y1, x2, y2):
    return BoundingBox(
        points=[(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        normalized_points=[(x1/1000, y1/1000), (x2/1000, y1/1000), (x2/1000, y2/1000), (x1/1000, y2/1000)],
        width=x2 - x1,
        height=y2 - y1,
        area=(x2 - x1) * (y2 - y1)
    )

def test_direction_and_script_detection():
    """Verify fine-grained direction and script classification."""
    # Pure Arabic
    lang, conf, dist = LanguageDetector.detect("جمهورية مصر العربية")
    assert lang == "ar"
    assert LanguageDetector.detect_direction("جمهورية مصر العربية") == "rtl"
    assert LanguageDetector.detect_script("جمهورية مصر العربية") == "arabic"

    # Pure English
    lang, conf, dist = LanguageDetector.detect("Invoice Number")
    assert lang == "en"
    assert LanguageDetector.detect_direction("Invoice Number") == "ltr"
    assert LanguageDetector.detect_script("Invoice Number") == "latin"

    # Mixed Arabic + English code
    mixed_str = "رقم الفاتورة INV-1023"
    assert LanguageDetector.detect_direction(mixed_str) == "auto"
    assert LanguageDetector.detect_script(mixed_str) == "mixed"

    # Mixed Arabic + Currency + Numbers
    currency_str = "الإجمالي 1250.50 EGP"
    assert LanguageDetector.detect_direction(currency_str) == "auto"
    assert LanguageDetector.detect_script(currency_str) == "mixed"

    # Pure Numbers (National ID)
    id_str = "29501011234567"
    assert LanguageDetector.detect_direction(id_str) == "ltr"
    assert LanguageDetector.detect_script(id_str) == "numeric"

    # Date
    date_str = "2024-05-15"
    assert LanguageDetector.detect_direction(date_str) == "ltr"
    assert LanguageDetector.detect_script(date_str) == "numeric"

    # Phone number
    phone_str = "+201012345678"
    assert LanguageDetector.detect_direction(phone_str) == "ltr"
    assert LanguageDetector.detect_script(phone_str) == "numeric"

    # Email and URL
    email_str = "finance@company.com"
    url_str = "https://billing.example.org/pay"
    assert LanguageDetector.detect_direction(email_str) == "ltr"
    assert LanguageDetector.detect_direction(url_str) == "ltr"

def test_arabic_reading_order_with_english_number():
    """
    CRITICAL TEST: In an Arabic line:
    Arabic label is on the RIGHT (x=700..850)
    English prefix is at (x=450..520)
    Number is at (x=530..600)
    The reading order MUST be: [Label, Prefix, Number], i.e. 'رقم الفاتورة INV- 1023',
    NEVER inverting the number or English code!
    """
    blocks = [
        TextBlock(box=make_box(700, 100, 850, 130), text="رقم الفاتورة", confidence=0.95),
        TextBlock(box=make_box(450, 100, 520, 130), text="INV-", confidence=0.96),
        TextBlock(box=make_box(530, 100, 600, 130), text="1023", confidence=0.98),
    ]

    ordered = organize_reading_order(blocks)
    texts = [b.text for b in ordered]

    assert texts == ["رقم الفاتورة", "INV-", "1023"]
    assert ordered[0].direction == "rtl"
    assert ordered[1].direction == "ltr"
    assert ordered[2].direction == "ltr"
    assert ordered[0].reading_order == 1
    assert ordered[1].reading_order == 2
    assert ordered[2].reading_order == 3

def test_arabic_currency_reading_order():
    """
    Arabic label on right, numbers and currency symbol on left.
    Must maintain: [الإجمالي, 1250.50, EGP].
    """
    blocks = [
        TextBlock(box=make_box(750, 200, 880, 230), text="الإجمالي", confidence=0.94),
        TextBlock(box=make_box(550, 200, 640, 230), text="1250.50", confidence=0.97),
        TextBlock(box=make_box(650, 200, 710, 230), text="EGP", confidence=0.95),
    ]

    ordered = organize_reading_order(blocks)
    texts = [b.text for b in ordered]

    assert texts == ["الإجمالي", "1250.50", "EGP"]
    assert ordered[0].direction == "rtl"
    assert ordered[1].direction == "ltr"
    assert ordered[2].direction == "ltr"

def test_pure_arabic_right_to_left_sorting():
    """
    Pure Arabic line: First word on right, second word to its left.
    Must be ordered Right-to-Left: [أحمد, محمد, علي].
    """
    blocks = [
        TextBlock(box=make_box(700, 100, 780, 130), text="أحمد", confidence=0.95),
        TextBlock(box=make_box(580, 100, 660, 130), text="محمد", confidence=0.94),
        TextBlock(box=make_box(460, 100, 540, 130), text="علي", confidence=0.96),
    ]

    ordered = organize_reading_order(blocks)
    texts = [b.text for b in ordered]

    assert texts == ["أحمد", "محمد", "علي"]
    assert all(b.direction == "rtl" for b in ordered)

def test_pure_english_left_to_right_sorting():
    """
    Pure English line: Must be ordered Left-to-Right: [Invoice, Number, INV-1023].
    """
    blocks = [
        TextBlock(box=make_box(100, 100, 180, 130), text="Invoice", confidence=0.96),
        TextBlock(box=make_box(200, 100, 280, 130), text="Number", confidence=0.95),
        TextBlock(box=make_box(300, 100, 420, 130), text="INV-1023", confidence=0.98),
    ]

    ordered = organize_reading_order(blocks)
    texts = [b.text for b in ordered]

    assert texts == ["Invoice", "Number", "INV-1023"]
    assert all(b.direction == "ltr" for b in ordered)

def test_national_id_number_preservation():
    """
    National ID split into blocks: Must NEVER be reversed.
    """
    blocks = [
        TextBlock(box=make_box(100, 100, 220, 130), text="29501", confidence=0.99),
        TextBlock(box=make_box(230, 100, 320, 130), text="0112", confidence=0.98),
        TextBlock(box=make_box(330, 100, 470, 130), text="34567", confidence=0.99),
    ]

    ordered = organize_reading_order(blocks)
    full_id = "".join(b.text for b in ordered)

    assert full_id == "29501011234567"
    assert all(b.direction == "ltr" for b in ordered)

def test_no_string_reversal_guarantee():
    """
    Verify that normalize_logical_text strictly preserves logical character sequence
    and never reverses characters or words.
    """
    test_cases = [
        "رقم الفاتورة INV-1023",
        "Invoice Number INV-1023",
        "الإجمالي 1250.50 EGP",
        "اسم العميل: أحمد محمد",
        "29501011234567",
        "+201012345678",
        "info@deepmind.com",
        "https://antigravity.ai"
    ]

    for tc in test_cases:
        norm = normalize_logical_text(tc)
        assert norm == tc
        assert is_bidi_safe(norm) is True

def test_structured_fields_generation():
    """Verify structured fields preserve logical values and direction metadata."""
    sample_fields = {
        "invoice_number": "INV-2024-0981",
        "total": "11400.00",
        "currency": "EGP",
        "seller": "شركة الحلول الذكية",
        "customer_name": "أحمد محمد",
        "mixed_item": "رقم الفاتورة INV-1023",
        "emails": ["sales@solutions.com", "billing@solutions.com"],
        "phones": ["+201012345678"],
        "key_values": {
            "اسم العميل": "أحمد محمد",
            "رقم الفاتورة": "INV-1023"
        }
    }

    structured = convert_dict_to_structured_fields(sample_fields, confidence=0.95)
    assert len(structured) >= 8

    # Find customer name
    seller_field = next(f for f in structured if f.label == "Seller")
    assert seller_field.value == "شركة الحلول الذكية"
    assert seller_field.direction == "rtl"
    assert seller_field.language == "ar"

    # Find invoice number
    inv_field = next(f for f in structured if f.label == "Invoice Number")
    assert inv_field.value == "INV-2024-0981"
    assert inv_field.direction == "ltr"

    # Find mixed key value
    kv_inv = next(f for f in structured if f.label == "رقم الفاتورة")
    assert kv_inv.value == "INV-1023"
    assert kv_inv.direction == "ltr"

def test_layout_analyzer_direction_and_tables():
    """Verify LayoutAnalyzer populates direction on lines, blocks, and tables."""
    blocks = [
        # Line 1: Header
        TextBlock(box=make_box(700, 50, 850, 90), text="فاتورة ضريبية", confidence=0.97),
        # Line 2: Table Header
        TextBlock(box=make_box(600, 150, 750, 180), text="الوصف  الكمية  السعر", confidence=0.96),
        # Line 3: Table Row
        TextBlock(box=make_box(600, 190, 750, 220), text="خدمات صيانة  1  500.00", confidence=0.95),
    ]

    ordered = organize_reading_order(blocks)
    layout, sections, tables = LayoutAnalyzer.analyze(ordered)

    assert len(layout.lines) == 3
    assert layout.lines[0].direction == "rtl"
    assert layout.lines[0].raw_text is not None
    assert layout.lines[0].normalized_text is not None
    assert layout.lines[0].bbox is not None

    assert len(tables) == 1
    table = tables[0]
    assert table.direction == "rtl"
    assert len(table.structured_headers) > 0
    assert len(table.structured_rows) > 0
    assert table.structured_headers[0].direction == "rtl"

def test_viewer_endpoint():
    """Verify that GET /viewer endpoint serves the Bidi-safe HTML dashboard."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/viewer")
    assert response.status_code == 200
    assert "dir=\"auto\"" in response.text
    assert "Document Intelligence" in response.text
    assert "Bidi" in response.text
