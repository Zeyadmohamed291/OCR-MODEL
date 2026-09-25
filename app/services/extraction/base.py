import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

logger = logging.getLogger("ocr_microservice")

class BaseExtractor(ABC):
    """
    Abstract base class for all document-specific extractors.
    Each extractor receives raw OCR text, optional layout info, and metadata,
    and returns a clean, structured dictionary of extracted fields.
    Also tracks field-level confidences, validation states, and notes in `_field_metadata`.
    """

    @abstractmethod
    def extract(
        self,
        text: str,
        layout: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract structured fields from document text and layout.
        Must never raise exceptions; return empty or partial dict on missing fields.
        """
        pass

    def set_field(
        self,
        fields: Dict[str, Any],
        name: str,
        value: Any,
        confidence: float = 1.0,
        is_valid: bool = True,
        note: Optional[str] = None,
        source_bbox: Optional[List[List[float]]] = None
    ) -> None:
        """
        Registers a field value along with its field-level confidence and validation metadata.
        """
        if value is None:
            return

        fields[name] = value

        if "_field_confidences" not in fields:
            fields["_field_confidences"] = {}
        if "_field_metadata" not in fields:
            fields["_field_metadata"] = {}

        # Round confidence to 2 decimals
        conf = max(0.0, min(1.0, round(confidence, 2)))
        fields["_field_confidences"][name] = conf
        fields["_field_metadata"][name] = {
            "confidence": conf,
            "is_valid": is_valid,
            "validation_note": note,
            "source_bbox": source_bbox
        }

    def get_layout_confidence(self, snippet: str, layout: Optional[Any] = None, default: float = 0.90) -> float:
        """
        Attempts to find the underlying OCR confidence of a specific text snippet from layout lines/blocks.
        """
        if not layout or not snippet:
            return default

        cleaned_snippet = snippet.strip().lower()
        if hasattr(layout, "lines") and layout.lines:
            for line in layout.lines:
                if line.text and cleaned_snippet in line.text.lower():
                    return float(line.confidence) if line.confidence > 0 else default

        if hasattr(layout, "blocks") and layout.blocks:
            for block in layout.blocks:
                if block.text and cleaned_snippet in block.text.lower():
                    return float(block.confidence) if block.confidence > 0 else default

        return default
