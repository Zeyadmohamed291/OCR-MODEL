import re
from typing import Dict, Any, Optional
from app.services.extraction.base import BaseExtractor

class FormExtractor(BaseExtractor):
    """Extractor for Application and Registration Forms."""
    def extract(self, text: str, layout: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        fields: Dict[str, Any] = {"form_title": None, "form_fields": {}}
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            fields["form_title"] = lines[0]
        for line in lines:
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if 1 <= len(k.split()) <= 4 and k:
                    fields["form_fields"][k] = v or None
        return {k: v for k, v in fields.items() if v}

class ReportExtractor(BaseExtractor):
    """Extractor for Official and Technical Reports."""
    def extract(self, text: str, layout: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        fields: Dict[str, Any] = {"report_title": None, "date": None, "author": None}
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            fields["report_title"] = lines[0]
        d_match = re.search(r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', text)
        if d_match:
            fields["date"] = d_match.group(1)
        author_match = re.search(r'(?:prepared\s*by|author|إعداد|بواسطة)\s*[:=]?\s*([A-Za-z\u0600-\u06FF\s]+)', text, re.IGNORECASE)
        if author_match:
            fields["author"] = author_match.group(1).splitlines()[0].strip()
        return {k: v for k, v in fields.items() if v}

class CertificateExtractor(BaseExtractor):
    """Extractor for Certificates and Awards."""
    def extract(self, text: str, layout: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        fields: Dict[str, Any] = {"recipient": None, "title": None, "issuer": None, "date": None}
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for l in lines[:3]:
            if any(kw in l.lower() for kw in ["certificate", "شهادة", "تقدير", "diploma", "award"]):
                fields["title"] = l
                break
        recip_match = re.search(r'(?:awarded\s*to|certified\s*that|منحت\s*(?:إلى|للسيد|للطالب)|تشهد\s*بأن)\s*[:=]?\s*([A-Za-z\u0600-\u06FF\s]+)', text, re.IGNORECASE)
        if recip_match:
            fields["recipient"] = recip_match.group(1).splitlines()[0].strip()
        d_match = re.search(r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', text)
        if d_match:
            fields["date"] = d_match.group(1)
        return {k: v for k, v in fields.items() if v}

class LetterExtractor(BaseExtractor):
    """Extractor for Formal Letters and Correspondence."""
    def extract(self, text: str, layout: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        fields: Dict[str, Any] = {"sender": None, "recipient": None, "date": None, "subject": None}
        recip_match = re.search(r'(?:السيد\s*/|عناية\s*/|to\s*:|dear\s+)([A-Za-z\u0600-\u06FF\s]+)', text, re.IGNORECASE)
        if recip_match:
            fields["recipient"] = recip_match.group(1).splitlines()[0].strip()
        subj_match = re.search(r'(?:الموضوع|subject|re)\s*[:=]?\s*([^\n]+)', text, re.IGNORECASE)
        if subj_match:
            fields["subject"] = subj_match.group(1).strip()
        d_match = re.search(r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', text)
        if d_match:
            fields["date"] = d_match.group(1)
        return {k: v for k, v in fields.items() if v}

class ScreenshotExtractor(BaseExtractor):
    """Extractor for Screenshots and Screen Captures."""
    def extract(self, text: str, layout: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        fields: Dict[str, Any] = {"detected_urls": [], "detected_timestamps": []}
        urls = re.findall(r'(?:https?://\S+|www\.\S+)', text)
        if urls:
            fields["detected_urls"] = list(dict.fromkeys(urls))
        times = re.findall(r'\b(?:[01]?\d|2[0-3]):[0-5]\d\s*(?:AM|PM|am|pm)?\b', text)
        if times:
            fields["detected_timestamps"] = list(dict.fromkeys(times))
        return {k: v for k, v in fields.items() if v}

class TableExtractor(BaseExtractor):
    """Extractor for Standalone Tables."""
    def extract(self, text: str, layout: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        fields: Dict[str, Any] = {"headers": [], "row_count": 0}
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            headers = [p.strip() for p in lines[0].split("|") if p.strip()] or lines[0].split()
            fields["headers"] = headers
            fields["row_count"] = max(0, len(lines) - 1)
        return {k: v for k, v in fields.items() if v}
