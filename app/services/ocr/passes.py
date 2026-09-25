"""Bounded, shared OCR routing for API, Gradio and document pages."""
import logging

import cv2
import numpy as np

from app.core.config import settings
from app.core.exceptions import OCRFailureError
from app.domain.schemas.core import OCRResult
from app.services.ocr.evaluator import evaluate_detection_quality

logger = logging.getLogger("ocr_microservice")


def run_ocr_passes(engine, primary, variants, quality):
    """Return (selected result, transform, attempted variants).

    At most four full-page calls: primary + three orientations for very weak
    text, or primary + one original-image fallback for other weak results.
    Confidence is a routing signal, never proof that the text is correct.
    """
    transform = variants.get("primary_transform")
    if np.ptp(primary) == 0:
        quality.warnings.append("No visible contrast; no text can be read from this image.")
        return OCRResult(blocks=[], total_time_ms=0, average_confidence=0,
                         image_width=primary.shape[1], image_height=primary.shape[0]), transform, []

    best = engine.process_image(primary)
    attempts = ["primary"]
    initial = evaluate_detection_quality(best)
    best_score = initial["composite_score"]
    confidences = [b.confidence for b in best.blocks]
    weak_fraction = sum(c < settings.CONFIDENCE_THRESHOLD for c in confidences) / max(len(confidences), 1)
    # Arabic/English lines have horizontal geometry. A page full of tall
    # detections can score deceptively well on individual rotated glyphs.
    vertical_fraction = sum(b.box.height > max(b.box.width, 1) * 1.5 for b in best.blocks) / max(len(best.blocks), 1)
    vertical_text = len(best.blocks) >= 3 and vertical_fraction >= .60
    very_weak = not best.blocks or initial["avg_confidence"] < settings.OCR_ORIENTATION_CONFIDENCE or vertical_text
    weak = very_weak or initial["avg_confidence"] < settings.OCR_RETRY_CONFIDENCE or weak_fraction >= .30 or best_score < .50

    # Rotate the bounded primary image, never an unbounded full-resolution
    # upload. Rotate the page before detection so vertical text can be found.
    if very_weak:
        candidates = [("rotate_90", 90, cv2.ROTATE_90_CLOCKWISE),
                      ("rotate_270", 270, cv2.ROTATE_90_COUNTERCLOCKWISE),
                      ("rotate_180", 180, cv2.ROTATE_180)]
    elif weak and "original" in variants:
        candidates = [("original", 0, None)]
    else:
        candidates = []

    for name, angle, rotation in candidates:
        if rotation is None:
            image = variants["original"]
            if np.array_equal(primary, image):
                continue
            # Large originals must still be eligible for the fallback, but
            # keep the retry within the same inference memory budget.
            largest = max(image.shape[:2])
            if largest > settings.OCR_CANVAS_SIZE:
                scale = settings.OCR_CANVAS_SIZE / largest
                image = cv2.resize(
                    image,
                    (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            elif largest <= 1200:
                # A conditional high-resolution retry gives small, uncertain
                # print more recognizer pixels. It is deliberately limited to
                # the fallback path so clean images pay no extra processing.
                scale = min(1.5, settings.OCR_CANVAS_SIZE / largest)
                image = cv2.resize(
                    image,
                    (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))),
                    interpolation=cv2.INTER_CUBIC,
                )
            candidate_transform = variants.get("original_transform")
            if candidate_transform:
                candidate_transform = dict(candidate_transform)
                candidate_transform.update(width=image.shape[1], height=image.shape[0])
        else:
            image = cv2.rotate(primary, rotation)
            candidate_transform = dict(variants.get("primary_transform") or {})
            candidate_transform.update(width=image.shape[1], height=image.shape[0],
                                       geometry_corrected=True, rotation=angle)
        attempts.append(name)
        try:
            alternate = engine.process_image(image)
        except OCRFailureError:
            # A failed optional pass must not discard an already available read.
            quality.warnings.append(f"Optional OCR pass {name} failed; retained available result.")
            logger.warning("Optional OCR pass %s failed", name, exc_info=True)
            continue
        score = evaluate_detection_quality(alternate)["composite_score"]
        if score > best_score and alternate.blocks:
            best, best_score, transform = alternate, score, candidate_transform
            if angle:
                quality.detected_orientation = angle
        # Stop orientation search once a clearly readable candidate is found.
        if angle and alternate.average_confidence >= .80 and score >= .70:
            break

    if not best.blocks:
        quality.warnings.append("No readable text detected after bounded OCR attempts.")
    elif any(b.confidence < settings.CONFIDENCE_THRESHOLD for b in best.blocks):
        quality.warnings.append("Some text has low OCR confidence and requires review.")
    return best, transform, attempts
