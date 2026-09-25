import re
import logging
from typing import Dict, Any, Optional
from app.services.extraction.base import BaseExtractor
from app.services.extraction.validation import parse_and_validate_date

logger = logging.getLogger("ocr_microservice")

class DriverLicenseExtractor(BaseExtractor):
    """
    Modular Extractor for Driving Licenses.
    Extracts license number, holder name, class, blood type, issue/expiry dates.
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

        # 1. License Number
        lic_match = re.search(r'(?:license\s*(?:no|number)|رقم\s*الرخصة)\s*[:=]?\s*([A-Za-z0-9-_]+)', text, re.IGNORECASE)
        if lic_match:
            lic_no = lic_match.group(1).strip()
            self.set_field(fields, "license_number", lic_no, confidence=0.95, is_valid=True)
        else:
            # Check 14-digit Egyptian NID if present on license
            nid_match = re.search(r'\b(2|3)\d{13}\b', text.replace(" ", ""))
            if nid_match:
                self.set_field(fields, "license_number", nid_match.group(0), confidence=0.95, is_valid=True)

        # 2. Holder Name
        name_match = re.search(r'(?:الاسم|name)\s*[:=]?\s*([A-Za-z\u0600-\u06FF\s]+)', text, re.IGNORECASE)
        if name_match:
            name_val = name_match.group(1).splitlines()[0].strip()
            if len(name_val) >= 2:
                n_conf = self.get_layout_confidence(name_val, layout, default=0.92)
                self.set_field(fields, "holder_name", name_val, confidence=n_conf, is_valid=True)

        # 3. License Class
        class_match = re.search(r'(?:درجة\s*(?:أولى|ثانية|ثالثة)|خاصة|مهنية|درجة\s*خاصة|private|commercial|class\s*[a-z0-9]+)', text, re.IGNORECASE)
        if class_match:
            class_val = class_match.group(0).strip()
            self.set_field(fields, "license_class", class_val, confidence=0.94, is_valid=True)

        # 4. Blood Type
        blood_match = re.search(r'\b(A|B|AB|O)[+-]\b|فصيلة\s*الدم\s*[:=]?\s*([A-Za-z+-]+)', text, re.IGNORECASE)
        if blood_match:
            bt_val = (blood_match.group(1) or blood_match.group(2)).strip()
            self.set_field(fields, "blood_type", bt_val, confidence=0.95, is_valid=True)

        # 5. Dates
        dates = re.findall(r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', text)
        if len(dates) >= 2:
            is_v_iss, _, inote = parse_and_validate_date(dates[0], must_be_past=True)
            self.set_field(fields, "issue_date", dates[0], confidence=0.95 if is_v_iss else 0.50, is_valid=is_v_iss, note=inote)
            is_v_exp, _, enote = parse_and_validate_date(dates[1])
            self.set_field(fields, "expiry_date", dates[1], confidence=0.95 if is_v_exp else 0.50, is_valid=is_v_exp, note=enote)
        elif len(dates) == 1:
            is_v_exp, _, enote = parse_and_validate_date(dates[0])
            self.set_field(fields, "expiry_date", dates[0], confidence=0.95 if is_v_exp else 0.50, is_valid=is_v_exp, note=enote)

        return fields
