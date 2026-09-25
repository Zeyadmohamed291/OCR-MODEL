import re
from typing import Tuple, Dict

class LanguageDetector:
    """
    Analyzes document text to determine linguistic script and mixture.
    Supports pure Arabic, pure English, mixed Arabic-English, numeric, or unknown.
    """

    ARABIC_LETTER_PATTERN = re.compile(r'[\u0620-\u064A\u0671-\u06D3\u06D5\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFC]')
    # Keep backwards-compatible ARABIC_PATTERN alias excluding digits
    ARABIC_PATTERN = ARABIC_LETTER_PATTERN
    LATIN_PATTERN = re.compile(r'[a-zA-Z]')
    DIGIT_PATTERN = re.compile(r'[0-9\u0660-\u0669\u06F0-\u06F9]')

    @classmethod
    def detect(cls, text: str) -> Tuple[str, float, Dict[str, float]]:
        if not text or not text.strip():
            return "unknown", 0.0, {"arabic": 0.0, "latin": 0.0, "digits": 0.0}

        arabic_count = len(cls.ARABIC_LETTER_PATTERN.findall(text))
        latin_count = len(cls.LATIN_PATTERN.findall(text))
        digit_count = len(cls.DIGIT_PATTERN.findall(text))
        total_meaningful = arabic_count + latin_count + digit_count

        if total_meaningful == 0:
            return "unknown", 0.0, {"arabic": 0.0, "latin": 0.0, "digits": 0.0}

        ar_ratio = arabic_count / total_meaningful
        en_ratio = latin_count / total_meaningful
        num_ratio = digit_count / total_meaningful

        distribution = {
            "arabic": round(ar_ratio, 2),
            "latin": round(en_ratio, 2),
            "digits": round(num_ratio, 2)
        }

        # Mixed detection: significant presence of both Arabic and Latin
        if arabic_count > 0 and latin_count > 0:
            lang = "ar-en"
            confidence = min(1.0, round(ar_ratio + en_ratio, 2))
        elif arabic_count > 0:
            lang = "ar"
            confidence = max(0.6, round(ar_ratio, 2))
        elif latin_count > 0:
            lang = "en"
            confidence = max(0.6, round(en_ratio, 2))
        elif digit_count > 0:
            lang = "numeric"
            confidence = round(num_ratio, 2)
        else:
            lang = "unknown"
            confidence = 0.5

        return lang, round(confidence, 2), distribution

    @classmethod
    def detect_direction(cls, text: str) -> str:
        """
        Determines the logical reading direction:
        - 'rtl': Confidently Arabic-only text blocks.
        - 'ltr': Confidently English-only, numeric, code, date, email, or URL blocks.
        - 'auto': Mixed Arabic-English or Arabic-numeric text where native Bidi isolation is needed.
        """
        if not text or not text.strip():
            return "ltr"

        arabic_count = len(cls.ARABIC_LETTER_PATTERN.findall(text))
        latin_count = len(cls.LATIN_PATTERN.findall(text))
        digit_count = len(cls.DIGIT_PATTERN.findall(text))

        # Mixed Arabic and Latin or Arabic and numbers
        if arabic_count > 0 and (latin_count > 0 or digit_count > 0):
            return "auto"

        # Pure Arabic (letters + punctuation/whitespace)
        if arabic_count > 0:
            return "rtl"

        # Pure Latin, numeric, codes, dates, or symbols
        return "ltr"

    @classmethod
    def detect_script(cls, text: str) -> str:
        """
        Classifies script into 'arabic', 'latin', 'numeric', 'mixed', or 'unknown'.
        """
        if not text or not text.strip():
            return "unknown"

        arabic_count = len(cls.ARABIC_LETTER_PATTERN.findall(text))
        latin_count = len(cls.LATIN_PATTERN.findall(text))
        digit_count = len(cls.DIGIT_PATTERN.findall(text))

        if arabic_count > 0 and latin_count > 0:
            return "mixed"
        if arabic_count > 0:
            return "arabic"
        if latin_count > 0:
            return "latin"
        if digit_count > 0:
            return "numeric"
        return "unknown"
