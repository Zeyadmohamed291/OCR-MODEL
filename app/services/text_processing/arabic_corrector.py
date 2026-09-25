# -*- coding: utf-8 -*-
"""
Intelligent Arabic Domain & OCR Post-Corrector.
Specifically targets Arabic OCR character confusions, calligraphy distortions,
and Egyptian administrative/ID card patterns.
"""
import re
from typing import List, Tuple, Optional, Dict, Any

ARABIC_DIACRITICS_REGEX = re.compile(r'[\u0617-\u061A\u064B-\u0652]')

def strip_tashkeel(text: str) -> str:
    """Removes Arabic diacritical marks (harakat/tashkeel)."""
    return ARABIC_DIACRITICS_REGEX.sub('', text)


class ArabicOCRCorrector:
    """
    Production-grade Arabic OCR post-processing corrector.
    Fixes:
      1. Distorted calligraphic headers (e.g. "جمهورية مصر العربية")
      2. Card titles (e.g. "بطاقة تحقيق الشخصية")
      3. Common Arabic character shape confusions in personal names (e.g. محمل -> محمد, عبا -> عبد)
      4. Egyptian Governorates and administrative keywords
      5. Stray OCR artifacts and broken spacing
    """

    # 1. Distorted header regex patterns -> Canonical Form
    OFFICIAL_HEADER_PATTERNS = [
        re.compile(r'(?:جمهو|جمعو|جهود|جمهز|جمهذ|جمع|جمو|هوز|نههو|نهز|مهو|كزه|كنذ)[^\n]{0,35}(?:بينمنا|بينا|بيغنما|للجمعية|العربية|العربيه|مصر|صنالج|صزالح|صزالع|خنالع|خنالح|تذف|كنذف|مصير|العزيز)', re.UNICODE),
        re.compile(r'\b(?:صنالج|صزالح|صزالع|خنالع|خنالح|كنذف|بينمنا|بيغنما)\b', re.UNICODE),
        re.compile(r'(?:نههوز|هوزكز|جمهوز|جمعوز)[^\n]{0,25}(?:بينا|بينمنا|صزالح|صنالج|صزالع)', re.UNICODE),
        re.compile(r'.*(?:جمهورية\s*مصر\s*العربية|جمهورية\s*مصر).*', re.UNICODE),
    ]

    CARD_TITLE_PATTERNS = [
        re.compile(r'^(?:بطاق[ةه]|نطاق[ةه]|بطا[ف|ق][ةه]|بطافه)\s*(?:تحقيق|تحديق|تحفيق)?\s*(?:الشخصي[ةه]|الشخصيه|الشخصية)', re.UNICODE),
        re.compile(r'^(?:تحقيق\s+الشخصي[ةه])', re.UNICODE),
        re.compile(r'^(?:بطاقة\s*تحقيق|بطاقه\s*تحقيق)', re.UNICODE),
        re.compile(r'^\bبطاق[ةه]\s+الشخصي[ةه]\b', re.UNICODE),
    ]

    # 2. Common Egyptian Governorates normalization map
    GOVERNORATE_CANONICAL = {
        "الاسكندرية": "الإسكندرية",
        "الاسكندريه": "الإسكندرية",
        "القاهره": "القاهرة",
        "الجيزه": "الجيزة",
        "الدقهليه": "الدقهلية",
        "الشرقيه": "الشرقية",
        "القليوبيه": "القليوبية",
        "كفرالشيخ": "كفر الشيخ",
        "الغربيه": "الغربية",
        "المنوفيه": "المنوفية",
        "البحيره": "البحيرة",
        "الاسماعيليه": "الإسماعيلية",
        "الاسماعيلية": "الإسماعيلية",
        "السويس": "السويس",
        "بورسعيد": "بورسعيد",
        "دمياط": "دمياط",
        "الفيوم": "الفيوم",
        "بنى سويف": "بني سويف",
        "المنيا": "المنيا",
        "اسيوط": "أسيوط",
        "سوهاج": "سوهاج",
        "قنا": "قنا",
        "اسوان": "أسوان",
        "الاقصر": "الأقصر",
        "البحر الاحمر": "البحر الأحمر",
        "الوادى الجديد": "الوادي الجديد",
        "مطروح": "مطروح",
        "شمال سيناء": "شمال سيناء",
        "جنوب سيناء": "جنوب سيناء"
    }

    # 3. Common Arabic Personal Name OCR Corrections (Terminal 'ل' vs 'د', prefix 'عبا' vs 'عبد')
    NAME_TERMINAL_SUBSTITUTIONS = [
        (r'\bمحمل\b', 'محمد'),
        (r'\bأحمل\b', 'أحمد'),
        (r'\bاحمل\b', 'أحمد'),
        (r'\bمحمول\b', 'محمود'),
        (r'\bسعيل\b', 'سعيد'),
        (r'\bماجل\b', 'ماجد'),
        (r'\bخالل\b', 'خالد'),
        (r'\bخالـل\b', 'خالد'),
        (r'\bوليل\b', 'وليد'),
        (r'\bمجل\b', 'مجد'),
        (r'\bمرال\b', 'مراد'),
        (r'\bسعل\b', 'سعد'),
        (r'\bراشل\b', 'راشد'),
        (r'\bزاهل\b', 'زاهد'),
        (r'\bطارف\b', 'طارق'),
        (r'\bصالـح\b', 'صالح'),
        (r'\bابراهيم\b', 'إبراهيم'),
        (r'\bاسماعيل\b', 'إسماعيل'),
        (r'\bايمن\b', 'أيمن'),
        (r'\bاشرف\b', 'أشرف'),
    ]

    # 'عبا' before a divine attribute in composite names -> 'عبد'
    ABD_PREFIX_REGEX = re.compile(
        r'\bعبا\s+(الشفيع|الرحمن|الله|الرحيم|العزيز|الكريم|الفتاح|الوهاب|الرزاق|العليم|السميع|البصير|الحكيم|القدوس|السلام|المؤمن|المهيمن|الجبار|المتكبر|الخالق|الغفار|القادر|المجيد|الودود|الرؤوف|الصبور|الحميد|المجيب|الواسع|المتين|الوكيل|الحي|القيوم|الباسط|المعز|المذل|العدل|اللطيف|الخبير|الحليم|العظيم|الغفور|الشكور|العلي|الكبير|الحفيظ|المقيت|الحسيب|الجليل)\b',
        re.UNICODE
    )

    @classmethod
    def is_card_title(cls, text: str) -> bool:
        clean = strip_tashkeel(text.strip())
        return any(pattern.search(clean) for pattern in cls.CARD_TITLE_PATTERNS)

    @classmethod
    def correct_line(cls, line_text: str, line_index: int = 0, total_lines: int = 1) -> str:
        """
        Corrects a single OCR line text based on context and positional heuristics.
        """
        if not line_text:
            return ""

        cleaned = line_text.strip()
        cleaned_no_tashkeel = strip_tashkeel(cleaned)

        # Step 1: Check if this is the top header of an Egyptian document
        if any(pattern.search(cleaned_no_tashkeel) for pattern in cls.OFFICIAL_HEADER_PATTERNS):
            if not any(kw in cleaned for kw in ["بطاقة", "بطاقه", "تحقيق", "الشخصية", "الشخصيه"]):
                return "جمهورية مصر العربية"

        if any(pattern.search(cleaned_no_tashkeel) for pattern in cls.CARD_TITLE_PATTERNS):
            return "بطاقة تحقيق الشخصية"

        # Step 2: Fix 'عبا' -> 'عبد' in composite names
        cleaned = cls.ABD_PREFIX_REGEX.sub(r'عبد \1', cleaned)

        # Step 3: Fix common terminal character confusions in names
        for pattern, replacement in cls.NAME_TERMINAL_SUBSTITUTIONS:
            cleaned = re.sub(pattern, replacement, cleaned)

        # Step 4: Fix address / governorate names
        for typo, canonical in cls.GOVERNORATE_CANONICAL.items():
            cleaned = re.sub(rf'\b{typo}\b', canonical, cleaned)

        # Step 5: Clean spurious punctuation artifacts attached to Arabic words
        cleaned = re.sub(r'[؛«»^~|_]+', ' ', cleaned)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()

        return cleaned

    @classmethod
    def correct_text_block_lines(cls, lines: List[str]) -> List[str]:
        """
        Processes a list of text lines in sequence, applying contextual and lookahead adjustments.
        """
        corrected = []
        n = len(lines)
        
        for i, line in enumerate(lines):
            clean = line.strip()
            clean_no_tashkeel = strip_tashkeel(clean)
            
            # Header check (top 3 lines)
            if i <= 2 and not any(kw in clean for kw in ['بطاقة', 'بطاقه', 'تحقيق', 'الشخصية', 'الشخصيه']):
                if any(p.search(clean_no_tashkeel) for p in cls.OFFICIAL_HEADER_PATTERNS):
                    corrected.append('جمهورية مصر العربية')
                    continue
                # Lookahead: if next lines have card title keywords, this line is unconditionally the header
                if any(c in clean for c in "جمهورصالحبينمكذفنع") and len(clean) >= 3:
                    upcoming = " ".join(lines[i+1:min(i+3, n)])
                    if any(w in upcoming for w in ["بطاقة", "بطاقه", "تحقيق"]):
                        corrected.append("جمهورية مصر العربية")
                        continue
                    
            # Card title check
            if any(p.search(clean_no_tashkeel) for p in cls.CARD_TITLE_PATTERNS):
                corrected.append('بطاقة تحقيق الشخصية')
                continue
                
            # Clean noisy sub-word in card title if fragmented by EasyOCR
            if re.match(r'^تحقيق\s+[ا|\|\.]\s*$', clean):
                corrected.append('تحقيق')
                continue

            c_line = cls.correct_line(line, line_index=i, total_lines=n)
            corrected.append(c_line)
            
        return corrected
