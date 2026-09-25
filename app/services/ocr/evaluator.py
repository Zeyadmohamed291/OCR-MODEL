import re
from typing import Dict, Any, List, Tuple, Optional
from app.domain.schemas.core import OCRResult, TextBlock, BoundingBox

def detect_script(text: str) -> str:
    """Classifies script of a single text block."""
    if not text:
        return "unknown"
    arabic = len(re.findall(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', text))
    latin = len(re.findall(r'[a-zA-Z]', text))
    digits = len(re.findall(r'[0-9\u0660-\u0669]', text))
    
    if arabic > 0 and latin > 0:
        return "mixed"
    elif arabic > 0:
        return "ar"
    elif latin > 0:
        return "latin"
    elif digits > 0:
        return "numeric"
    return "symbol"

def evaluate_detection_quality(result: OCRResult) -> Dict[str, Any]:
    """
    Evaluates OCR result quality using multiple signals:
    - Average and median confidence
    - Text coherence and alphanumeric ratio
    - Character density and word lengths
    - Structured patterns (dates, numbers, codes)
    - Composite quality score in [0.0, 1.0]
    """
    if not result or not result.blocks:
        return {
            "composite_score": 0.0,
            "avg_confidence": 0.0,
            "coherence_ratio": 0.0,
            "block_count": 0,
            "char_count": 0
        }

    blocks = result.blocks
    block_count = len(blocks)
    all_text = " ".join(b.text for b in blocks)
    total_chars = len(all_text.replace(" ", ""))

    if total_chars == 0:
        return {
            "composite_score": 0.0,
            "avg_confidence": 0.0,
            "coherence_ratio": 0.0,
            "block_count": 0,
            "char_count": 0
        }

    # 1. Alphanumeric & Coherence Ratio
    meaningful_chars = len(re.findall(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFFa-zA-Z0-9\u0660-\u0669\u06F0-\u06F9]', all_text))
    coherence_ratio = meaningful_chars / max(total_chars, 1)

    # 2. Confidence Metric
    confidences = [b.confidence for b in blocks]
    avg_conf = sum(confidences) / len(confidences)

    # 3. Pattern Boost (presence of dates, phone numbers, codes, prices)
    has_structured_data = bool(re.search(r'\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{6,}|\+?20\d{8,10}|[A-Za-z0-9_-]+@[A-Za-z0-9.-]+)\b', all_text))
    pattern_boost = 0.1 if has_structured_data else 0.0

    # 4. Composite Quality Score
    # 35% confidence + 35% coherence + 15% text volume + 15% structured presence
    volume_score = min(1.0, total_chars / 60.0)
    composite_score = (0.35 * avg_conf) + (0.35 * coherence_ratio) + (0.15 * volume_score) + pattern_boost
    composite_score = round(min(1.0, max(0.0, composite_score)), 3)

    return {
        "composite_score": composite_score,
        "avg_confidence": round(avg_conf, 3),
        "coherence_ratio": round(coherence_ratio, 3),
        "block_count": block_count,
        "char_count": total_chars,
        "has_structured_data": has_structured_data
    }

def calculate_iou(box1: BoundingBox, box2: BoundingBox) -> float:
    """Calculates Intersection Over Union (IOU) between two bounding boxes."""
    x1_min = min(p[0] for p in box1.points)
    x1_max = max(p[0] for p in box1.points)
    y1_min = min(p[1] for p in box1.points)
    y1_max = max(p[1] for p in box1.points)

    x2_min = min(p[0] for p in box2.points)
    x2_max = max(p[0] for p in box2.points)
    y2_min = min(p[1] for p in box2.points)
    y2_max = max(p[1] for p in box2.points)

    inter_x1 = max(x1_min, x2_min)
    inter_y1 = max(y1_min, y2_min)
    inter_x2 = min(x1_max, x2_max)
    inter_y2 = min(y1_max, y2_max)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area1 = max(1.0, (x1_max - x1_min) * (y1_max - y1_min))
    area2 = max(1.0, (x2_max - x2_min) * (y2_max - y2_min))
    union_area = area1 + area2 - inter_area

    return inter_area / union_area

def select_or_merge_passes(
    primary: OCRResult,
    secondary: Optional[OCRResult] = None
) -> Tuple[OCRResult, str]:
    """
    Intelligently selects the superior OCR result or performs complementary merging.
    Never relies on confidence alone.
    """
    if not secondary or not secondary.blocks:
        return primary, "primary"

    if not primary or not primary.blocks:
        return secondary, "secondary"

    q_a = evaluate_detection_quality(primary)
    q_b = evaluate_detection_quality(secondary)

    score_a = q_a["composite_score"]
    score_b = q_b["composite_score"]

    # If one pass is nearly empty (< 2 blocks) and the other is rich (>= 4 blocks), pick the rich pass
    if q_a["block_count"] <= 1 and q_b["block_count"] >= 4:
        return secondary, "secondary"
    if q_b["block_count"] <= 1 and q_a["block_count"] >= 4:
        return primary, "primary"

    # Base pass is the one with higher composite quality
    base_result = primary if score_a >= score_b else secondary
    base_name = "primary" if score_a >= score_b else "secondary"
    other_result = secondary if score_a >= score_b else primary

    # Check for complementary merging:
    # Add blocks from other_result that are high confidence (>= 0.60) and don't overlap with base blocks
    merged_blocks = list(base_result.blocks)
    merged_any = False

    for b_other in other_result.blocks:
        if b_other.confidence < 0.60:
            continue
        overlaps = any(calculate_iou(b_other.box, b_base.box) > 0.18 for b_base in merged_blocks)
        if not overlaps:
            merged_blocks.append(b_other)
            merged_any = True

    if merged_any:
        total_conf = sum(b.confidence for b in merged_blocks)
        avg_conf = total_conf / len(merged_blocks)
        merged_result = OCRResult(
            blocks=merged_blocks,
            total_time_ms=primary.total_time_ms + secondary.total_time_ms,
            average_confidence=round(avg_conf, 3),
            image_width=base_result.image_width,
            image_height=base_result.image_height,
            raw_output=base_result.raw_output
        )
        return merged_result, "merged"

    return base_result, base_name
