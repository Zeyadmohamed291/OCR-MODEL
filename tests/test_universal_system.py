import pytest
import numpy as np
from app.services.classification.classifier import UniversalDocumentClassifier
from app.services.language.language_detector import LanguageDetector
from app.services.image_processing.quality import analyze_image_quality
from app.services.layout.reading_order import organize_reading_order
from app.services.layout.layout_analyzer import LayoutAnalyzer
from app.services.extraction.registry import extractor_registry
from app.services.extraction.id_card import IDCardExtractor
from app.services.extraction.invoice import InvoiceExtractor
from app.services.extraction.receipt import ReceiptExtractor
from app.services.extraction.contract import ContractExtractor
from app.services.extraction.cv import CVExtractor
from app.services.extraction.passport import PassportExtractor
from app.services.extraction.driver_license import DriverLicenseExtractor
from app.services.extraction.bank_document import BankDocumentExtractor
from app.domain.schemas.core import TextBlock, BoundingBox
from app.domain.schemas.responses import OCRResponse

# ---------------------------------------------------------
# 1. Egyptian ID Card
# ---------------------------------------------------------
def test_egyptian_id_classification_and_extraction():
    text = "جمهورية مصر العربية\nبطاقة تحقيق الشخصية\n29501011234567\nأحمد محمود علي\nشارع التحرير الدقي الجيزة"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "id_card"
    assert conf > 0.7

    fields = extractor_registry.extract(doc_type, text)
    assert fields["national_id"] == "29501011234567"
    assert fields["birth_date"] == "1995-01-01"
    assert fields["governorate_code"] == "12"
    assert fields["gender"] == "Female"
    assert fields["name"] is not None

# ---------------------------------------------------------
# 2. Invoice Document
# ---------------------------------------------------------
def test_invoice_classification_and_extraction():
    text = """
    Tax Invoice
    فاتورة ضريبية
    Invoice #: INV-2024-0981
    Date: 2024-05-15
    Due Date: 2024-06-15
    Seller: Tech Solutions Cairo
    Bill To: Global Trade Co
    Subtotal: 10000.00
    VAT: 1400.00
    Total Amount: 11400.00 EGP
    """
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "invoice"

    fields = extractor_registry.extract(doc_type, text)
    assert fields["invoice_number"] == "INV-2024-0981"
    assert fields["invoice_date"] == "2024-05-15"
    assert fields["due_date"] == "2024-06-15"
    assert "Tech Solutions" in fields["seller"]
    assert "Global Trade" in fields["buyer"]
    assert fields["subtotal"] == "10000.00"
    assert fields["tax"] == "1400.00"
    assert fields["total"] == "11400.00"
    assert fields["currency"] == "EGP"

# ---------------------------------------------------------
# 3. Receipt Document
# ---------------------------------------------------------
def test_receipt_classification_and_extraction():
    text = """
    Starbucks Coffee
    Receipt # 98451
    Order # 42
    Date: 2024-08-20
    12:35 PM
    Cashier: Omar
    Latte Grande  65.00
    Total: 65.00 EGP
    Payment: Cash
    """
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "receipt"

    fields = extractor_registry.extract(doc_type, text)
    assert fields["merchant"] == "Starbucks Coffee"
    assert fields["receipt_number"] == "98451"
    assert fields["date"] == "2024-08-20"
    assert fields["time"] == "12:35 PM"
    assert fields["total"] == "65.00"
    assert fields["payment_method"] == "Cash"

# ---------------------------------------------------------
# 4. Contract Document
# ---------------------------------------------------------
def test_contract_classification_and_extraction():
    text = """
    عقد اتفاق وتقديم خدمات برمجية
    حرر في: 2024-01-10
    الطرف الأول: شركة التطوير الحديث
    الطرف الثاني: مؤسسة الأمل للتجارة
    البند الأول: موضوع العقد والخدمات المتفق عليها
    البند الثاني: القيمة المالية وطريقة السداد
    يلتزم الطرف الثاني بسداد مبلغ 50,000 جنيه مصري
    التوقيعات:
    توقيع الطرف الأول: _____  توقيع الطرف الثاني: _____
    """
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "contract"

    fields = extractor_registry.extract(doc_type, text)
    assert "عقد" in fields["title"]
    assert "شركة التطوير" in fields["first_party"]
    assert "مؤسسة الأمل" in fields["second_party"]
    assert fields["date"] == "2024-01-10"
    assert len(fields["clauses"]) >= 2
    assert fields["signatures_detected"] is True

