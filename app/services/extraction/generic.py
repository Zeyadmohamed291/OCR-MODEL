import re
from typing import Dict, Any, List, Optional
from app.services.extraction.base import BaseExtractor
from app.services.extraction.validation import (
    validate_email,
    validate_phone,
    parse_and_validate_date,
    normalize_unicode_digits,
)

class GenericExtractor(BaseExtractor):
    """
    Universal entity and pattern extractor applicable to any document type.
    Extracts dates, emails, phone numbers, URLs, monetary amounts, and key-value pairs
    with independent field confidences and validation flags.
    """

    EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')
    URL_REGEX = re.compile(r'\b(?:https?://|www\.)[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?\b', re.IGNORECASE)
    
    # Phone numbers: Egyptian (010, 011, 012, 015), landlines, and international with '+'
    PHONE_REGEX = re.compile(r'(?:\+?20\s?|0020\s?|0)?(?:10|11|12|15)\d{8}\b|\+?[1-9]\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}')
    
    # Dates: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD
    DATE_REGEX = re.compile(r'\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b')
    
    # Amounts with currency
    AMOUNT_REGEX = re.compile(r'(?:(?:EGP|USD|EUR|GBP|SAR|AED|LE|L\.E|ج\.م|جنيه|دولار|ريال|درهم)\s*[:=]?\s*[\d,]+(?:\.\d{1,2})?|[\d,]+(?:\.\d{1,2})?\s*(?:EGP|USD|EUR|GBP|SAR|AED|LE|L\.E|ج\.م|جنيه|دولار|ريال|درهم))\b', re.IGNORECASE)

    def extract(
        self,
        text: str,
        layout: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not text:
            return {}

        results: Dict[str, Any] = {}

        # 1. Emails
        emails = list(dict.fromkeys(self.EMAIL_REGEX.findall(text)))
        if emails:
            is_valid_emails = all(validate_email(e)[0] for e in emails)
            self.set_field(results, "emails", emails, confidence=0.98 if is_valid_emails else 0.70, is_valid=is_valid_emails)

        # 2. URLs
        urls = list(dict.fromkeys(self.URL_REGEX.findall(text)))
        if urls:
            self.set_field(results, "urls", urls, confidence=0.96, is_valid=True)

        # 3. Phones
        phones = list(dict.fromkeys(self.PHONE_REGEX.findall(text)))
        if phones:
            clean_phones = [p.strip() for p in phones]
            is_valid_phones = all(validate_phone(p)[0] for p in clean_phones)
            self.set_field(results, "phones", clean_phones, confidence=0.95 if is_valid_phones else 0.65, is_valid=is_valid_phones)

        # 4. Dates
        dates = list(dict.fromkeys(self.DATE_REGEX.findall(normalize_unicode_digits(text))))
        if dates:
            is_valid_dates = any(parse_and_validate_date(d)[0] for d in dates)
            self.set_field(results, "dates", dates, confidence=0.95 if is_valid_dates else 0.60, is_valid=is_valid_dates)

        # 5. Monetary Amounts
        amounts = list(dict.fromkeys(self.AMOUNT_REGEX.findall(normalize_unicode_digits(text))))
        if amounts:
            self.set_field(results, "amounts", [a.strip() for a in amounts], confidence=0.94, is_valid=True)

        # 6. Key-Value Pairs (e.g. "Key: Value" or "Key = Value")
        kv_pairs = {}
        for line in text.splitlines():
            line_str = line.strip()
            if ":" in line_str and not line_str.startswith("http"):
                parts = line_str.split(":", 1)
                k, v = parts[0].strip(), parts[1].strip()
                if 1 <= len(k.split()) <= 4 and v and len(k) < 35:
                    kv_pairs[k] = v
            elif "=" in line_str:
                parts = line_str.split("=", 1)
                k, v = parts[0].strip(), parts[1].strip()
                if 1 <= len(k.split()) <= 4 and v and len(k) < 35:
                    kv_pairs[k] = v

        if kv_pairs:
            self.set_field(results, "key_values", kv_pairs, confidence=0.90, is_valid=True)

        return results
