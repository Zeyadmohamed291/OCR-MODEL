"""
Backwards-compatible wrapper delegating to app.services.extraction.id_card
"""
from typing import Optional, Dict, Tuple
from app.services.extraction.id_card import (
    EGYPTIAN_GOVERNORATES,
    ADDRESS_KEYWORDS,
    is_valid_egyptian_id,
    IDCardExtractor
)

def extract_id_fields(text: str) -> Dict[str, Optional[str]]:
    return IDCardExtractor.extract_id_fields(text)

