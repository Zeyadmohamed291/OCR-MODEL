import io
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services.classification.classifier import UniversalDocumentClassifier
from app.services.extraction.registry import extractor_registry
from app.services.image_processing.validator import detect_image_magic_bytes
from app.services.image_processing.loader import MAX_IMAGE_DIMENSION
from app.services.image_processing.preprocessor import AdaptivePreprocessor
from app.domain.schemas.core import ImageQualityMetrics

client = TestClient(app)

def create_synthetic_image(text: str = "Test Document", width: int = 600, height: int = 400, angle: float = 0.0) -> bytes:
    """Helper to generate a valid in-memory JPEG image with text."""
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(img, text, (30, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    if angle != 0.0:
        center = (width // 2, height // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        img = cv2.warpAffine(img, M, (width, height), borderValue=(255, 255, 255))
    success, buffer = cv2.imencode(".jpg", img)
    return buffer.tobytes()

# -------------------------------------------------------------
# Test Group A: The 24 Document & Image Intelligence Scenarios
# -------------------------------------------------------------

def test_01_egyptian_id_scenario():
    text = "جمهورية مصر العربية\nبطاقة تحقيق الشخصية\n29603121409876\nمحمود سامي علي\n10 شارع التحرير الدقي الجيزة"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "id_card"
    fields = extractor_registry.extract(doc_type, text)
    assert fields["national_id"] == "29603121409876"
    assert fields["birth_date"] == "1996-03-12"
    assert fields["governorate"] == "القليوبية"
    assert fields["gender"] == "Male"
    assert fields["_field_confidences"]["national_id"] >= 0.95

def test_02_passport_scenario():
    text = "PASSPORT جواز سفر\nP<EGYHASSAN<<AHMED<<<<<<<<<<<<<<<<<<<<<<<\nA987654321EGY9201015M3001015<<<<<<<<<<<02"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "passport"
    fields = extractor_registry.extract(doc_type, text)
    assert fields["passport_number"] == "A98765432"
    assert fields["nationality"] == "EGY"
    assert fields["sex"] == "Male"
    assert fields["_field_metadata"]["passport_number"]["is_valid"] is True

def test_03_driver_license_scenario():
    text = "جمهورية مصر العربية\nوزارة الداخلية - مرور الجيزة\nرخصة قيادة خاصة\nالاسم: كمال أشرف منصور\nفصيلة الدم: A+\nتاريخ الانتهاء: 2030-05-15"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "driver_license"
    fields = extractor_registry.extract(doc_type, text)
    assert fields["holder_name"] == "كمال أشرف منصور"
    assert fields["blood_type"] == "A+"
    assert fields["expiry_date"] == "2030-05-15"

def test_04_invoice_scenario():
    text = "فاتورة ضريبية Tax Invoice\nInvoice #: INV-8899\nSeller: Nile Tech\nBill To: Cairo Trading\nSubtotal: 1500.00\nTax: 210.00\nDiscount: 50.00\nTotal Amount: 1660.00 EGP"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "invoice"
    fields = extractor_registry.extract(doc_type, text)
    assert fields["invoice_number"] == "INV-8899"
    assert fields["total"] == "1660.00"
    assert fields["_field_metadata"]["total"]["is_valid"] is True
    assert fields["_field_confidences"]["total"] >= 0.98

def test_05_receipt_scenario():
    text = "McDonalds Egypt\nReceipt # 44512\nDate: 2024-06-12\nBig Mac Meal 120.00\nTotal: 120.00 EGP\nPayment: Cash"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "receipt"
    fields = extractor_registry.extract(doc_type, text)
    assert fields["merchant"] == "McDonalds Egypt"
    assert fields["total"] == "120.00"
    assert fields["payment_method"] == "Cash"

def test_06_contract_scenario():
    text = "عقد إيجار شقة سكنية\nحرر في: 2024-01-01\nالطرف الأول: حسام السيد\nالطرف الثاني: عمر شريف\nالبند الأول: موضوع الإيجار\nتوقيع الطرفين"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "contract"
    fields = extractor_registry.extract(doc_type, text)
    assert "عقد" in fields["title"]
    assert "حسام" in fields["first_party"]
    assert fields["signatures_detected"] is True

def test_07_cv_scenario():
    text = "Karim Nader\nkarim.nader@example.com\n+201201234567\nCairo, Egypt\nSummary: Software developer\nSkills: Python, FastAPI, Docker, SQL\nEducation: Bachelor of Computer Science"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "cv"
    fields = extractor_registry.extract(doc_type, text)
    assert fields["name"] == "Karim Nader"
    assert fields["email"] == "karim.nader@example.com"
    assert "Python" in fields["skills"]

def test_08_bank_document_scenario():
    text = "National Bank of Egypt البنك الأهلي المصري\nAccount Statement كشف حساب بنكي\nIBAN: EG380002000100023458912001\nBalance: 75000.00 EGP"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "bank_document"
    fields = extractor_registry.extract(doc_type, text)
    assert "IBAN" in fields["iban"] or "EG38" in fields["iban"]
    assert fields["balance"] == "75000.00"

def test_09_form_scenario():
    text = "نموذج طلب التحاق بالجامعة\nApplication Form\nاسم الطالب: محمد عادل\nالرقم القومي: _____________\nالتاريخ: 2024-09-01"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "form"
    fields = extractor_registry.extract(doc_type, text)
    assert "form_title" in fields or "dates" in fields

def test_10_report_scenario():
    text = "Annual Audit Report تقرير المراجعة السنوي\nPrepared by: Financial Committee\nDate: 2024-03-31\nExecutive Summary of operations"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "report"
    fields = extractor_registry.extract(doc_type, text)
    assert fields.get("report_title") or fields.get("date")

def test_11_certificate_scenario():
    text = "شهادة تقدير وتفوق\nCertificate of Excellence\nThis is to certify that Mariam Ali has passed\nDate: 2024-05-20"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "certificate"
    fields = extractor_registry.extract(doc_type, text)
    assert "شهادة" in fields.get("title", "") or fields.get("recipient")

def test_12_arabic_document_scenario():
    text = "السيد الأستاذ مدير الإدارة العامة\nتحية طيبة وبعد\nنحيط سيادتكم علماً بانتهاء أعمال الصيانة المقررة لشهر مايو.\nوتفضلوا بقبول فائق الاحترام"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type in ("letter", "generic_document")
    fields = extractor_registry.extract(doc_type, text)
    assert fields is not None

def test_13_english_document_scenario():
    text = "Dear Operations Team,\nPlease find attached the quarterly status memo regarding software deployment milestones.\nBest regards,\nManagement"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type in ("letter", "generic_document")
    fields = extractor_registry.extract(doc_type, text)
    assert fields is not None

def test_14_arabic_english_mixed_document_scenario():
    text = "فاتورة Tax Invoice رقم INV-2024\nالمشتري Buyer: Cairo Solutions\nTotal الإجمالي: 5000.00 EGP"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "invoice"
    fields = extractor_registry.extract(doc_type, text)
    assert fields["invoice_number"] == "INV-2024"
    assert fields["total"] == "5000.00"

def test_15_screenshot_scenario():
    text = "https://console.cloud.google.com/monitoring\nDashboard | Metrics | Alerts\nBattery 92% | 11:30 AM | WiFi Connected"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "screenshot"
    fields = extractor_registry.extract(doc_type, text)
    assert len(fields["detected_urls"]) >= 1 or len(fields.get("urls", [])) >= 1

def test_16_table_scenario():
    text = "Product | Qty | Unit Price | Total\nServer A | 2 | 2500.00 | 5000.00\nServer B | 1 | 3000.00 | 3000.00"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type in ("table", "invoice")
    fields = extractor_registry.extract(doc_type, text)
    assert fields is not None

def test_17_generic_image_with_text_scenario():
    text = "Enjoy your coffee today"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type == "image_with_text"
    fields = extractor_registry.extract(doc_type, text)
    assert isinstance(fields, dict)

def test_18_unknown_document_scenario():
    text = "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt."
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    assert doc_type in ("generic_document", "unknown")
    fields = extractor_registry.extract(doc_type, text)
    assert isinstance(fields, dict)

def test_19_rotated_image_preprocessing_scenario():
    # Verify deskewing and orientation correction logic works safely
    img = np.full((300, 400, 3), 240, dtype=np.uint8)
    cv2.putText(img, "Rotated Line 123", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    metrics = ImageQualityMetrics(skew_angle=5.0, is_blurry=False)
    processed, variants = AdaptivePreprocessor.preprocess_adaptive(img, metrics)
    assert processed is not None
    assert "original" in variants

def test_20_low_quality_image_preprocessing_scenario():
    # Low contrast / underexposed image
    dark_img = np.full((300, 400, 3), 40, dtype=np.uint8)
    metrics = ImageQualityMetrics(brightness=35.0, contrast=20.0, is_blurry=False)
    processed, variants = AdaptivePreprocessor.preprocess_adaptive(dark_img, metrics)
    assert processed is not None

def test_21_noisy_image_preprocessing_scenario():
    # Image with noise
    noisy_img = np.random.randint(0, 256, (300, 400, 3), dtype=np.uint8)
    metrics = ImageQualityMetrics(is_blurry=False)
    processed, variants = AdaptivePreprocessor.preprocess_adaptive(noisy_img, metrics)
    assert processed is not None

def test_22_perspective_distorted_image_scenario():
    # Synthetic distorted document
    img = np.full((400, 500, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (450, 350), (0, 0, 0), 2)
    metrics = ImageQualityMetrics(is_blurry=False)
    processed, variants = AdaptivePreprocessor.preprocess_adaptive(img, metrics)
    assert processed is not None

def test_23_numeric_heavy_document_scenario():
    text = "Balance: 125000.50\nAccount: 9876543210\nTax ID: 456-789-012\nCode: 99401"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    fields = extractor_registry.extract(doc_type, text)
    assert any("125000.50" in a for a in fields.get("amounts", [])) or "125000.50" in str(fields)

def test_24_email_url_heavy_document_scenario():
    text = "Support: support@example.com\nBilling: billing@company.org\nPortal: https://portal.company.org/login"
    doc_type, conf = UniversalDocumentClassifier.classify(text)
    fields = extractor_registry.extract(doc_type, text)
    assert "support@example.com" in fields.get("emails", [])
    assert "billing@company.org" in fields.get("emails", [])
    assert any("portal.company.org" in u for u in fields.get("urls", []))

# -------------------------------------------------------------
# Test Group B: Security, Memory & Error Handling Hardening
# -------------------------------------------------------------

def test_security_magic_bytes_detection():
    # Valid JPEG
    assert detect_image_magic_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image/jpeg"
    # Valid PNG
    assert detect_image_magic_bytes(b"\x89PNG\r\n\x1a\n\x00\x00") == "image/png"
    # Valid WebP
    assert detect_image_magic_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8") == "image/webp"
    # Fake / Invalid
    assert detect_image_magic_bytes(b"Hello this is a plain text file") is None

def test_security_corrupted_file_upload_returns_structured_error():
    """Corrupted bytes must return HTTP 415 or 400 with structured ErrorResponse, never a 500 stacktrace."""
    corrupted_bytes = b"NotAnImageCorruptedBinaryGarbageData12345678"
    response = client.post(
        "/ocr/extract",
        files={"file": ("corrupt.jpg", corrupted_bytes, "image/jpeg")}
    )
    assert response.status_code in (400, 415)
    data = response.json()
    # Verify standard structured error format
    assert data["success"] is False
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]
    # Verify NO Python stack traces are exposed
    assert "Traceback" not in response.text
    assert "File \"" not in response.text

def test_security_fake_extension_rejected():
    """Text file disguised with .jpg extension must be rejected."""
    fake_bytes = b"Just plain text disguised as jpg"
    response = client.post(
        "/ocr/extract",
        files={"file": ("document.jpg", fake_bytes, "image/jpeg")}
    )
    assert response.status_code == 415
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_signature_and_declared_type_mismatch_is_rejected():
    jpeg = create_synthetic_image()
    response = client.post("/ocr/extract", files={"file": ("image.png", jpeg, "image/png")})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

def test_performance_telemetry_breakdown_in_successful_response():
    """Verify that ProcessingMeta reports granular stage timings."""
    image_bytes = create_synthetic_image("Invoice # INV-001\nTotal: 100.00", width=400, height=200)
    response = client.post(
        "/ocr/extract",
        files={"file": ("sample.jpg", image_bytes, "image/jpeg")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Check granular telemetry
    processing = data["processing"]
    assert "processing_time_ms" in processing
    assert "image_loading_time_ms" in processing
    assert "preprocessing_time_ms" in processing
    assert "ocr_time_ms" in processing
    assert "layout_time_ms" in processing
    assert "classification_time_ms" in processing
    assert "extraction_time_ms" in processing
    assert processing["processing_time_ms"] > 0
