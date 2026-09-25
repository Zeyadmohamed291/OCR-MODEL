import pytest
from app.domain.schemas.core import TextBlock, BoundingBox
from app.services.classification.classifier import UniversalDocumentClassifier
from app.services.layout.layout_analyzer import LayoutAnalyzer
from app.services.layout.reading_order import organize_reading_order
from app.services.extraction.registry import extractor_registry
from app.services.layout.bidi_formatter import convert_dict_to_structured_fields

def make_box(x1, y1, x2, y2):
    return BoundingBox(
        points=[(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        normalized_points=[(x1/1000, y1/1000), (x2/1000, y1/1000), (x2/1000, y2/1000), (x1/1000, y2/1000)],
        width=x2 - x1,
        height=y2 - y1,
        area=(x2 - x1) * (y2 - y1)
    )

# -------------------------------------------------------------
# 1. Multi-Signal Classification Tests across 14+ Document Types
# -------------------------------------------------------------

def test_classify_all_supported_document_types():
    """Verify classification accuracy across all 14+ required document types."""
    samples = {
        "invoice": "فاتورة ضريبية Tax Invoice\nرقم الفاتورة: INV-9901\nالإجمالي: 5000.00 EGP\nضريبة القيمة المضافة: 700.00",
        "receipt": "كاشير Cashier #4\nفاتورة مبسطة\nطلب رقم 145\nنقدى Cash 150.00\nالباقي 50.00",
        "contract": "عقد اتفاق وتوريد\nالطرف الأول: شركة الأهرام\nالطرف الثاني: مؤسسة النور\nالبند الأول: موضوع العقد\nتوقيع الطرفين",
        "cv": "Ahmed Hassan\nSoftware Engineer\nEmail: ahmed@example.com\nLinkedIn: linkedin.com/in/ahmed\nEducation: Faculty of Engineering\nExperience: Senior Developer\nSkills: Python, Docker, FastApi",
        "passport": "PASSPORT جواز سفر\nType P Country EGY\nP<EGYHASSAN<<AHMED<<<<<<<<<<<<<<<<<<<<<<<\nA123456784EGY9001015M3001015<<<<<<<<<<<02",
        "id_card": "جمهورية مصر العربية\nبطاقة تحقيق الشخصية\nمحمود إبراهيم أحمد\n29501011234567\nالجيزة",
        "driver_license": "جمهورية مصر العربية\nوزارة الداخلية - مرور الجيزة\nرخصة قيادة خاصة\nفصيلة الدم: O+\nدرجة ثالثة",
        "bank_document": "CIB Bank كشف حساب بنكي\nAccount Statement\nIBAN: EG380002000100023458912001\nSWIFT: CIBEEGCX\nBalance: 154000.00",
        "form": "نموذج تسجيل بيانات موظف\nApplication Form\nالاسم: _________\nتاريخ الميلاد: _________\nالتوقيع: _________",
        "report": "Annual Technical Report تقرير فني سنوي\nPrepared By: Operations Team\nExecutive Summary\nFindings and Recommendations",
        "certificate": "شهادة تقدير Certificate of Appreciation\nThis is hereby certified that Ahmed Ali has completed the advanced track\nDate: 2024-05-15",
        "letter": "السيد / مدير عام المشتريات المحترم\nتحية طيبة وبعد ،،\nالموضوع: توريد خوادم جديدة\nوتفضلوا بقبول فائق الاحترام والتقدير\nSincerely,",
        "screenshot": "https://dashboard.cloud.google.com/billing\nSettings | View | Edit\n12:45 PM | Battery 85% | WiFi Connected",
        "table": "Item | Quantity | Unit Price | Total\nWidget A | 5 | 100.00 | 500.00\nWidget B | 2 | 250.00 | 500.00\nTotal | 7 | 350.00 | 1000.00"
    }

    for expected_type, sample_text in samples.items():
        doc_type, conf = UniversalDocumentClassifier.classify(sample_text)
        assert doc_type == expected_type, f"Expected '{expected_type}', but got '{doc_type}' for text:\n{sample_text}"
        assert conf >= 0.60

def test_classify_with_signals_internal_reporting():
    """Verify that classify_with_signals returns rich signal provenance."""
    sample = "فاتورة ضريبية Tax Invoice\nرقم الفاتورة: INV-2024\nالمجموع: 1200 EGP"
    res = UniversalDocumentClassifier.classify_with_signals(sample)

    assert res["category"] == "invoice"
    assert res["confidence"] >= 0.70
    assert len(res["signals"]) > 0
    assert any("invoice" in s for s in res["signals"])

def test_unknown_and_sparse_document_classification():
    """Verify that sparse or unrecognizable documents gracefully degrade without errors."""
    # Sparse text (<= 4 words)
    cat, conf = UniversalDocumentClassifier.classify("Hello world photo")
    assert cat == "image_with_text"

    # Random text with no domain keywords
    cat, conf = UniversalDocumentClassifier.classify("The quick brown fox jumps over the lazy dog multiple times across the green field.")
    assert cat in ("generic_document", "unknown")
    assert conf <= 0.60

    # Empty text
    cat, conf = UniversalDocumentClassifier.classify("")
    assert cat == "unknown"
    assert conf == 0.0

# -------------------------------------------------------------
# 2. Rich Layout Structure Tests (Title, Header, Footer, Columns, Signatures, Sections)
# -------------------------------------------------------------

def test_rich_layout_analysis():
    """Verify detection of title, header, footer, columns, signatures, and structured sections."""
    blocks = [
        # Running Header (top 5% of page)
        TextBlock(box=make_box(100, 20, 300, 40), text="Acme Corporation - Confidential", confidence=0.95),
        
        # Document Title (large font in top 20%)
        TextBlock(box=make_box(300, 70, 700, 120), text="عقد تقديم خدمات برمجية", confidence=0.98),
        
        # Section 1 Heading
        TextBlock(box=make_box(100, 160, 400, 195), text="البند الأول: موضوع العقد", confidence=0.97),
        # Section 1 Body
        TextBlock(box=make_box(100, 210, 850, 250), text="يلتزم الطرف الثاني بتصميم وبرمجة نظام إدارة الوثائق بالكامل.", confidence=0.96),
        
        # Section 2 Heading
        TextBlock(box=make_box(100, 300, 400, 335), text="البند الثاني: القيمة والمدفوعات", confidence=0.97),
        # Section 2 Body
        TextBlock(box=make_box(100, 350, 850, 390), text="تبلغ قيمة هذا العقد مائة ألف جنيه مصري يتم سدادها على دفعات.", confidence=0.95),
        
        # Signatures line
        TextBlock(box=make_box(100, 800, 800, 840), text="توقيع الطرف الأول: شركة التقنية      توقيع الطرف الثاني: المطور", confidence=0.96),
        
        # Running Footer (bottom 5% of page)
        TextBlock(box=make_box(450, 940, 550, 965), text="صفحة 1 من 3", confidence=0.99)
    ]

    ordered = organize_reading_order(blocks)
    layout, sections, tables = LayoutAnalyzer.analyze(ordered, image_width=1000, image_height=1000)

    # 1. Title
    assert layout.title == "عقد تقديم خدمات برمجية"
    
    # 2. Running Header and Footer
    assert layout.header == "Acme Corporation - Confidential"
    assert layout.footer == "صفحة 1 من 3"
    
    # 3. Signatures
    assert layout.has_signatures is True
    
    # 4. Sections with Structured Content and Bounding Box
    assert len(sections) == 2
    sec1 = sections[0]
    assert "البند الأول" in sec1.title
    assert "يلتزم الطرف الثاني" in sec1.content
    assert sec1.bbox is not None
    assert sec1.confidence >= 0.90

    sec2 = sections[1]
    assert "البند الثاني" in sec2.title
    assert "تبلغ قيمة هذا العقد" in sec2.content
    assert sec2.bbox is not None

def test_multi_column_layout_detection():
    """Verify column detection when blocks are horizontally partitioned."""
    blocks = [
        # Left column
        TextBlock(box=make_box(50, 100, 400, 130), text="Left column line 1", confidence=0.95),
        TextBlock(box=make_box(50, 150, 400, 180), text="Left column line 2", confidence=0.95),
        TextBlock(box=make_box(50, 200, 400, 230), text="Left column line 3", confidence=0.95),
        # Right column
        TextBlock(box=make_box(550, 100, 900, 130), text="Right column line 1", confidence=0.95),
        TextBlock(box=make_box(550, 150, 900, 180), text="Right column line 2", confidence=0.95),
        TextBlock(box=make_box(550, 200, 900, 230), text="Right column line 3", confidence=0.95),
    ]

    ordered = organize_reading_order(blocks)
    layout, _, _ = LayoutAnalyzer.analyze(ordered, image_width=1000, image_height=1000)
    assert layout.columns == 2

# -------------------------------------------------------------
# 3. Semantic Field Extraction & Spatial Grounding Tests
# -------------------------------------------------------------

def test_invoice_extraction_with_table_items_and_bboxes():
    """Verify invoice extraction extracts table items and attaches source bounding boxes."""
    blocks = [
        TextBlock(box=make_box(100, 50, 400, 90), text="Tax Invoice فاتورة ضريبية", confidence=0.98),
        TextBlock(box=make_box(100, 110, 450, 140), text="Invoice #: INV-2024-8877", confidence=0.97),
        TextBlock(box=make_box(100, 150, 400, 180), text="Date: 2024-06-01", confidence=0.96),
        TextBlock(box=make_box(100, 190, 400, 220), text="Seller: Future Tech Ltd", confidence=0.95),
        # Table Header
        TextBlock(box=make_box(100, 300, 700, 330), text="Description  Qty  Total", confidence=0.96),
        # Table Row 1
        TextBlock(box=make_box(100, 340, 700, 370), text="Web Development  1  10000.00", confidence=0.95),
        # Table Row 2
        TextBlock(box=make_box(100, 380, 700, 410), text="Cloud Hosting  12  2400.00", confidence=0.95),
        # Totals
        TextBlock(box=make_box(500, 500, 850, 530), text="Subtotal: 12400.00", confidence=0.98),
        TextBlock(box=make_box(500, 540, 850, 570), text="Tax: 1736.00", confidence=0.98),
        TextBlock(box=make_box(500, 580, 850, 610), text="Total: 14136.00 EGP", confidence=0.99),
    ]

    ordered = organize_reading_order(blocks)
    layout, _, tables = LayoutAnalyzer.analyze(ordered, image_width=1000, image_height=1000)
    layout.tables = tables

    full_text = "\n".join(l.text for l in layout.lines)
    extracted = extractor_registry.extract("invoice", full_text, layout=layout)

    # 1. Verify semantic extraction
    assert extracted["invoice_number"] == "INV-2024-8877"
    assert extracted["total"] == "14136.00"
    assert extracted["currency"] == "EGP"
    assert "Future Tech" in extracted["seller"]
    assert len(extracted.get("items", [])) >= 2
    assert extracted["items"][0]["description"] == "Web Development"

    # 2. Verify StructuredField conversion attaches source_bbox
    structured = convert_dict_to_structured_fields(extracted, confidence=0.96, layout=layout)
    inv_field = next(f for f in structured if f.field_name == "invoice_number")
    assert inv_field.value == "INV-2024-8877"
    assert inv_field.source_bbox is not None
    assert len(inv_field.source_bbox) == 4  # 4-point polygon

    tot_field = next(f for f in structured if f.field_name == "total")
    assert tot_field.value == "14136.00"
    assert tot_field.source_bbox is not None

def test_unknown_document_preserves_full_utility():
    """Verify that an unknown document still returns text, layout, lines, and detected entities."""
    blocks = [
        TextBlock(box=make_box(100, 50, 600, 80), text="Note from meeting on 2024-07-15", confidence=0.95),
        TextBlock(box=make_box(100, 100, 600, 130), text="Contact support at help@platform.io", confidence=0.96),
        TextBlock(box=make_box(100, 150, 600, 180), text="Call manager at +201099887766", confidence=0.97),
        TextBlock(box=make_box(100, 200, 600, 230), text="Estimated budget is 2500.00 USD", confidence=0.98),
    ]

    ordered = organize_reading_order(blocks)
    layout, sections, tables = LayoutAnalyzer.analyze(ordered)

    full_text = "\n".join(l.text for l in layout.lines)
    doc_type, conf = UniversalDocumentClassifier.classify(full_text, layout=layout)
    assert doc_type in ("generic_document", "unknown")

    # Extract generic entities
    extracted = extractor_registry.extract(doc_type, full_text, layout=layout)
    assert any("help@platform.io" in e for e in extracted.get("emails", []))
    assert any("201099887766" in p for p in extracted.get("phones", []))
    assert any("2024-07-15" in d for d in extracted.get("dates", []))
    assert any("2500.00" in a for a in extracted.get("amounts", []))
