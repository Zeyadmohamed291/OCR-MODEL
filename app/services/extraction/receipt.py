import re
import logging
from typing import Dict, Any, Optional, List
from app.services.extraction.base import BaseExtractor
from app.services.extraction.validation import (
    parse_and_validate_date,
    validate_invoice_math
)

logger = logging.getLogger("ocr_microservice")

class ReceiptExtractor(BaseExtractor):
    """
    Modular Extractor for Receipts and POS slips.
    Extracts merchant, date, time, items, financial totals, and payment methods.
    Applies date plausibility and financial arithmetic validation.
    """

    def extract(
        self,
        text: str,
        layout: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        if not text:
            return fields

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 1. Merchant Name
        for line in lines[:3]:
            lower_line = line.lower()
            if len(line.split()) <= 6 and not any(kw in lower_line for kw in ["receipt", "invoice", "فاتورة", "إيصال", "order", "date", "cashier", "كاشير"]):
                m_conf = self.get_layout_confidence(line, layout, default=0.92)
                self.set_field(fields, "merchant", line, confidence=m_conf, is_valid=True)
                break

        # 2. Receipt / Ticket / Order Number
        rec_match = re.search(
            r'(?:receipt\s*#|ticket\s*#|order\s*#|طلب\s*رقم|إيصال\s*رقم)\s*[:=]?\s*([A-Za-z0-9-_]+)',
            text,
            re.IGNORECASE
        )
        if rec_match:
            rec_num = rec_match.group(1).strip()
            self.set_field(fields, "receipt_number", rec_num, confidence=0.95, is_valid=True)

        # 3. Date & Time
        date_match = re.search(r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', text)
        if date_match:
            raw_date = date_match.group(1).strip()
            is_valid_date, parsed, note = parse_and_validate_date(raw_date, must_be_past=True)
            d_conf = self.get_layout_confidence(raw_date, layout, default=0.96 if is_valid_date else 0.50)
            self.set_field(fields, "date", raw_date, confidence=d_conf, is_valid=is_valid_date, note=note)

        time_match = re.search(r'\b([01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\s*(?:AM|PM|am|pm|ص|م)?\b', text)
        if time_match:
            raw_time = time_match.group(0).strip()
            t_conf = self.get_layout_confidence(raw_time, layout, default=0.95)
            self.set_field(fields, "time", raw_time, confidence=t_conf, is_valid=True)

        # 4. Financial Totals
        subtotal_str: Optional[str] = None
        tax_str: Optional[str] = None
        total_str: Optional[str] = None

        sub_match = re.search(r'(?:subtotal|المجموع\s*الفرعي)\s*[:=]?\s*([\d,]+(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if sub_match:
            subtotal_str = sub_match.group(1).replace(",", "")
            self.set_field(fields, "subtotal", subtotal_str, confidence=0.95, is_valid=True)

        tax_match = re.search(r'(?:tax|vat|الضريبة)\s*[:=]?\s*([\d,]+(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if tax_match:
            tax_str = tax_match.group(1).replace(",", "")
            self.set_field(fields, "tax", tax_str, confidence=0.95, is_valid=True)

        total_match = re.search(
            r'\b(?:total\s*amount|grand\s*total|total|amount\s*due|المجموع\s*الكلي|الإجمالي|المبلغ|الحساب)\s*[:=]?\s*([\d,]+(?:\.\d{1,2})?)',
            text,
            re.IGNORECASE
        )
        if total_match:
            total_str = total_match.group(1).replace(",", "")
            self.set_field(fields, "total", total_str, confidence=0.95, is_valid=True)

        # Validate math if subtotal and total available
        if total_str and subtotal_str:
            try:
                tot_flt = float(total_str)
                sub_flt = float(subtotal_str)
                tax_flt = float(tax_str) if tax_str else 0.0
                is_math_valid, math_note = validate_invoice_math(sub_flt, tax_flt, 0.0, tot_flt)
                if is_math_valid:
                    self.set_field(fields, "total", total_str, confidence=0.99, is_valid=True, note=math_note)
                else:
                    self.set_field(fields, "total", total_str, confidence=0.55, is_valid=False, note=math_note)
            except ValueError:
                pass

        # 5. Payment Method (Only when clearly detected)
        payment_method: Optional[str] = None
        if re.search(r'\b(cash|نقد|كاش|نقدى)\b', text, re.IGNORECASE):
            payment_method = "Cash"
        elif re.search(r'\b(visa|mastercard|mada|card|بطاقة|فيزا|ماستركارد|credit|debit)\b', text, re.IGNORECASE):
            payment_method = "Card"
        elif re.search(r'\b(apple\s*pay|samsung\s*pay|mada\s*pay|محفظة)\b', text, re.IGNORECASE):
            payment_method = "Mobile Pay"

        if payment_method:
            self.set_field(fields, "payment_method", payment_method, confidence=0.96, is_valid=True)

        # 6. Currency
        curr_match = re.search(r'\b(EGP|USD|EUR|SAR|AED|ج\.م|جنيه|ريال|درهم)\b', text, re.IGNORECASE)
        if curr_match:
            curr_val = curr_match.group(1).upper()
            self.set_field(fields, "currency", curr_val, confidence=0.98, is_valid=True)

        # 7. Line Items Extraction
        items: List[Dict[str, Any]] = []
        if layout and hasattr(layout, 'tables') and layout.tables:
            for tbl in layout.tables:
                if hasattr(tbl, 'raw_data') and len(tbl.raw_data) > 1:
                    for row in tbl.raw_data[1:]:
                        if len(row) >= 2:
                            items.append({"item": row[0], "price": row[-1]})

        if not items:
            # Pattern matching for line items e.g. "Latte Grande  65.00"
            for line in lines:
                m = re.match(r'^([A-Za-z\u0600-\u06FF\s]+)\s+([\d,]+(?:\.\d{2})?)$', line)
                if m:
                    item_name = m.group(1).strip()
                    if not any(kw in item_name.lower() for kw in ["total", "subtotal", "tax", "vat", "cash", "إجمالي", "مجموع"]):
                        items.append({
                            "item": item_name,
                            "price": m.group(2).replace(",", "")
                        })

        if items:
            self.set_field(fields, "items", items, confidence=0.90, is_valid=True)

        return fields
