import logging
from typing import Dict, Any, Optional
from app.services.extraction.base import BaseExtractor
from app.services.extraction.generic import GenericExtractor
from app.services.extraction.id_card import IDCardExtractor
from app.services.extraction.passport import PassportExtractor
from app.services.extraction.invoice import InvoiceExtractor
from app.services.extraction.receipt import ReceiptExtractor
from app.services.extraction.contract import ContractExtractor
from app.services.extraction.cv import CVExtractor
from app.services.extraction.driver_license import DriverLicenseExtractor
from app.services.extraction.bank_document import BankDocumentExtractor
from app.services.extraction.other_extractors import (
    FormExtractor, ReportExtractor, CertificateExtractor,
    LetterExtractor, ScreenshotExtractor, TableExtractor
)

logger = logging.getLogger("ocr_microservice")

class ExtractorRegistry:
    """
    Central dispatcher and registry for document extractors.
    Combines generic entity extraction with specialized document intelligence.
    """

    def __init__(self):
        self.generic_extractor = GenericExtractor()
        self._extractors: Dict[str, BaseExtractor] = {
            "id_card": IDCardExtractor(),
            "passport": PassportExtractor(),
            "invoice": InvoiceExtractor(),
            "receipt": ReceiptExtractor(),
            "contract": ContractExtractor(),
            "cv": CVExtractor(),
            "driver_license": DriverLicenseExtractor(),
            "bank_document": BankDocumentExtractor(),
            "form": FormExtractor(),
            "report": ReportExtractor(),
            "certificate": CertificateExtractor(),
            "letter": LetterExtractor(),
            "screenshot": ScreenshotExtractor(),
            "table": TableExtractor(),
            "image_with_text": self.generic_extractor,
            "generic_document": self.generic_extractor,
            "unknown": self.generic_extractor
        }

    def extract(
        self,
        document_type: str,
        text: str,
        layout: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes generic extraction + specialized extraction for the document type.
        Guarantees safe execution without crashing.
        """
        if not text:
            return {}

        results: Dict[str, Any] = {}

        def _merge_dict(target: Dict[str, Any], source: Dict[str, Any]) -> None:
            for k, v in source.items():
                if k in ("_field_confidences", "_field_metadata") and isinstance(v, dict):
                    if k not in target:
                        target[k] = {}
                    target[k].update(v)
                else:
                    target[k] = v

        # 1. Always run Generic Extractor to capture dates, emails, phones, URLs, amounts, KV pairs
        try:
            generic_fields = self.generic_extractor.extract(text, layout=layout, metadata=metadata)
            if generic_fields:
                _merge_dict(results, generic_fields)
        except Exception as e:
            logger.warning(f"Generic entity extraction encountered error: {e}", exc_info=True)

        # 2. Run Specialized Extractor for the document category
        extractor = self._extractors.get(document_type.lower().strip())
        if extractor and extractor != self.generic_extractor:
            try:
                specialized_fields = extractor.extract(text, layout=layout, metadata=metadata)
                if specialized_fields:
                    _merge_dict(results, specialized_fields)
            except Exception as e:
                logger.error(f"Specialized extractor for '{document_type}' encountered error: {e}", exc_info=True)

        return results

# Singleton instance
extractor_registry = ExtractorRegistry()
