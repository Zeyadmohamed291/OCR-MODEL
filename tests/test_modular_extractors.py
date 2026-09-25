import inspect
import pytest
from app.services.extraction.registry import extractor_registry, ExtractorRegistry
from app.services.extraction.base import BaseExtractor
from app.services.extraction.id_card import IDCardExtractor
from app.services.extraction.invoice import InvoiceExtractor
from app.services.extraction.receipt import ReceiptExtractor
from app.services.extraction.cv import CVExtractor
from app.services.extraction.contract import ContractExtractor
from app.services.extraction.passport import PassportExtractor
from app.services.extraction.driver_license import DriverLicenseExtractor
from app.services.extraction.generic import GenericExtractor
from app.services.extraction.validation import (
    validate_egyptian_national_id,
    validate_invoice_math,
    validate_passport_number,
    parse_and_validate_date
)
from app.domain.schemas.core import LayoutTable
from app.services.layout.bidi_formatter import convert_dict_to_structured_fields

# -------------------------------------------------------------
# 1. Egyptian ID Extractor Tests (No fixed line indexes, validation, no hallucinations)
# -------------------------------------------------------------

def test_egyptian_id_candidate_detection_and_derivation():
    extractor = IDCardExtractor()
    text = """
    بطاقة تحقيق الشخصية
    جمهورية مصر العربية
    29807151401234
    أحمد إبراهيم الدسوقي
    شارع النصر قسم النزهة القاهرة
    """
    fields = extractor.extract(text)

    assert fields["national_id"] == "29807151401234"
    assert fields["birth_date"] == "1998-07-15"
    assert fields["gender"] == "Male"
    assert fields["governorate_code"] == "14"
    assert fields["governorate"] == "القليوبية"
    assert "أحمد إبراهيم" in fields["name"]
    assert "قسم النزهة" in fields["address"]
    
    # Verify field-level confidence
    assert fields["_field_confidences"]["national_id"] >= 0.95
    assert fields["_field_confidences"]["birth_date"] >= 0.98
    assert fields["_field_metadata"]["national_id"]["is_valid"] is True

def test_egyptian_id_with_nonstandard_line_order():
    """Ensure extraction does NOT depend on fixed line indices."""
    extractor = IDCardExtractor()
    # Name first, national ID separated, address on different line
    text = """
    الاسم: سارة ممدوح فهمي
    جمهورية مصر العربية
    بطاقة تحقيق الشخصية
    العنوان: 15 شارع الجلاء مدينة طنطا الغربية
    الرقم القومي: 30205201609876
    """
    fields = extractor.extract(text)

    assert fields["national_id"] == "30205201609876"
    assert fields["birth_date"] == "2002-05-20"
    assert fields["gender"] == "Male"
    assert fields["governorate"] == "الغربية"
    assert fields["name"] == "سارة ممدوح فهمي"
    assert "شارع الجلاء" in fields["address"]

def test_egyptian_id_validation_failure_and_no_hallucination():
    """Invalid national ID format must not invent dates or governorates."""
    extractor = IDCardExtractor()
    # Month 19 is invalid!
    text = """
    بطاقة تحقيق الشخصية
    الرقم القومي 29519011234567
    """
    fields = extractor.extract(text)

    # Must never invent birth date or gender from an invalid ID
    assert fields.get("birth_date") is None
    assert fields.get("gender") is None
    assert fields.get("governorate") is None

def test_egyptian_id_never_invents_missing_fields():
    extractor = IDCardExtractor()
    text = "29501011234567"
    fields = extractor.extract(text)

    assert fields["national_id"] == "29501011234567"
    assert fields.get("name") is None
    assert fields.get("address") is None

# -------------------------------------------------------------
# 2. Invoice Extractor Tests (Dynamic items, quantities, arithmetic validation)
# -------------------------------------------------------------

def test_invoice_dynamic_extraction_with_table_items():
    extractor = InvoiceExtractor()
    text = """
    فاتورة مبيعات ضريبية
    Invoice #: INV-2024-5541
    Date: 2024-04-10
    Due Date: 2024-05-10
    Seller: Delta Electronics Cairo
    Bill To: Modern Systems Ltd
    Subtotal: 2000.00
    Tax: 280.00
    Discount: 100.00
    Total Amount: 2180.00 EGP
    """
    table = LayoutTable(
        table_id=1,
        rows=3,
        cols=4,
        headers=["Item", "Quantity", "Unit Price", "Total"],
        raw_data=[
            ["Item", "Quantity", "Unit Price", "Total"],
            ["LED Monitor 27 inch", "2", "800.00", "1600.00"],
            ["Wireless Keyboard", "1", "400.00", "400.00"]
        ]
    )
    class DummyLayout:
        tables = [table]
        lines = []
        blocks = []

    fields = extractor.extract(text, layout=DummyLayout())

    assert fields["invoice_number"] == "INV-2024-5541"
    assert fields["invoice_date"] == "2024-04-10"
    assert fields["seller"] == "Delta Electronics Cairo"
    assert fields["buyer"] == "Modern Systems Ltd"
    assert fields["subtotal"] == "2000.00"
    assert fields["tax"] == "280.00"
    assert fields["discount"] == "100.00"
    assert fields["total"] == "2180.00"
    assert fields["currency"] == "EGP"
    assert len(fields["items"]) == 2
    assert fields["quantities"] == [2.0, 1.0]
    assert fields["unit_prices"] == [800.0, 400.0]

    # Math consistency check (2000 + 280 - 100 == 2180): confidence is boosted
    assert fields["_field_metadata"]["total"]["is_valid"] is True
    assert fields["_field_confidences"]["total"] >= 0.98

