import re
import datetime
import logging
from typing import Dict, Any, Optional
from app.services.extraction.base import BaseExtractor
from app.services.extraction.validation import (
    validate_passport_number,
    compute_mrz_check_digit,
    parse_and_validate_date
)

logger = logging.getLogger("ocr_microservice")

class PassportExtractor(BaseExtractor):
    """
    Modular Extractor for Passports.
    Supports ICAO Doc 9303 Machine Readable Zone (MRZ) parsing with check-digit validation
    and Visual Inspection Zone (VIZ) heuristics.
    Only returns fields that are actually detected.
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

        # 1. Parse MRZ (Machine Readable Zone)
        # Type 3 MRZ has 2 lines of 44 characters (or slightly varying due to OCR spaces)
        mrz_lines = [l.replace(" ", "") for l in lines if ("P<" in l or ("<" in l and len(l) >= 28))]

        mrz_parsed = False
        if len(mrz_lines) >= 2:
            l1, l2 = mrz_lines[-2], mrz_lines[-1]
            if l1.startswith("P<") or "<" in l1:
                mrz_parsed = True
                self.set_field(fields, "mrz_detected", True, confidence=0.99, is_valid=True)

                # Line 1: P<ISSLASTNAME<<GIVENNAME<MIDDLE<<<<<<<<<<<<
                country_code = l1[2:5].replace("<", "")
                if country_code:
                    self.set_field(fields, "issuing_country", country_code, confidence=0.99, is_valid=True)
                    self.set_field(fields, "nationality", country_code, confidence=0.99, is_valid=True)

                name_part = l1[5:]
                surname, given = None, None
                if "<<" in name_part:
                    surname_raw, given_raw = name_part.split("<<", 1)
                    surname = surname_raw.replace("<", " ").strip()
                    given = given_raw.replace("<", " ").strip()
                elif name_part:
                    surname = name_part.replace("<", " ").strip()

                if surname:
                    self.set_field(fields, "surname", surname, confidence=0.98, is_valid=True)
                if given:
                    self.set_field(fields, "given_names", given, confidence=0.98, is_valid=True)
                if surname and given:
                    full_name = f"{given} {surname}"
                    self.set_field(fields, "name", full_name, confidence=0.98, is_valid=True)
                elif surname:
                    self.set_field(fields, "name", surname, confidence=0.98, is_valid=True)

                # Line 2: doc_no(9), check(1), nationality(3), dob(6), check(1), sex(1), exp(6), check(1)
                if len(l2) >= 28:
                    doc_no = l2[0:9].replace("<", "").strip()
                    if doc_no:
                        # Check digit validation
                        chk_digit_char = l2[9:10]
                        chk_valid = False
                        if chk_digit_char.isdigit():
                            calc_chk = compute_mrz_check_digit(l2[0:9])
                            chk_valid = (calc_chk == int(chk_digit_char))

                        p_valid, p_note = validate_passport_number(doc_no)
                        conf = 0.99 if chk_valid else (0.95 if p_valid else 0.50)
                        self.set_field(
                            fields, "passport_number", doc_no,
                            confidence=conf,
                            is_valid=p_valid,
                            note="MRZ checksum verified" if chk_valid else p_note
                        )

                    # Date of Birth
                    dob_raw = l2[13:19]
                    if dob_raw.isdigit() and len(dob_raw) == 6:
                        yy = int(dob_raw[:2])
                        year = f"19{yy}" if yy > 30 else f"20{yy}"
                        dob_str = f"{year}-{dob_raw[2:4]}-{dob_raw[4:6]}"
                        is_v_dob, _, dnote = parse_and_validate_date(dob_str, must_be_past=True)
                        self.set_field(fields, "date_of_birth", dob_str, confidence=0.99 if is_v_dob else 0.50, is_valid=is_v_dob, note=dnote)
                        # Also provide birth_date for backward compatibility
                        self.set_field(fields, "birth_date", dob_str, confidence=0.99 if is_v_dob else 0.50, is_valid=is_v_dob)

                    # Sex / Gender
                    sex_char = l2[20].upper()
                    if sex_char in ["M", "F"]:
                        gender_val = "Male" if sex_char == "M" else "Female"
                        self.set_field(fields, "sex", gender_val, confidence=0.99, is_valid=True)
                        self.set_field(fields, "gender", gender_val, confidence=0.99, is_valid=True)

                    # Expiry Date
                    exp_raw = l2[21:27]
                    if exp_raw.isdigit() and len(exp_raw) == 6:
                        yy = int(exp_raw[:2])
                        year = f"20{yy}"
                        exp_str = f"{year}-{exp_raw[2:4]}-{exp_raw[4:6]}"
                        is_v_exp, _, enote = parse_and_validate_date(exp_str)
                        self.set_field(fields, "expiry_date", exp_str, confidence=0.99 if is_v_exp else 0.50, is_valid=is_v_exp, note=enote)

        # 2. Visual Inspection Zone (VIZ) Fallbacks / Complements
        # Passport Number
        if not fields.get("passport_number"):
            p_match = re.search(
                r'(?:passport\s*(?:no|number)|رقم الجواز)\s*[:=]?\s*([A-Z0-9]{7,10})',
                text,
                re.IGNORECASE
            )
            if p_match:
                doc_no = p_match.group(1).strip()
                p_valid, p_note = validate_passport_number(doc_no)
                conf = self.get_layout_confidence(doc_no, layout, default=0.95 if p_valid else 0.45)
                self.set_field(fields, "passport_number", doc_no, confidence=conf, is_valid=p_valid, note=p_note)

        # Name
        if not fields.get("surname"):
            sn_match = re.search(r'(?:surname|nom|اللقب|اسم العائلة)\s*[:=]?\s*([A-Za-z\u0600-\u06FF\s]+)', text, re.IGNORECASE)
            if sn_match:
                sn_val = sn_match.group(1).splitlines()[0].strip()
                if len(sn_val) >= 2:
                    self.set_field(fields, "surname", sn_val, confidence=0.92, is_valid=True)

        if not fields.get("given_names"):
            gn_match = re.search(r'(?:given\s*names?|prénoms|الاسم)\s*[:=]?\s*([A-Za-z\u0600-\u06FF\s]+)', text, re.IGNORECASE)
            if gn_match:
                gn_val = gn_match.group(1).splitlines()[0].strip()
                if len(gn_val) >= 2:
                    self.set_field(fields, "given_names", gn_val, confidence=0.92, is_valid=True)

        if not fields.get("name"):
            if fields.get("surname") and fields.get("given_names"):
                self.set_field(fields, "name", f"{fields['given_names']} {fields['surname']}", confidence=0.92, is_valid=True)
            elif fields.get("given_names"):
                self.set_field(fields, "name", fields["given_names"], confidence=0.90, is_valid=True)

        # Nationality & Issuing Country
        if not fields.get("nationality"):
            nat_match = re.search(r'(?:nationality|nationalité|الجنسية)\s*[:=]?\s*([A-Za-z\u0600-\u06FF\s]+)', text, re.IGNORECASE)
            if nat_match:
                nat_val = nat_match.group(1).splitlines()[0].strip()
                if len(nat_val) >= 2:
                    self.set_field(fields, "nationality", nat_val, confidence=0.92, is_valid=True)

        if not fields.get("issuing_country"):
            ctry_match = re.search(r'(?:issuing\s*country|country|دولة الإصدار)\s*[:=]?\s*([A-Za-z\u0600-\u06FF\s]+)', text, re.IGNORECASE)
            if ctry_match:
                ctry_val = ctry_match.group(1).splitlines()[0].strip()
                if len(ctry_val) >= 2:
                    self.set_field(fields, "issuing_country", ctry_val, confidence=0.92, is_valid=True)

        # Date of Birth
        if not fields.get("date_of_birth"):
            dob_match = re.search(r'(?:date\s*of\s*birth|dob|né le|تاريخ الميلاد)\s*[:=]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text, re.IGNORECASE)
            if dob_match:
                dob_raw = dob_match.group(1).strip()
                is_v, _, note = parse_and_validate_date(dob_raw, must_be_past=True)
                self.set_field(fields, "date_of_birth", dob_raw, confidence=0.95 if is_v else 0.50, is_valid=is_v, note=note)
                self.set_field(fields, "birth_date", dob_raw, confidence=0.95 if is_v else 0.50, is_valid=is_v)

        # Issue Date
        if not fields.get("issue_date"):
            iss_match = re.search(r'(?:date\s*of\s*issue|issue\s*date|délivré le|تاريخ الإصدار)\s*[:=]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text, re.IGNORECASE)
            if iss_match:
                iss_raw = iss_match.group(1).strip()
                is_v, _, note = parse_and_validate_date(iss_raw, must_be_past=True)
                self.set_field(fields, "issue_date", iss_raw, confidence=0.95 if is_v else 0.50, is_valid=is_v, note=note)

        # Expiry Date
        if not fields.get("expiry_date"):
            exp_match = re.search(r'(?:date\s*of\s*expiry|expiry\s*date|expire le|تاريخ الانتهاء)\s*[:=]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text, re.IGNORECASE)
            if exp_match:
                exp_raw = exp_match.group(1).strip()
                is_v, _, note = parse_and_validate_date(exp_raw)
                self.set_field(fields, "expiry_date", exp_raw, confidence=0.95 if is_v else 0.50, is_valid=is_v, note=note)

        # Sex
        if not fields.get("sex"):
            sex_match = re.search(r'(?:sex|gender|sexe|النوع|الجنس)\s*[:=]?\s*(M|F|Male|Female|ذكر|أنثى)\b', text, re.IGNORECASE)
            if sex_match:
                s_raw = sex_match.group(1).upper()
                s_val = "Male" if s_raw in ["M", "MALE", "ذكر"] else "Female"
                self.set_field(fields, "sex", s_val, confidence=0.95, is_valid=True)
                self.set_field(fields, "gender", s_val, confidence=0.95, is_valid=True)

        return fields
