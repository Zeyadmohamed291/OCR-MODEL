import logging
from typing import Optional, Dict
from app.domain.interfaces.ocr_engine import AbstractOCREngine
from app.core.exceptions import ValidationFailureError

logger = logging.getLogger("ocr_microservice")

# Engine registry cache
_engines: Dict[str, AbstractOCREngine] = {}

def get_ocr_engine_by_name(provider: Optional[str] = None) -> AbstractOCREngine:
    """
    Returns the local EasyOCR engine. Unsupported providers fail explicitly.
    """
    prov = (provider or "easy").lower().strip()
    if prov not in ("easy", "easyocr"):
        raise ValidationFailureError("Only the local EasyOCR provider is enabled.")
    prov = "easy"
    
    if prov not in _engines:
        logger.info("Initializing EasyOCREngine.")
        from app.infrastructure.ocr.easyocr_engine import EasyOCREngine
        _engines[prov] = EasyOCREngine()
            
    return _engines[prov]

def get_ocr_engine() -> AbstractOCREngine:
    """
    Default dependency injection entrypoint for FastAPI routers.
    """
    return get_ocr_engine_by_name()


def is_ocr_engine_initialized() -> bool:
    return "easy" in _engines