def test_invoice_arithmetic_inconsistency_validation():
    """Inconsistent financial totals must be flagged as invalid without altering values."""
    extractor = InvoiceExtractor()
    text = """
    Invoice No: INV-ERR-001
    Subtotal: 1000.00
    Tax: 140.00
    Discount: 0.00
    Total: 5000.00
    """
    fields = extractor.extract(text)

    # The extracted value MUST be preserved (not silently changed to 1140.00)
    assert fields["total"] == "5000.00"
    # But marked invalid and low confidence
    assert fields["_field_metadata"]["total"]["is_valid"] is False
    assert fields["_field_confidences"]["total"] <= 0.60
    assert "Inconsistent" in fields["_field_metadata"]["total"]["validation_note"]

# -------------------------------------------------------------
# 3. Receipt Extractor Tests
# -------------------------------------------------------------

def test_receipt_comprehensive_extraction():
    extractor = ReceiptExtractor()
    text = """
    Costa Coffee Zamalek
    Receipt # 10442
    Date: 2024-09-01
    10:15 AM
    Americano 50.00
    Croissant 40.00
    Subtotal: 90.00
    Tax: 12.60
    Total: 102.60 EGP
    Payment: Visa Card
    """
    fields = extractor.extract(text)

    assert fields["merchant"] == "Costa Coffee Zamalek"
    assert fields["receipt_number"] == "10442"
    assert fields["date"] == "2024-09-01"
    assert fields["time"] == "10:15 AM"
    assert fields["total"] == "102.60"
    assert fields["payment_method"] == "Card"
    assert fields["currency"] == "EGP"
    assert fields["_field_metadata"]["total"]["is_valid"] is True

def test_receipt_no_hallucinated_payment_method():
    extractor = ReceiptExtractor()
    text = """
    Bakery Shop
    Date: 2024-03-01
    Total: 25.00
    """
    fields = extractor.extract(text)
    assert "payment_method" not in fields

# -------------------------------------------------------------
# 4. CV / Resume Extractor Tests
# -------------------------------------------------------------

def test_cv_comprehensive_extraction():
    extractor = CVExtractor()
    text = """
    Youssef Tarek
    youssef.tarek@example.com
    +201099887766
    linkedin.com/in/youssef-tarek
    Cairo, Egypt

    Professional Summary:
    Full stack developer specializing in Python and React.

    Education:
    Bachelor of Computer Engineering, Ain Shams University 2021

    Experience:
    Senior Software Engineer at Cairo Tech
    Developer at Nile Solutions

    Skills:
    Python, FastAPI, Docker, Kubernetes, React, PostgreSQL, Git

    Certifications:
    AWS Certified Solutions Architect

    Languages:
    Arabic, English, German
    """
    fields = extractor.extract(text)

    assert fields["name"] == "Youssef Tarek"
    assert fields["email"] == "youssef.tarek@example.com"
    assert fields["phone"] == "+201099887766"
    assert any("linkedin.com" in l for l in fields["links"])
    assert "Bachelor" in fields["education"][0]
    assert "Senior Software Engineer" in fields["experience"][0]
    assert "Python" in fields["skills"]
    assert "Docker" in fields["skills"]
    assert any("AWS" in c for c in fields["certifications"])
    assert "Arabic" in fields["languages"]
    assert "English" in fields["languages"]
    assert fields["_field_metadata"]["email"]["is_valid"] is True

def test_cv_invalid_email_handling():
    extractor = CVExtractor()
    text = """
    Hassan Ali
    hassan_not_an_email
    Phone: +201112223334
    """
    fields = extractor.extract(text)
    assert "email" not in fields
    assert fields["phone"] == "+201112223334"

# -------------------------------------------------------------
# 5. Contract Extractor Tests
# -------------------------------------------------------------

def test_contract_comprehensive_extraction():
    extractor = ContractExtractor()
    text = """
    عقد بيع وتوريد معدات
    حرر في: 2024-02-15
    الطرف الأول: الشركة الهندسية للمقاولات
    الطرف الثاني: مصنع النصر للغزل
    البند الأول: موضوع العقد والالتزامات
    البند الثاني: القيمة الإجمالية 250,000 جنيه مصري
    البند الثالث: شروط التسليم والضمان
    التوقيعات:
    توقيع الطرف الأول: _____    توقيع الطرف الثاني: _____
    """
    fields = extractor.extract(text)

    assert "عقد" in fields["title"]
    assert "الشركة الهندسية" in fields["first_party"]
    assert "مصنع النصر" in fields["second_party"]
    assert fields["date"] == "2024-02-15"
    assert len(fields["clauses"]) >= 3
    assert fields["signatures_detected"] is True
    assert any("250,000" in a for a in fields["amounts"])

