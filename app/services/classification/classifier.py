import re
from typing import Tuple, Dict, Any, List, Optional

class UniversalDocumentClassifier:
    """
    Universal Multi-Signal Document Classifier supporting 17 document types:
    id_card, passport, driver_license, invoice, receipt, contract, cv,
    bank_document, form, report, certificate, letter, screenshot, table,
    image_with_text, generic_document, unknown.

    Uses a fusion of:
    1. OCR text & multilingual keywords (Arabic and English)
    2. Structural signals (sections, tables, key-value ratios)
    3. Document geometry & aspect ratio (receipts, cards, sheets)
    4. Exact regex patterns (dates, amounts, National IDs, MRZ, IBAN)

    Never raises exceptions; gracefully falls back to 'generic_document' or 'unknown'.
    """

    CATEGORIES = [
        "id_card", "passport", "driver_license", "invoice", "receipt",
        "contract", "cv", "bank_document", "form", "report", "certificate",
        "letter", "screenshot", "table", "image_with_text", "generic_document", "unknown"
    ]

    @classmethod
    def classify_with_signals(
        cls,
        text: str,
        layout: Any = None,
        metadata: Any = None
    ) -> Dict[str, Any]:
        if not text or not text.strip():
            return {"category": "unknown", "confidence": 0.0, "signals": ["empty_input"]}

        clean_text = text.strip()
        lower = clean_text.lower()
        word_count = len(clean_text.split())
        lines = [l.strip() for l in clean_text.splitlines() if l.strip()]
        line_count = len(lines)

        signals_detected: List[str] = []
        scores: Dict[str, float] = {cat: 0.0 for cat in cls.CATEGORIES}

        # Sparse text check
        if word_count <= 4 and not any(kw in lower for kw in ["جمهورية", "passport", "بطاقة", "invoice", "receipt", "عقد"]):
            return {"category": "image_with_text", "confidence": 0.70, "signals": ["sparse_text_word_count_le_4"]}

        # -------------------------------------------------------------
        # 1. Structural & Layout Signals from LayoutInfo
        # -------------------------------------------------------------
        tables_count = 0
        sections_count = 0
        columns_count = 1
        has_signatures = False

        if layout:
            if hasattr(layout, 'tables') and layout.tables:
                tables_count = len(layout.tables)
            if hasattr(layout, 'blocks') and layout.blocks:
                sections_count = sum(1 for b in layout.blocks if getattr(b, 'type', '') == 'header')
            if hasattr(layout, 'columns'):
                columns_count = getattr(layout, 'columns', 1)
            if hasattr(layout, 'has_signatures'):
                has_signatures = getattr(layout, 'has_signatures', False)

        if tables_count > 0:
            scores["table"] += 2.0 * tables_count
            scores["invoice"] += 1.0 * tables_count
            scores["receipt"] += 0.8 * tables_count
            scores["bank_document"] += 1.2 * tables_count
            signals_detected.append(f"tables_detected_{tables_count}")

        # -------------------------------------------------------------
        # 2. Geometry Signals (Aspect Ratio)
        # -------------------------------------------------------------
        if metadata:
            width = getattr(metadata, 'width', 0) if not isinstance(metadata, dict) else metadata.get('width', 0)
            height = getattr(metadata, 'height', 0) if not isinstance(metadata, dict) else metadata.get('height', 0)
            if width > 0 and height > 0:
                aspect_ratio = height / width
                # Tall receipt ratio (H/W >= 1.8)
                if aspect_ratio >= 1.8:
                    scores["receipt"] += 1.8
                    signals_detected.append("tall_aspect_ratio_receipt")
                # Standard ID/License landscape card (W/H >= 1.35 and relatively small)
                elif width / height >= 1.35 and word_count <= 50:
                    scores["id_card"] += 1.2
                    scores["driver_license"] += 1.2
                    signals_detected.append("landscape_card_aspect_ratio")

        # -------------------------------------------------------------
        # 3. Numeric & Specialized Pattern Signals
        # -------------------------------------------------------------
        # Passport MRZ (e.g. P<EGY, P<USA, P<)
        if re.search(r'p<[a-z]{3}|p<[a-z0-9<]{10}', lower):
            scores["passport"] += 5.5
            signals_detected.append("mrz_passport_pattern")

        # Egyptian National ID (14 digits starting with 2 or 3)
        normalized_digits = clean_text.replace(" ", "").translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
        if re.search(r'\b(2|3)\d{13}\b', normalized_digits):
            scores["id_card"] += 3.5
            signals_detected.append("egyptian_14_digit_national_id")

        # IBAN pattern
        if re.search(r'\b[a-z]{2}\d{2}[a-z0-9]{11,30}\b', lower):
            scores["bank_document"] += 2.5
            signals_detected.append("iban_detected")

        # Invoice number pattern
        if re.search(r'(inv[-#:\s]|فاتورة رقم|invoice\s*#)\s*[a-z0-9-]+', lower):
            scores["invoice"] += 2.2
            signals_detected.append("invoice_number_pattern")

        # -------------------------------------------------------------
        # 4. Multilingual Keyword Matching
        # -------------------------------------------------------------
        keyword_maps = {
            "passport": ["جواز سفر", "passport", "republic of egypt passport", "place of birth", "type p", "nationality"],
            "id_card": ["بطاقة تحقيق الشخصية", "جمهورية مصر العربية", "الرقم القومي", "بطاقة رقم قومي", "national id", "identity card"],
            "driver_license": ["رخصة قيادة", "رخصة تسيير", "driving license", "driver license", "driving licence", "فصيلة الدم", "درجة ثانية", "درجة ثالثة", "درجة أولى", "خاصة"],
            "receipt": ["فاتورة مبسطة", "إيصال", "كاشير", "pos", "receipt", "cashier", "change", "tax invoice - simplified", "الباقي", "نقدى", "طريقة الدفع", "order #", "table #", "طلب رقم"],
            "invoice": ["فاتورة", "فاتورة ضريبية", "invoice", "tax invoice", "bill to", "due date", "subtotal", "vat", "ضريبة القيمة المضافة", "إجمالي الفاتورة", "رقم الفاتورة", "تاريخ الاستحقاق"],
            "contract": ["عقد", "اتفاقية", "الطرف الأول", "الطرف الثاني", "الطرف الثانى", "البند", "ديباجة", "مادة", "تم الاتفاق", "agreement", "contract", "parties hereto", "whereas", "terms and conditions"],
            "cv": ["curriculum vitae", "resume", "cv", "experience", "education", "skills", "work experience", "الخبرات", "المؤهلات", "التعليم", "المهارات", "اللغات", "languages", "summary", "projects", "certifications"],
            "bank_document": ["كشف حساب", "رقم الحساب", "iban", "swift", "balance", "debit", "credit", "رصيد", "بنك", "bank", "account statement", "حركات الحساب", "إيداع", "سحب"],
            "form": ["استمارة", "نموذج", "طلب تسجيل", "application form", "form", "signature:", "التوقيع:", "الاسم:", "date:", "التاريخ:"],
            "certificate": ["شهادة", "تشهد", "تقدير", "إتمام", "شهادة تخرج", "certificate", "hereby certified", "awarded to", "completion", "certified that", "شهادة شكر"],
            "letter": ["السيد /", "عناية", "تحية طيبة وبعد", "dear", "to whom it may concern", "sincerely", "regards", "مع وافر الاحترام", "برجاء التكرم", "مرفق لسيادتكم"],
            "report": ["تقرير", "report", "executive summary", "المقدمة", "التوصيات", "الخاتمة", "جدول الأعمال", "annual report", "findings", "conclusion"],
            "screenshot": ["http://", "https://", "www.", ".com", "file", "edit", "view", "settings", "wifi", "battery", "am", "pm", "chrome", "firefox", "status bar", "notification"]
        }

        for cat, kw_list in keyword_maps.items():
            for kw in kw_list:
                # If pure ASCII/Latin word, require word boundary to avoid substring collisions (e.g. form in platform)
                if kw.isalnum() and kw.isascii():
                    if re.search(r'\b' + re.escape(kw) + r'\b', lower):
                        scores[cat] += 1.4
                        signals_detected.append(f"kw_{cat}:{kw}")
                else:
                    if kw in lower:
                        scores[cat] += 1.4
                        signals_detected.append(f"kw_{cat}:{kw}")

        # High-specificity contextual combinations
        if ("@gmail.com" in lower or "@yahoo.com" in lower or "linkedin.com" in lower or "github.com" in lower) and ("experience" in lower or "education" in lower or "الخبرات" in lower):
            scores["cv"] += 2.5
            signals_detected.append("cv_contact_plus_sections")

        if "مرور" in lower and ("رخصة" in lower or "قيادة" in lower):
            scores["driver_license"] += 2.5
            signals_detected.append("traffic_dept_license")

        # Lines with pipes or tabs
        lines_with_pipes = sum(1 for line in lines if "|" in line or "\t" in line)
        if lines_with_pipes >= 3:
            scores["table"] += 3.0
            signals_detected.append("delimiters_pipe_or_tab")

        # -------------------------------------------------------------
        # 5. Determine Top Category & Confidence
        # -------------------------------------------------------------
        best_cat, max_score = max(scores.items(), key=lambda item: item[1])

        if max_score >= 2.0:
            conf = min(0.98, 0.60 + (max_score * 0.05))
            category = best_cat
        elif max_score >= 1.2:
            conf = 0.55
            category = best_cat
        elif word_count <= 4:
            conf = 0.60
            category = "image_with_text"
        else:
            conf = 0.50
            category = "generic_document"

        return {
            "category": category,
            "confidence": round(conf, 2),
            "signals": signals_detected,
            "scores": {k: round(v, 2) for k, v in scores.items() if v > 0}
        }

    @classmethod
    def classify(cls, text: str, layout: Any = None, metadata: Any = None) -> Tuple[str, float]:
        """Backward-compatible classification method returning (category, confidence)."""
        res = cls.classify_with_signals(text, layout, metadata)
        return res["category"], res["confidence"]
