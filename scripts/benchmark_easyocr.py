"""Reproducible local OCR benchmark; synthetic degradations are not independent documents.

Run from repository root: python -m scripts.benchmark_easyocr --output path.json
"""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from app.infrastructure.ocr.easyocr_engine import EasyOCREngine
from app.services.image_processing.quality import analyze_image_quality
from app.services.image_processing.preprocessor import AdaptivePreprocessor
from app.services.layout.reading_order import organize_reading_order
from app.services.layout.layout_analyzer import LayoutAnalyzer
from app.services.ocr.evaluator import evaluate_detection_quality
from app.services.ocr.passes import run_ocr_passes
from app.services.ocr.metrics import text_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=Path('artifacts/easyocr_validation/source.jpg'))
    parser.add_argument('--expected', type=Path, default=Path('artifacts/easyocr_validation/expected.txt'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    image = cv2.imread(str(args.image))
    if image is None:
        raise ValueError('Cannot decode benchmark image')
    expected = args.expected.read_text(encoding='utf-8').strip()
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), 5, 1)
    # Expanded canvas preserves all text in the skewed sample.
    nw, nh = int(w * abs(matrix[0, 0]) + h * abs(matrix[0, 1])) + 2, int(h * abs(matrix[0, 0]) + w * abs(matrix[0, 1])) + 2
    matrix[0, 2] += nw / 2 - w / 2
    matrix[1, 2] += nh / 2 - h / 2
    rng = np.random.default_rng(42)
    samples = {
        'original': image,
        'blur': cv2.GaussianBlur(image, (3, 3), 0.7),
        'low_contrast': np.clip(image.astype(float) * .30 + 145, 0, 255).astype(np.uint8),
        'noise': np.clip(image.astype(float) + rng.normal(0, 7, image.shape), 0, 255).astype(np.uint8),
        'skew_5': cv2.warpAffine(image, matrix, (nw, nh), borderValue=(255, 255, 255)),
        'rotation_90': cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
        'small': cv2.resize(image, None, fx=.65, fy=.65, interpolation=cv2.INTER_AREA),
    }
    engine = EasyOCREngine()  # Model load excluded from timings.
    rows = []
    for name, sample in samples.items():
        start = time.perf_counter()
        quality = analyze_image_quality(sample)
        primary, variants = AdaptivePreprocessor.preprocess_adaptive(sample, quality)
        result, _, attempts = run_ocr_passes(engine, primary, variants, quality)
        calls = len(attempts)
        ordered = organize_reading_order(result.blocks, result.image_width)
        layout, _, _ = LayoutAnalyzer.analyze(ordered, result.image_width, result.image_height)
        actual = '\n'.join(line.text for line in layout.lines)
        rows.append(dict(id=name, expected_text=expected, actual_text=actual,
                         metrics=text_metrics(expected, actual), calls=calls,
                         latency_ms=round((time.perf_counter()-start)*1000, 2),
                         confidence=result.average_confidence,
                         raw_blocks=[dict(text=b.raw_text, confidence=b.confidence, box=b.box.points) for b in ordered]))
        args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print(name, rows[-1]['metrics'], 'calls', calls, flush=True)


if __name__ == '__main__':
    main()