# -------------------------------------------------------------
# 6. Passport Extractor Tests
# -------------------------------------------------------------

def test_passport_mrz_extraction_and_validation():
    extractor = PassportExtractor()
    # 2 lines of standard ICAO Doc 9303 Type 3 MRZ
    text = """
    PASSPORT
    P<EGYELMASRY<<MOHAMED<AHMED<<<<<<<<<<<<<<<<<
    A123456784EGY9005155M3005155<<<<<<<<<<<<<<02
    """
    fields = extractor.extract(text)

    assert fields["passport_number"] == "A12345678"
    assert fields["surname"] == "ELMASRY"
    assert fields["given_names"] == "MOHAMED AHMED"
    assert fields["name"] == "MOHAMED AHMED ELMASRY"
    assert fields["nationality"] == "EGY"
    assert fields["issuing_country"] == "EGY"
    assert fields["date_of_birth"] == "1990-05-15"
    assert fields["sex"] == "Male"
    assert fields["expiry_date"] == "2030-05-15"
    # MRZ check verified: confidence is 0.99
    assert fields["_field_confidences"]["passport_number"] >= 0.95
    assert fields["_field_metadata"]["passport_number"]["is_valid"] is True

def test_passport_only_returns_actually_detected_fields():
    extractor = PassportExtractor()
    text = "Just a visual zone note: Passport No: A98765432"
    fields = extractor.extract(text)

    assert fields["passport_number"] == "A98765432"
    assert "surname" not in fields
    assert "date_of_birth" not in fields
    assert "expiry_date" not in fields

# -------------------------------------------------------------
# 7. Driver License Extractor Tests
# -------------------------------------------------------------

def test_driver_license_extraction():
    extractor = DriverLicenseExtractor()
    text = """
    رخصة قيادة خاصة
    الاسم: محمود عادل سالم
    رقم الرخصة: 29201012104567
    درجة خاصة
    فصيلة الدم: O+
    تاريخ الإصدار: 2020-01-10
    تاريخ الانتهاء: 2030-01-10
    """
    fields = extractor.extract(text)

    assert fields["holder_name"] == "محمود عادل سالم"
    assert fields["license_number"] == "29201012104567"
    assert "خاصة" in fields["license_class"]
    assert fields["blood_type"] == "O+"
    assert fields["issue_date"] == "2020-01-10"
    assert fields["expiry_date"] == "2030-01-10"

# -------------------------------------------------------------
# 8. Field-Level Confidence Independence
# -------------------------------------------------------------

def test_field_confidences_are_independent_from_document_and_ocr_averages():
    """Verify that field confidences are not hardcoded to document or average OCR confidence."""
    text = """
    Tax Invoice
    Invoice #: INV-9901
    Date: 2024-05-01
    Subtotal: 1000.00
    Tax: 140.00
    Total: 5000.00
    """
    fields = extractor_registry.extract("invoice", text)
    
    # Check that individual fields have distinct confidences
    inv_conf = fields["_field_confidences"]["invoice_number"]
    total_conf = fields["_field_confidences"]["total"]
    
    # Inconsistent total should have low confidence
    assert total_conf <= 0.60
    # While valid invoice number has high confidence
    assert inv_conf >= 0.90
    assert inv_conf != total_conf

    # Convert to structured fields
    structured = convert_dict_to_structured_fields(fields, confidence=0.85)
    field_map = {sf.field_name: sf for sf in structured}
    
    assert field_map["total"].confidence <= 0.60
    assert field_map["total"].is_valid is False
    assert field_map["invoice_number"].confidence >= 0.90
    assert field_map["invoice_number"].is_valid is True

# -------------------------------------------------------------
# 9. Decoupled OCR Engine Verification
# -------------------------------------------------------------

def test_ocr_engine_is_completely_decoupled_from_extractors():
    """Ensure adding a new extractor does not require modifying the OCR engine."""
    import app.infrastructure.ocr.easyocr_engine as ocr_module
    
    source_code = inspect.getsource(ocr_module)
    # The OCR engine must NEVER import or know about any extractor
    assert "Extractor" not in source_code
    assert "id_card" not in source_code
    assert "invoice" not in source_code
    assert "national_id" not in source_code
    
    # Demonstrate dynamic registration of a new custom extractor
    class CustomMedicalReportExtractor(BaseExtractor):
        def extract(self, text, layout=None, metadata=None):
            f = {}
            self.set_field(f, "diagnosis", "Healthy", confidence=0.97)
            return f

    custom_registry = ExtractorRegistry()
    custom_registry._extractors["medical_report"] = CustomMedicalReportExtractor()
    
    res = custom_registry.extract("medical_report", "Medical Report text")
    assert res["diagnosis"] == "Healthy"
    assert res["_field_confidences"]["diagnosis"] == 0.97
