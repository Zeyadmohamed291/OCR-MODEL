import re
import datetime
import unicodedata
from typing import Optional, Tuple, Dict, Any, List

EGYPTIAN_GOVERNORATES = {
    "01": "القاهرة", "02": "الاسكندرية", "03": "بورسعيد", "04": "السويس",
    "11": "دمياط", "12": "الدقهلية", "13": "الشرقية", "14": "القليوبية",
    "15": "كفر الشيخ", "16": "الغربية", "17": "المنوفية", "18": "البحيرة",
    "19": "الاسماعيلية", "21": "الجيزة", "22": "بنى سويف", "23": "الفيوم",
    "24": "المنيا", "25": "اسيوط", "26": "سوهاج", "27": "قنا", "28": "اسوان",
    "29": "الاقصر", "31": "البحر الاحمر", "32": "الوادى الجديد",
    "33": "مطروح", "34": "شمال سيناء", "35": "جنوب سيناء", "88": "خارج الجمهورية"
}

DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
    "%m/%d/%Y", "%d.%m.%Y", "%Y.%m.%d", "%Y%m%d"
]

def normalize_unicode_digits(value: str) -> str:
    """Convert Unicode decimal digits to ASCII for validation only."""
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in str(value))

def parse_and_validate_date(
    date_str: str,
    must_be_past: bool = False,
    must_be_future: bool = False
) -> Tuple[bool, Optional[datetime.date], Optional[str]]:
    """
    Validates calendar date correctness and plausibility.
    Returns: (is_valid, parsed_date, reason)
    """
    if not date_str:
        return False, None, "Empty date"

    cleaned = date_str.strip()
    # Normalize separators
    normalized = re.sub(r'[\s]+', '', normalize_unicode_digits(cleaned))

    parsed: Optional[datetime.date] = None
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.datetime.strptime(normalized, fmt).date()
            # Basic sanity check on year
            if 1900 <= dt.year <= 2100:
                parsed = dt
                break
        except (ValueError, TypeError):
            continue

    if not parsed:
        return False, None, f"Invalid date format or calendar date: {date_str}"

    today = datetime.date.today()
    if must_be_past and parsed > today:
        return False, parsed, f"Date {parsed} is in the future but must be past"

    if must_be_future and parsed < today:
        return False, parsed, f"Date {parsed} is in the past but expected future/active"

    return True, parsed, "Valid date"


def validate_egyptian_national_id(nid: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Validates a 14-digit Egyptian National ID strictly.
    Returns: (is_valid, extracted_info, reason)
    """
    if not nid:
        return False, None, "National ID is missing"

    clean_nid = re.sub(r'\D', '', normalize_unicode_digits(str(nid)))
    if len(clean_nid) != 14:
        return False, None, f"National ID must be 14 digits, got {len(clean_nid)}"

    century_digit = clean_nid[0]
    if century_digit not in ('2', '3'):
        return False, None, f"Invalid century indicator '{century_digit}' (must be 2 or 3)"

    year_digits = clean_nid[1:3]
    month = clean_nid[3:5]
    day = clean_nid[5:7]
    gov_code = clean_nid[7:9]
    gender_digit = int(clean_nid[12])

    century_prefix = "19" if century_digit == '2' else "20"
    year_str = f"{century_prefix}{year_digits}"

    # Calendar validation
    try:
        birth_date = datetime.date(int(year_str), int(month), int(day))
    except ValueError:
        return False, None, f"Invalid birth date digits in ID: {year_str}-{month}-{day}"

    # Cannot be born in the future
    if birth_date > datetime.date.today():
        return False, None, f"Birth date {birth_date} is in the future"

    # Governorate validation
    if gov_code not in EGYPTIAN_GOVERNORATES:
        return False, None, f"Unknown governorate code '{gov_code}'"

    governorate_name = EGYPTIAN_GOVERNORATES[gov_code]
    gender = "Male" if gender_digit % 2 != 0 else "Female"

    info = {
        "birth_date": birth_date.strftime("%Y-%m-%d"),
        "governorate": governorate_name,
        "governorate_code": gov_code,
        "gender": gender
    }
    return True, info, "Valid Egyptian National ID"


def validate_invoice_math(
    subtotal: Optional[float],
    tax: Optional[float],
    discount: Optional[float],
    total: Optional[float],
    tolerance: float = 0.05
) -> Tuple[bool, Optional[str]]:
    """
    Checks if subtotal + tax - discount == total within numeric tolerance.
    """
    if total is None:
        return True, "No total provided to validate"

    # If subtotal is present, check relation
    if subtotal is not None:
        calc_total = subtotal + (tax or 0.0) - (discount or 0.0)
        diff = abs(calc_total - total)
        if diff <= tolerance:
            return True, f"Consistent: {subtotal} + {tax or 0.0} - {discount or 0.0} == {total}"
        else:
            return False, f"Inconsistent totals: subtotal({subtotal}) + tax({tax or 0.0}) - discount({discount or 0.0}) = {calc_total:.2f} != total({total})"

    return True, "Insufficient numerical components to verify math"


def validate_passport_number(passport_num: str) -> Tuple[bool, Optional[str]]:
    """
    Validates standard passport number alphanumeric formats.
    """
    if not passport_num:
        return False, "Passport number is empty"

    cleaned = passport_num.strip().upper()
    if not re.match(r'^[A-Z0-9]{7,10}$', cleaned):
        return False, f"Passport number '{passport_num}' does not match standard pattern [A-Z0-9]{{7,10}}"

    return True, "Valid passport pattern"


def compute_mrz_check_digit(data: str) -> int:
    """
    Calculates ICAO Doc 9303 check digit using weights 7, 3, 1 repeating.
    """
    weights = [7, 3, 1]
    total = 0
    for i, char in enumerate(data):
        w = weights[i % 3]
        if char.isdigit():
            val = int(char)
        elif 'A' <= char <= 'Z':
            val = ord(char) - ord('A') + 10
        elif char == '<':
            val = 0
        else:
            val = 0
        total += val * w
    return total % 10


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    if not email:
        return False, "Empty email"
    if re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}$', email.strip()):
        return True, "Valid email"
    return False, f"Invalid email format: {email}"


def validate_phone(phone: str) -> Tuple[bool, Optional[str]]:
    if not phone:
        return False, "Empty phone"
    cleaned = re.sub(r'[\s\-().]', '', phone)
    # Generic phone length check
    if 7 <= len(cleaned) <= 15:
        return True, "Valid phone number"
    return False, f"Plausible phone length violated: {len(cleaned)} digits"