# ---------------------------------------------------------
# 5. CV / Resume Document
# ---------------------------------------------------------
def test_cv_classification_and_extraction():
    text = """
    Ahmed Mohamed Hassan
    ahmed.hassan@example.com
    +201012345678
    linkedin.com/in/ahmed-hassan
    Cairo, Egypt

    Professional Summary:
    Senior Software Engineer with 5 years experience in Python and FastAPI.

    Skills:
    Python, FastAPI, Docker, PostgreSQL, React, Git, Machine Learning

    Education:
    Bachelor of Computer Science, Cairo University (2019)
    """
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "cv"

    fields = extractor_registry.extract(doc_type, text)
    assert fields["name"] == "Ahmed Mohamed Hassan"
    assert fields["email"] == "ahmed.hassan@example.com"
    assert "01012345678" in fields["phone"]
    assert any("linkedin.com" in link for link in fields["links"])
    assert "Python" in fields["skills"]
    assert "Docker" in fields["skills"]
    assert any("Cairo University" in edu for edu in fields["education"])

# ---------------------------------------------------------
# 6. Passport Document (MRZ)
# ---------------------------------------------------------
def test_passport_classification_and_extraction():
    text = """
    PASSPORT
    ARAB REPUBLIC OF EGYPT
    P<EGYHASSAN<<AHMED<<<<<<<<<<<<<<<<<<<<<<<<<<
    A123456780EGY9001015M3001018<<<<<<<<<<<<<<02
    """
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "passport"

    fields = extractor_registry.extract(doc_type, text)
    assert fields["mrz_detected"] is True
    assert fields["passport_number"] == "A12345678"
    assert fields["surname"] == "HASSAN"
    assert fields["given_names"] == "AHMED"
    assert fields["nationality"] == "EGY"
    assert fields["birth_date"] == "1990-01-01"
    assert fields["expiry_date"] == "2030-01-01"
    assert fields["gender"] == "Male"

# ---------------------------------------------------------
# 7. Driver License Document
# ---------------------------------------------------------
def test_driver_license_classification_and_extraction():
    text = """
    جمهورية مصر العربية
    وزارة الداخلية - قطاع المرور
    رخصة قيادة خاصة
    الاسم: محمود خليل إبراهيم
    رقم الرخصة: 29205151234567
    درجة خاصة
    فصيلة الدم: O+
    تاريخ الإصدار: 2020-05-15
    تاريخ الانتهاء: 2030-05-15
    """
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "driver_license"

    fields = extractor_registry.extract(doc_type, text)
    assert "محمود" in fields["holder_name"]
    assert "خاصة" in fields["license_class"]
    assert "O+" in fields["blood_type"]

# ---------------------------------------------------------
# 8. Bank Document
# ---------------------------------------------------------
def test_bank_document_classification_and_extraction():
    text = """
    Commercial International Bank (CIB)
    كشف حساب بنكي - Account Statement
    Account Number: 100023458912
    IBAN: EG380002000100023458912001
    SWIFT Code: CIBEEGCX
    Statement Period: 2024-01-01 to 2024-01-31
    Closing Balance: 245,600.50 EGP
    """
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "bank_document"

    fields = extractor_registry.extract(doc_type, text)
    assert "CIB" in fields["bank_name"] or "Bank" in fields["bank_name"]
    assert fields["account_number"] == "100023458912"
    assert fields["iban"] == "EG380002000100023458912001"
    assert fields["swift_bic"] == "CIBEEGCX"
    assert fields["balance"] == "245600.50"

# ---------------------------------------------------------
# 9. Language Detection (Arabic, English, Mixed, Numeric)
# ---------------------------------------------------------
def test_language_detection():
    # Pure Arabic
    lang, conf, dist = LanguageDetector.detect("هذا نص باللغة العربية الفصحى لاستخراج المعلومات والبيانات")
    assert lang == "ar"
    assert conf > 0.8

    # Pure English
    lang, conf, dist = LanguageDetector.detect("This is an official document written completely in English.")
    assert lang == "en"
    assert conf > 0.8

    # Mixed Arabic & English
    lang, conf, dist = LanguageDetector.detect("جمهورية مصر العربية Arab Republic of Egypt Tax Invoice فاتورة ضريبية")
    assert lang == "ar-en"

    # Numeric heavy
    lang, conf, dist = LanguageDetector.detect("984572910 293847291 01928374 84729104 29384720")
    assert lang == "numeric"

