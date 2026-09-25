import re
import datetime
import logging
from typing import Optional, Dict, Tuple, Any, List
from app.services.extraction.base import BaseExtractor
from app.services.extraction.validation import (
    EGYPTIAN_GOVERNORATES,
    validate_egyptian_national_id,
    parse_and_validate_date,
    normalize_unicode_digits,
)

logger = logging.getLogger("ocr_microservice")

def _normalize_ar(s: str) -> str:
    s = re.sub(r'[\u0617-\u061A\u064B-\u0652]', '', s)
    s = re.sub(r'[أإآٱ]', 'ا', s)
    s = re.sub(r'[ةه]', 'ه', s)
    s = re.sub(r'[ىي]', 'ي', s)
    return s.lower()

def is_address_indicator(line: str) -> bool:
    norm = _normalize_ar(line)
    # Check standalone street abbreviation like 'ش 308' or '2ش مسجد'
    if re.search(r'(?:^|\s|\d)ش(?:\s|\.|\/|$)', norm):
        return True
    if any(_normalize_ar(kw) in norm for kw in ADDRESS_KEYWORDS):
        return True
    if any(_normalize_ar(gov) in norm for gov in EGYPTIAN_GOVERNORATES.values()):
        return True
    return False

ADDRESS_KEYWORDS = [
    "مركز", "قسم", "مدينة", "قرية", "كفر", "ميت", "عزبة", "حي", "حى", "شارع",
    "محافظة", "برج", "عمارة", "شقة", "مساكن", "بلوك", "طريق", "حارة", "زقاق",
    "التجمع", "ميدان", "منطقة", "اول", "أول", "ثان", "ثاني"
]

NAME_ANCHOR_KEYWORDS = ["بطاقة", "تحقيق", "الشخصية", "جمهورية", "مصر", "العربية"]

