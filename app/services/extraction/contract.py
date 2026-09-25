import re
import logging
from typing import Dict, Any, Optional, List
from app.services.extraction.base import BaseExtractor
from app.services.extraction.validation import parse_and_validate_date

logger = logging.getLogger("ocr_microservice")

class ContractExtractor(BaseExtractor):
    """
    Modular Extractor for Contracts and Legal Agreements.
    Extracts agreement title, parties, dates, monetary amounts, structured clauses,
    and detects signatures.
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

        # 1. Title
        for l in lines[:4]:
            if any(kw in l for kw in ["عقد", "اتفاقية", "Agreement", "Contract", "Memorandum"]):
                t_conf = self.get_layout_confidence(l, layout, default=0.95)
                self.set_field(fields, "title", l, confidence=t_conf, is_valid=True)
                break

        # 2. Parties
        parties: List[str] = []
        p1_match = re.search(
            r'(?:الطرف\s*الأول|First\s*Party)\s*[:=]?\s*([A-Za-z\u0600-\u06FF0-9\s.,]+)',
            text,
            re.IGNORECASE
        )
        if p1_match:
            p1_val = p1_match.group(1).splitlines()[0].strip()
            if len(p1_val) >= 2:
                p1_conf = self.get_layout_confidence(p1_val, layout, default=0.92)
                self.set_field(fields, "first_party", p1_val, confidence=p1_conf, is_valid=True)
                parties.append(p1_val)

        p2_match = re.search(
            r'(?:الطرف\s*(?:الثاني|الثانى)|Second\s*Party)\s*[:=]?\s*([A-Za-z\u0600-\u06FF0-9\s.,]+)',
            text,
            re.IGNORECASE
        )
        if p2_match:
            p2_val = p2_match.group(1).splitlines()[0].strip()
            if len(p2_val) >= 2:
                p2_conf = self.get_layout_confidence(p2_val, layout, default=0.92)
                self.set_field(fields, "second_party", p2_val, confidence=p2_conf, is_valid=True)
                parties.append(p2_val)

        if parties:
            self.set_field(fields, "parties", parties, confidence=0.92, is_valid=True)

        # 3. Contract Dates
        date_matches = re.findall(
            r'(?:تاريخ\s*التحرير|حرر\s*في|الموافق|Date|dated)\s*[:=]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            text,
            re.IGNORECASE
        )
        dates_list = []
        for d in date_matches:
            is_valid_date, parsed, note = parse_and_validate_date(d)
            dates_list.append(d)

        if dates_list:
            primary_date = dates_list[0]
            is_valid_pdate, _, pnote = parse_and_validate_date(primary_date)
            self.set_field(fields, "date", primary_date, confidence=0.96 if is_valid_pdate else 0.50, is_valid=is_valid_pdate, note=pnote)
            self.set_field(fields, "dates", list(dict.fromkeys(dates_list)), confidence=0.95, is_valid=True)

        # 4. Clauses / Articles
        clauses = []
        clause_pattern = re.compile(
            r'(?:(?:البند|المادة|الفصل)\s*[\u0600-\u06FF0-9]+|Article\s*\d+|Clause\s*\d+)[^\n]*',
            re.IGNORECASE
        )
        for match in clause_pattern.finditer(text):
            clause_str = match.group(0).strip()
            if 3 < len(clause_str) < 120:
                clauses.append(clause_str)

        if clauses:
            self.set_field(fields, "clauses", clauses[:15], confidence=0.94, is_valid=True)

        # 5. Financial Amounts Mentioned
        amounts = re.findall(
            r'(?:[\d,]+(?:\.\d{1,2})?\s*(?:جنيه|ج\.م|EGP|USD|EUR|دولار|ريال))',
            text
        )
        if amounts:
            self.set_field(fields, "amounts", list(dict.fromkeys(amounts))[:5], confidence=0.93, is_valid=True)

        # 6. Signatures Detection
        has_signatures = False
        if layout and getattr(layout, "has_signatures", False):
            has_signatures = True
        elif any(kw in text for kw in ["توقيع", "التوقيعات", "Signature", "Signatures", "Signed by"]):
            has_signatures = True

        if has_signatures:
            self.set_field(fields, "signatures_detected", True, confidence=0.95, is_valid=True)

        return fields