# ---------------------------------------------------------
# 10. Screenshot Document
# ---------------------------------------------------------
def test_screenshot_classification():
    text = """
    10:45 AM  |  Settings  |  WiFi Connected  |  Battery 85%
    https://myportal.company.com/dashboard/analytics
    File Edit View Search Terminal Help
    Status: Online (200 OK)
    """
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "screenshot"

    fields = extractor_registry.extract(doc_type, text)
    assert any("myportal.company.com" in u for u in fields["detected_urls"])

# ---------------------------------------------------------
# 11. Standalone Table
# ---------------------------------------------------------
def test_table_classification_and_extraction():
    text = """
    Item | Quantity | Price | Total
    Laptop | 2 | 15000 | 30000
    Mouse | 5 | 200 | 1000
    Keyboard | 3 | 500 | 1500
    """
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "table"

    fields = extractor_registry.extract(doc_type, text)
    assert "Item" in fields["headers"]
    assert fields["row_count"] >= 3

# ---------------------------------------------------------
# 12. Generic Image with Text
# ---------------------------------------------------------
def test_image_with_text():
    text = "STOP NO PARKING"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type in ["image_with_text", "generic_document"]

# ---------------------------------------------------------
# 13. Unknown Document Graceful Degradation
# ---------------------------------------------------------
def test_unknown_document_no_crash():
    text = "Random words scattered without context or identifiable patterns."
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type in ["unknown", "generic_document"]

    # Must extract without throwing errors
    fields = extractor_registry.extract(doc_type, text)
    assert isinstance(fields, dict)

# ---------------------------------------------------------
# 14. Image Quality Analysis
# ---------------------------------------------------------
def test_image_quality_analysis():
    # Sharp gradient image
    sharp_img = np.zeros((400, 400, 3), dtype=np.uint8)
    sharp_img[:, :200] = 255
    metrics_sharp = analyze_image_quality(sharp_img)
    assert metrics_sharp.is_blurry is False
    assert metrics_sharp.resolution_ok is True

    # Blurry uniform image
    blur_img = np.ones((400, 400, 3), dtype=np.uint8) * 128
    metrics_blur = analyze_image_quality(blur_img)
    assert metrics_blur.is_blurry is True
    assert len(metrics_blur.warnings) > 0

# ---------------------------------------------------------
# 15. Reading Order & Layout Analyzer
# ---------------------------------------------------------
def test_reading_order_and_layout():
    # Create artificial bounding boxes simulating two lines of text
    b1 = TextBlock(
        box=BoundingBox(points=[(10, 10), (100, 10), (100, 30), (10, 30)], normalized_points=[(0.01, 0.01), (0.1, 0.01), (0.1, 0.03), (0.01, 0.03)], width=90, height=20, area=1800),
        text="Hello",
        confidence=0.95
    )
    b2 = TextBlock(
        box=BoundingBox(points=[(110, 10), (200, 10), (200, 30), (110, 30)], normalized_points=[(0.11, 0.01), (0.2, 0.01), (0.2, 0.03), (0.11, 0.03)], width=90, height=20, area=1800),
        text="World",
        confidence=0.98
    )
    ordered = organize_reading_order([b2, b1], image_width=500)
    assert ordered[0].text == "Hello"
    assert ordered[1].text == "World"

    layout_info, sections, tables = LayoutAnalyzer.analyze(ordered, 500, 500)
    assert len(layout_info.lines) == 1
    assert layout_info.lines[0].text == "Hello World"

# ---------------------------------------------------------
# 16. Universal Response Schema Verification
# ---------------------------------------------------------
def test_universal_response_schema():
    resp = OCRResponse(
        success=True,
        text="Sample output text",
        document_type="invoice",
        confidence=0.92,
        processing_time_ms=45.2,
        image_width=800,
        image_height=600,
        fields={"invoice_number": "INV-100", "total": "500 EGP"}
    )
    dumped = resp.model_dump()
    assert dumped["success"] is True
    assert dumped["document_type"] == "invoice"
    assert dumped["fields"]["invoice_number"] == "INV-100"

# ---------------------------------------------------------
# 17. End-to-End API Router Verification
# ---------------------------------------------------------
def test_api_extract_endpoint_e2e():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    # Test with sample test_id.jpg if exists
    import os
    img_path = "tests/test_id.jpg"
    if os.path.exists(img_path):
        with open(img_path, "rb") as f:
            response = client.post("/ocr/extract", files={"file": ("test_id.jpg", f, "image/jpeg")})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "document" in data
        assert "layout" in data
        assert "ocr" in data
        assert "quality" in data
        assert "processing" in data
        assert "text" in data
        # Check backward compatibility fields
        assert "document_type" in data
        assert "confidence" in data
        assert "processing_time_ms" in data