def is_valid_egyptian_id(nid: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Backwards-compatible wrapper around validate_egyptian_national_id.
    Returns: (is_valid, birth_date, gov_code, gender)
    """
    is_valid, info, _ = validate_egyptian_national_id(nid)
    if is_valid and info:
        return True, info["birth_date"], info["governorate_code"], info["gender"]
    return False, None, None, None


class IDCardExtractor(BaseExtractor):
    """
    Modular Extractor for Egyptian National ID cards and generic ID cards.
    Uses candidate detection, label recognition, spatial layout relationships,
    and mathematical/calendar validation without relying on fixed line indices.
    """

    def extract(
        self,
        text: str,
        layout: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self._extract_internal(text, layout=layout, metadata=metadata)

    @classmethod
    def extract_id_fields(cls, text: str) -> Dict[str, Optional[str]]:
        """
        Maintains complete backwards compatibility for legacy callers.
        """
        instance = cls()
        results = instance._extract_internal(text)
        # Ensure standard keys are present
        legacy_keys = ["national_id", "name", "address", "birth_date", "gender", "governorate_code"]
        out: Dict[str, Optional[str]] = {}
        for k in legacy_keys:
            out[k] = results.get(k)
        if "governorate" in results:
            out["governorate"] = results.get("governorate")
        return out

    def _extract_internal(
        self,
        text: str,
        layout: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        fields: Dict[str, Any] = {
            "national_id": None,
            "name": None,
            "address": None,
            "birth_date": None,
            "gender": None,
            "governorate": None,
            "governorate_code": None
        }

        if not text:
            return fields

        # 1. Normalize Numerals & Handle Spurious Spacing
        normalized_text = normalize_unicode_digits(text)

        # Fix split digit groups in RTL
        fixed_lines = []
        for raw_line in normalized_text.splitlines():
            stripped = raw_line.strip()
            if stripped:
                digit_chars = sum(c.isdigit() for c in stripped)
                alpha_chars = sum(c.isalpha() for c in stripped)
                if digit_chars > alpha_chars and digit_chars >= 10:
                    groups = re.findall(r'\d+', stripped)
                    if len(groups) > 1:
                        rev = ''.join(reversed(groups))
                        if len(rev) == 14 and rev[0] in ('2', '3'):
                            fixed_lines.append(rev)
                            continue
            fixed_lines.append(raw_line)
        normalized_text = '\n'.join(fixed_lines)

        # Remove spaces within numbers
        cleaned_text = re.sub(r'(?<=\d)[ \t]+(?=\d)', '', normalized_text)
        noisy_symbols = ['|', '_', '-', '؛', ';', ':', '.', ',', '»', '«']
        for sym in noisy_symbols:
            cleaned_text = cleaned_text.replace(sym, ' ')

        lines = [l.strip() for l in cleaned_text.splitlines() if l.strip()]

        # 2. Candidate Detection for 14-Digit National ID
        id_candidates = re.findall(r'\b(?:2|3)\d{13}\b', cleaned_text)
        found_valid_nid = False

        for cand in id_candidates:
            is_valid, info, reason = validate_egyptian_national_id(cand)
            if is_valid and info:
                nid_conf = self.get_layout_confidence(cand, layout, default=0.98)
                self.set_field(fields, "national_id", cand, confidence=nid_conf, is_valid=True, note=reason)
                self.set_field(fields, "birth_date", info["birth_date"], confidence=0.99, is_valid=True, note="Derived from validated ID")
                self.set_field(fields, "gender", info["gender"], confidence=0.99, is_valid=True, note="Derived from validated ID")
                self.set_field(fields, "governorate", info["governorate"], confidence=0.98, is_valid=True, note="Decoded governorate")
                self.set_field(fields, "governorate_code", info["governorate_code"], confidence=0.98, is_valid=True)
                found_valid_nid = True
                break

        # Fallback A: Per-line digit agglomeration and sliding window
        if not found_valid_nid:
            for line in lines:
                raw_digits = re.sub(r'\D', '', line)
                if len(raw_digits) == 14 and raw_digits[0] in ('2', '3'):
                    is_valid, info, reason = validate_egyptian_national_id(raw_digits)
                    if is_valid and info:
                        nid_conf = self.get_layout_confidence(raw_digits, layout, default=0.98)
                        self.set_field(fields, "national_id", raw_digits, confidence=nid_conf, is_valid=True, note=reason)
                        self.set_field(fields, "birth_date", info["birth_date"], confidence=0.99, is_valid=True, note="Derived from validated ID")
                        self.set_field(fields, "gender", info["gender"], confidence=0.99, is_valid=True, note="Derived from validated ID")
                        self.set_field(fields, "governorate", info["governorate"], confidence=0.98, is_valid=True, note="Decoded governorate")
                        self.set_field(fields, "governorate_code", info["governorate_code"], confidence=0.98, is_valid=True)
                        found_valid_nid = True
                        break
                elif len(raw_digits) > 14:
                    for w_idx in range(len(raw_digits) - 14 + 1):
                        sub_cand = raw_digits[w_idx:w_idx+14]
                        if sub_cand[0] in ('2', '3'):
                            is_valid, info, reason = validate_egyptian_national_id(sub_cand)
                            if is_valid and info:
                                nid_conf = self.get_layout_confidence(sub_cand, layout, default=0.98)
                                self.set_field(fields, "national_id", sub_cand, confidence=nid_conf, is_valid=True, note=reason)
                                self.set_field(fields, "birth_date", info["birth_date"], confidence=0.99, is_valid=True, note="Derived from validated ID")
                                self.set_field(fields, "gender", info["gender"], confidence=0.99, is_valid=True, note="Derived from validated ID")
                                self.set_field(fields, "governorate", info["governorate"], confidence=0.98, is_valid=True, note="Decoded governorate")
                                self.set_field(fields, "governorate_code", info["governorate_code"], confidence=0.98, is_valid=True)
                                found_valid_nid = True
                                break
                    if found_valid_nid:
                        break

        # Fallback B: Cross-line digit stitching for RTL/EasyOCR split groups
        if not found_valid_nid:
            all_num_lines = [re.sub(r'\D', '', l) for l in lines if sum(c.isdigit() for c in l) >= 2]
            if len(all_num_lines) >= 2:
                # Try combinations of adjacent number segments
                for i in range(len(all_num_lines) - 1):
                    for combo in [all_num_lines[i] + all_num_lines[i+1], all_num_lines[i+1] + all_num_lines[i]]:
                        if len(combo) == 14 and combo[0] in ('2', '3'):
                            is_valid, info, reason = validate_egyptian_national_id(combo)
                            if is_valid and info:
                                self.set_field(fields, "national_id", combo, confidence=0.95, is_valid=True, note=reason)
                                self.set_field(fields, "birth_date", info["birth_date"], confidence=0.99, is_valid=True, note="Derived from validated ID")
                                self.set_field(fields, "gender", info["gender"], confidence=0.99, is_valid=True, note="Derived from validated ID")
                                self.set_field(fields, "governorate", info["governorate"], confidence=0.98, is_valid=True, note="Decoded governorate")
                                self.set_field(fields, "governorate_code", info["governorate_code"], confidence=0.98, is_valid=True)
                                found_valid_nid = True
                                break
                    if found_valid_nid:
                        break

        # 3. Dynamic Name Extraction (Free-Form, Anchored & Label-Based)
        # Priority A: Explicit Label ("الاسم", "Name")
        detected_name: Optional[str] = None
        for i, line in enumerate(lines):
            lower_line = line.lower()
            if "الاسم" in line or "name" in lower_line:
                candidate = re.sub(r'^(الاسم|name)\s*(:| )*\s*', '', line, flags=re.IGNORECASE).strip()
                if len(candidate) > 2 and not any(kw in candidate for kw in ADDRESS_KEYWORDS):
                    detected_name = candidate
                    break
                elif i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    if len(next_line) > 2 and not re.search(r'\d', next_line):
                        detected_name = next_line
                        break

        # Priority B: Positional Header Anchor ("بطاقة تحقيق الشخصية")
        if not detected_name:
            anchor_idx = -1
            for i, line in enumerate(lines):
                if any(kw in line for kw in ["بطاقة", "تحقيق", "الشخصية"]):
                    anchor_idx = i

            if anchor_idx != -1:
                name_tokens = []
                for j in range(anchor_idx + 1, min(anchor_idx + 6, len(lines))):
                    candidate_line = lines[j].strip()
                    # Exclude header words
                    if any(kw in candidate_line for kw in ["بطاقة", "تحقيق", "الشخصية", "جمهورية", "مصر"]):
                        continue
                    # If line is the 14-digit Egyptian national ID, skip it
                    cleaned_digits = candidate_line.replace(" ", "")
                    if len(cleaned_digits) == 14 and cleaned_digits.isdigit() and cleaned_digits[0] in ('2', '3'):
                        continue
                    # Exclude address indicators
                    if is_address_indicator(candidate_line):
                        break
                    if any(kw in candidate_line for kw in ["الاسم", "العنوان"]):
                        break
                    # Valid name part
                    if len(candidate_line) >= 2:
                        name_tokens.append(candidate_line)

                if name_tokens:
                    detected_name = " ".join(name_tokens)

        # Priority C: English / Latin Fallback (Name: ...)
        if not detected_name:
            for l in lines[:4]:
                if re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)+$', l):
                    detected_name = l
                    break

        if detected_name:
            from app.services.text_processing.arabic_corrector import ArabicOCRCorrector
            detected_name = ArabicOCRCorrector.correct_line(detected_name)
            name_conf = self.get_layout_confidence(detected_name, layout, default=0.92)
            # Validation: Name should have at least 2 words
            has_multiple_words = len(detected_name.split()) >= 2
            self.set_field(
                fields,
                "name",
                detected_name,
                confidence=name_conf if has_multiple_words else 0.65,
                is_valid=has_multiple_words,
                note="Multi-word personal name detected" if has_multiple_words else "Single word name candidate"
            )

        # 4. Dynamic Address Extraction (Keyword & Label-Based)
        detected_address: Optional[str] = None
        # Priority A: Explicit Label ("العنوان", "Address")
        for i, line in enumerate(lines):
            lower_line = line.lower()
            if "العنوان" in line or "address" in lower_line:
                candidate = re.sub(r'^(العنوان|address)\s*(:| )*\s*', '', line, flags=re.IGNORECASE).strip()
                if len(candidate) > 2:
                    detected_address = candidate
                    break
                elif i + 1 < len(lines):
                    detected_address = lines[i+1].strip()
                    break

        # Priority B: Keyword-guided address block
        if not detected_address:
            address_lines = []
            found_start = False
            for line in lines:
                norm_line = _normalize_ar(line)
                if not found_start:
                    if is_address_indicator(line) and not any(kw in line for kw in ["تحقيق", "الشخصية", "جمهورية"]) and "الاسم" not in line:
                        found_start = True
                        address_lines.append(line)
                else:
                    # Collect remaining address lines until national ID or serial line
                    digits_in_line = sum(c.isdigit() for c in line)
                    is_serial = bool(re.search(r'^[A-Za-z0-9/$-]{5,}$', line.strip()))
                    if not re.search(r'\b\d{14}\b', line) and digits_in_line < 4 and not is_serial:
                        address_lines.append(line)
                    else:
                        break

            if address_lines:
                detected_address = " ".join(address_lines)

        if detected_address:
            from app.services.text_processing.arabic_corrector import ArabicOCRCorrector
            detected_address = ArabicOCRCorrector.correct_line(detected_address)
            addr_conf = self.get_layout_confidence(detected_address, layout, default=0.90)
            self.set_field(fields, "address", detected_address, confidence=addr_conf, is_valid=True)

        # 5. Birth Date Fallback (if not already extracted from Egyptian National ID)
        if not fields.get("birth_date"):
            dob_keywords = ["تاريخ الميلاد", "dob", "birth", "date of birth"]
            found_dob: Optional[str] = None
            for i, line in enumerate(lines):
                lower = line.lower()
                if any(kw in lower for kw in dob_keywords):
                    match = re.search(r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b', line)
                    if match:
                        found_dob = match.group(1)
                    elif i + 1 < len(lines):
                        match = re.search(r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b', lines[i+1])
                        if match:
                            found_dob = match.group(1)
                    if found_dob:
                        break

            if found_dob:
                is_valid_date, parsed, note = parse_and_validate_date(found_dob, must_be_past=True)
                dob_conf = 0.95 if is_valid_date else 0.50
                self.set_field(
                    fields,
                    "birth_date",
                    found_dob,
                    confidence=dob_conf,
                    is_valid=is_valid_date,
                    note=note
                )

        return fields
