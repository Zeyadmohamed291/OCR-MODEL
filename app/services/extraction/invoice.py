import re
import logging
from typing import Dict, Any, Optional, List
from app.services.extraction.base import BaseExtractor
from app.services.extraction.validation import (
    parse_and_validate_date,
    validate_invoice_math
)

logger = logging.getLogger("ocr_microservice")

class InvoiceExtractor(BaseExtractor):
    """
    Modular Extractor for Invoices (commercial, tax, electronic).
    Extracts invoice metadata, line items (description, quantity, unit price, total),
    financial breakdowns (subtotal, tax, discount, total), and performs arithmetic validation.
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

        # 1. Invoice Number
        inv_match = re.search(
            r'(?:invoice\s*(?:no|number|#)|inv\s*#|فاتورة\s*رقم|رقم\s*الفاتورة|(?:invoice|فاتورة)[^\n]*?(?:رقم|no|number|#))\s*[:=]?\s*([A-Za-z0-9-_/]+)',
            text,
            re.IGNORECASE
        )
        if inv_match:
            inv_num = inv_match.group(1).strip()
            is_valid = bool(re.match(r'^[A-Za-z0-9-_/]{3,}$', inv_num))
            conf = self.get_layout_confidence(inv_num, layout, default=0.96 if is_valid else 0.60)
            self.set_field(
                fields, "invoice_number", inv_num,
                confidence=conf, is_valid=is_valid,
                note="Valid alphanumeric invoice number" if is_valid else "Unusual format"
            )

        # 2. Dates (Invoice Date & Due Date)
        date_match = re.search(
            r'(?:invoice\s*date|date|تاريخ\s*الفاتورة|التاريخ)\s*[:=]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            text,
            re.IGNORECASE
        )
        if date_match:
            raw_date = date_match.group(1).strip()
            is_valid_date, parsed, note = parse_and_validate_date(raw_date)
            date_conf = self.get_layout_confidence(raw_date, layout, default=0.95 if is_valid_date else 0.50)
            # Store as invoice_date and date for compatibility
            self.set_field(fields, "invoice_date", raw_date, confidence=date_conf, is_valid=is_valid_date, note=note)
            self.set_field(fields, "date", raw_date, confidence=date_conf, is_valid=is_valid_date, note=note)

        due_match = re.search(
            r'(?:due\s*date|payment\s*due|تاريخ\s*الاستحقاق|ميعاد\s*السداد)\s*[:=]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            text,
            re.IGNORECASE
        )
        if due_match:
            raw_due = due_match.group(1).strip()
            is_valid_due, _, note = parse_and_validate_date(raw_due)
            due_conf = self.get_layout_confidence(raw_due, layout, default=0.95 if is_valid_due else 0.50)
            self.set_field(fields, "due_date", raw_due, confidence=due_conf, is_valid=is_valid_due, note=note)

        # 3. Seller and Buyer
        seller_match = re.search(
            r'(?:seller|vendor|from|المورد|البائع|شركة)\s*[:=]?\s*([A-Za-z\u0600-\u06FF0-9\s.&\'"-]+)',
            text,
            re.IGNORECASE
        )
        if seller_match:
            seller_val = seller_match.group(1).splitlines()[0].strip()
            if len(seller_val) >= 2 and not any(kw in seller_val.lower() for kw in ["invoice", "date", "bill to", "tax"]):
                s_conf = self.get_layout_confidence(seller_val, layout, default=0.92)
                self.set_field(fields, "seller", seller_val, confidence=s_conf, is_valid=True)

        buyer_match = re.search(
            r'(?:bill\s*to|buyer|customer|client|العميل|المشتري|إلى|السيد)\s*[:=]?\s*([A-Za-z\u0600-\u06FF0-9\s.&\'"-]+)',
            text,
            re.IGNORECASE
        )
        if buyer_match:
            buyer_val = buyer_match.group(1).splitlines()[0].strip()
            if len(buyer_val) >= 2 and not any(kw in buyer_val.lower() for kw in ["subtotal", "vat", "tax", "total"]):
                b_conf = self.get_layout_confidence(buyer_val, layout, default=0.92)
                self.set_field(fields, "buyer", buyer_val, confidence=b_conf, is_valid=True)

        # 4. Currency
        curr_match = re.search(r'\b(EGP|USD|EUR|GBP|SAR|AED|ج\.م|جنيه|دولار|ريال)\b', text, re.IGNORECASE)
        if curr_match:
            curr_val = curr_match.group(1).upper()
            c_conf = self.get_layout_confidence(curr_match.group(0), layout, default=0.98)
            self.set_field(fields, "currency", curr_val, confidence=c_conf, is_valid=True)

        # 5. Financial Breakdown
        subtotal_str: Optional[str] = None
        tax_str: Optional[str] = None
        discount_str: Optional[str] = None
        total_str: Optional[str] = None

        subtotal_match = re.search(
            r'(?:subtotal|net\s*amount|المجموع\s*الفرعي|الإجمالي\s*قبل\s*الضريبة)\s*[:=]?\s*([\d,]+(?:\.\d{1,2})?)',
            text,
            re.IGNORECASE
        )
        if subtotal_match:
            subtotal_str = subtotal_match.group(1).replace(",", "")
            self.set_field(fields, "subtotal", subtotal_str, confidence=0.95, is_valid=True)

        tax_match = re.search(
            r'(?:tax|vat|sales\s*tax|ضريبة\s*القيمة\s*المضافة|الضريبة)\s*[:=]?\s*([\d,]+(?:\.\d{1,2})?)',
            text,
            re.IGNORECASE
        )
        if tax_match:
            tax_str = tax_match.group(1).replace(",", "")
            self.set_field(fields, "tax", tax_str, confidence=0.95, is_valid=True)

        discount_match = re.search(
            r'(?:discount|خصم|تخفيض)\s*[:=]?\s*([\d,]+(?:\.\d{1,2})?)',
            text,
            re.IGNORECASE
        )
        if discount_match:
            discount_str = discount_match.group(1).replace(",", "")
            self.set_field(fields, "discount", discount_str, confidence=0.95, is_valid=True)

        total_match = re.search(
            r'\b(?:total\s*amount|grand\s*total|total|إجمالي|المجموع|صافي)(?:[^\n\d:]*?)[:=]?\s*([\d,]+(?:\.\d{1,2})?)',
            text,
            re.IGNORECASE
        )
        if total_match:
            total_str = total_match.group(1).replace(",", "")
            self.set_field(fields, "total", total_str, confidence=0.95, is_valid=True)

        # 6. Mathematical Consistency Validation
        sub_flt = float(subtotal_str) if subtotal_str else None
        tax_flt = float(tax_str) if tax_str else None
        disc_flt = float(discount_str) if discount_str else None
        tot_flt = float(total_str) if total_str else None

        if tot_flt is not None and sub_flt is not None:
            is_math_valid, math_note = validate_invoice_math(sub_flt, tax_flt, disc_flt, tot_flt)
            if is_math_valid:
                # Math confirmed: boost total confidence
                self.set_field(fields, "total", total_str, confidence=0.99, is_valid=True, note=math_note)
                if subtotal_str:
                    self.set_field(fields, "subtotal", subtotal_str, confidence=0.98, is_valid=True)
                if tax_str:
                    self.set_field(fields, "tax", tax_str, confidence=0.98, is_valid=True)
            else:
                # Math inconsistent: preserve value, mark invalid with lower confidence
                self.set_field(fields, "total", total_str, confidence=0.55, is_valid=False, note=math_note)

        # 7. Dynamic Line Items Extraction (Table & Text-Based)
        items: List[Dict[str, Any]] = []
        quantities: List[float] = []
        unit_prices: List[float] = []

        # A. From Layout Tables if detected
        if layout and hasattr(layout, 'tables') and layout.tables:
            for tbl in layout.tables:
                if hasattr(tbl, 'raw_data') and len(tbl.raw_data) > 1:
                    headers = [h.lower() for h in tbl.raw_data[0]]
                    desc_idx, qty_idx, price_idx, tot_idx = -1, -1, -1, -1
                    for idx, h in enumerate(headers):
                        if any(kw in h for kw in ["item", "desc", "الصنف", "الوصف", "بيان"]):
                            desc_idx = idx
                        elif any(kw in h for kw in ["qty", "quantity", "الكمية", "عدد"]):
                            qty_idx = idx
                        elif any(kw in h for kw in ["price", "unit", "سعر", "فردي"]):
                            price_idx = idx
                        elif any(kw in h for kw in ["total", "amount", "الإجمالي", "قيمة"]):
                            tot_idx = idx

                    for row in tbl.raw_data[1:]:
                        if len(row) >= 2:
                            item_dict: Dict[str, Any] = {
                                "description": row[desc_idx] if desc_idx != -1 and desc_idx < len(row) else row[0],
                                "amount": row[tot_idx] if tot_idx != -1 and tot_idx < len(row) else row[-1]
                            }
                            # Quantity
                            if qty_idx != -1 and qty_idx < len(row):
                                try:
                                    q = float(re.sub(r'[^\d.]', '', row[qty_idx]))
                                    item_dict["quantity"] = q
                                    quantities.append(q)
                                except (ValueError, TypeError):
                                    pass
                            # Unit Price
                            if price_idx != -1 and price_idx < len(row):
                                try:
                                    p = float(re.sub(r'[^\d.]', '', row[price_idx]))
                                    item_dict["unit_price"] = p
                                    unit_prices.append(p)
                                except (ValueError, TypeError):
                                    pass

                            items.append(item_dict)

        # B. From Text Patterns if no tables available
        if not items:
            item_pattern = re.compile(r'^([A-Za-z\u0600-\u06FF\s0-9]+)\s+(\d+(?:\.\d+)?)\s*[@xX]\s*([\d,]+(?:\.\d{2})?)\s+([\d,]+(?:\.\d{2})?)$')
            for line in lines:
                m = item_pattern.match(line)
                if m:
                    try:
                        q_val = float(m.group(2))
                        p_val = float(m.group(3).replace(",", ""))
                        t_val = float(m.group(4).replace(",", ""))
                        items.append({
                            "description": m.group(1).strip(),
                            "quantity": q_val,
                            "unit_price": p_val,
                            "amount": str(t_val)
                        })
                        quantities.append(q_val)
                        unit_prices.append(p_val)
                    except (ValueError, TypeError):
                        pass

        if items:
            self.set_field(fields, "items", items, confidence=0.92, is_valid=True)
        if quantities:
            self.set_field(fields, "quantities", quantities, confidence=0.92, is_valid=True)
        if unit_prices:
            self.set_field(fields, "unit_prices", unit_prices, confidence=0.92, is_valid=True)

        return fields
