import re
from typing import Dict, Any, List, Optional
from app.domain.schemas.core import StructuredField
from app.services.language.language_detector import LanguageDetector

# Disallowed / dangerous bidirectional overrides that forcibly invert visual rendering
BIDI_OVERRIDES = re.compile(r'[\u202A-\u202E\u2066-\u2069]')

def normalize_logical_text(text: str) -> str:
    """
    Cleans up whitespace and replaces non-standard space characters
    WITHOUT ANY character or word reversals.
    Preserves strict logical Unicode order.
    """
    if not text:
        return ""
    
    # Strip any invisible Bidi override control codes
    cleaned = BIDI_OVERRIDES.sub('', text)
    
    # Normalize Unicode whitespace (non-breaking space, thin space, zero-width)
    cleaned = cleaned.replace('\u00A0', ' ').replace('\u202F', ' ').replace('\u200B', '')
    
    # Collapse multiple spaces on a single line, but preserve intentional line breaks
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in cleaned.splitlines()]
    return "\n".join(lines).strip()

def is_bidi_safe(text: str) -> bool:
    """
    Verifies that text does not contain forced directional overrides.
    """
    if not text:
        return True
    return not bool(BIDI_OVERRIDES.search(text))

def find_source_bbox(
    val_str: str,
    label_str: Optional[str] = None,
    layout: Optional[Any] = None
) -> Optional[List[List[float]]]:
    """Finds matching layout line bounding box for an extracted value or label."""
    if not layout or not hasattr(layout, 'lines') or not layout.lines or not val_str:
        return None

    val_clean = val_str.strip().lower()
    if not val_clean:
        return None

    # First attempt: match by value
    for line in layout.lines:
        line_text = line.text.lower()
        if val_clean in line_text:
            if hasattr(line, 'bbox') and line.bbox:
                return line.bbox
            if hasattr(line, 'box') and line.box:
                return [[float(p[0]), float(p[1])] for p in line.box.points]

    # Second attempt: match by label
    if label_str:
        lbl_clean = label_str.strip().lower()
        for line in layout.lines:
            if lbl_clean in line.text.lower():
                if hasattr(line, 'bbox') and line.bbox:
                    return line.bbox
                if hasattr(line, 'box') and line.box:
                    return [[float(p[0]), float(p[1])] for p in line.box.points]

    return None

def build_structured_field(
    label: Optional[str],
    value: Any,
    confidence: float = 1.0,
    field_name: Optional[str] = None,
    source_bbox: Optional[List[List[float]]] = None,
    is_valid: bool = True,
    validation_note: Optional[str] = None
) -> StructuredField:
    """
    Builds a StructuredField with automatic language, direction, spatial bounding box, and validation state.
    """
    val_str = str(value) if value is not None else ""
    val_clean = normalize_logical_text(val_str)
    
    lang, _, _ = LanguageDetector.detect(val_clean)
    direction = LanguageDetector.detect_direction(val_clean)
    
    return StructuredField(
        label=label,
        value=value,
        raw_value=val_str,
        source_bbox=source_bbox,
        language=lang,
        direction=direction,
        confidence=round(confidence, 2),
        field_name=field_name,
        is_valid=is_valid,
        validation_note=validation_note
    )

def convert_dict_to_structured_fields(
    fields_dict: Dict[str, Any],
    confidence: float = 1.0,
    layout: Optional[Any] = None
) -> List[StructuredField]:
    """
    Transforms extracted key-value dictionary into structured fields with source bounding boxes,
    utilizing field-level confidences and validation flags when available.
    """
    if not fields_dict:
        return []

    structured: List[StructuredField] = []
    field_confidences = fields_dict.get("_field_confidences", {})
    field_metadata = fields_dict.get("_field_metadata", {})
    
    for k, v in fields_dict.items():
        if k in ("key_values", "_structured", "_field_confidences", "_field_metadata") or v is None:
            continue
            
        label_text = k.replace("_", " ").title()
        meta = field_metadata.get(k, {})
        f_conf = meta.get("confidence", field_confidences.get(k, confidence))
        is_valid = meta.get("is_valid", True)
        note = meta.get("validation_note", None)
        
        # Handle list of items (e.g. emails, phones, urls, clauses, skills)
        if isinstance(v, list):
            for item in v:
                bbox = find_source_bbox(str(item), label_text, layout)
                field = build_structured_field(
                    label=label_text,
                    value=item,
                    confidence=f_conf,
                    field_name=k,
                    source_bbox=bbox,
                    is_valid=is_valid,
                    validation_note=note
                )
                structured.append(field)
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                bbox = find_source_bbox(str(sub_v), sub_k, layout)
                sub_meta = meta.get(sub_k, {}) if isinstance(meta, dict) else {}
                sub_conf = sub_meta.get("confidence", f_conf)
                sub_valid = sub_meta.get("is_valid", is_valid)
                sub_note = sub_meta.get("validation_note", note)
                field = build_structured_field(
                    label=sub_k,
                    value=sub_v,
                    confidence=sub_conf,
                    field_name=f"{k}.{sub_k}",
                    source_bbox=bbox,
                    is_valid=sub_valid,
                    validation_note=sub_note
                )
                structured.append(field)
        else:
            bbox = find_source_bbox(str(v), label_text, layout)
            field = build_structured_field(
                label=label_text,
                value=v,
                confidence=f_conf,
                field_name=k,
                source_bbox=bbox,
                is_valid=is_valid,
                validation_note=note
            )
            structured.append(field)
            
    # Handle explicit key_values if present
    if "key_values" in fields_dict and isinstance(fields_dict["key_values"], dict):
        for k, v in fields_dict["key_values"].items():
            bbox = find_source_bbox(str(v), k, layout)
            field = build_structured_field(
                label=k,
                value=v,
                confidence=confidence,
                field_name="key_value",
                source_bbox=bbox
            )
            structured.append(field)

    return structured
