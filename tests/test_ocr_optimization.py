import pytest
import numpy as np
import cv2
from app.domain.schemas.core import TextBlock, BoundingBox, OCRResult
from app.services.ocr.evaluator import detect_script, evaluate_detection_quality, select_or_merge_passes
from app.api.dependencies.ocr import get_ocr_engine

# ---------------------------------------------------------
# 1. Rich Raw Detection Schema
# ---------------------------------------------------------
def test_rich_raw_detections():
    bbox = BoundingBox(
        points=[(10.0, 20.0), (110.0, 20.0), (110.0, 50.0), (10.0, 50.0)],
        normalized_points=[(0.01, 0.02), (0.11, 0.02), (0.11, 0.05), (0.01, 0.05)],
        width=100.0,
        height=30.0,
        area=3000.0
    )
    block = TextBlock(
        box=bbox,
        text="29501011234567",
        confidence=0.98,
        x=10.0,
        y=20.0,
        width=100.0,
        height=30.0,
        page=1,
        detection_order=1,
        script="numeric"
    )
    assert block.x == 10.0
    assert block.y == 20.0
    assert block.width == 100.0
    assert block.height == 30.0
    assert block.page == 1
    assert block.detection_order == 1
    assert block.script == "numeric"

# ---------------------------------------------------------
# 2. Script Detection Per Block
# ---------------------------------------------------------
def test_script_detection_per_block():
    assert detect_script("جمهورية مصر العربية") == "ar"
    assert detect_script("Commercial Invoice") == "latin"
    assert detect_script("123456789") == "numeric"
    assert detect_script("Cairo القاهرة 2024") == "mixed"
    assert detect_script("###$$$") == "symbol"

# ---------------------------------------------------------
# 3. Multi-Signal Quality Evaluation
# ---------------------------------------------------------
def test_multi_signal_quality_evaluation():
    # A. High quality result
    bbox = BoundingBox(points=[(0, 0), (10, 0), (10, 10), (0, 10)], normalized_points=[(0,0),(0.1,0),(0.1,0.1),(0,0.1)], width=10, height=10, area=100)
    good_blocks = [
        TextBlock(box=bbox, text="Total Amount: 15000 EGP", confidence=0.95),
        TextBlock(box=bbox, text="Invoice Number: INV-9812", confidence=0.94),
        TextBlock(box=bbox, text="Date: 2024-05-15", confidence=0.96)
    ]
    good_res = OCRResult(blocks=good_blocks, total_time_ms=100, average_confidence=0.95, image_width=500, image_height=500)
    eval_good = evaluate_detection_quality(good_res)
    assert eval_good["composite_score"] > 0.65
    assert eval_good["has_structured_data"] is True
    assert eval_good["coherence_ratio"] > 0.80

    # B. Noisy gibberish result
    bad_blocks = [
        TextBlock(box=bbox, text="~!!@#$$%", confidence=0.25),
        TextBlock(box=bbox, text="^^^^||||", confidence=0.20)
    ]
    bad_res = OCRResult(blocks=bad_blocks, total_time_ms=100, average_confidence=0.22, image_width=500, image_height=500)
    eval_bad = evaluate_detection_quality(bad_res)
    assert eval_bad["composite_score"] < 0.40
    assert eval_bad["has_structured_data"] is False

# ---------------------------------------------------------
# 4. Multi-Pass Selection & Complementary Merging
# ---------------------------------------------------------
def test_multi_pass_selection_and_merging():
    bbox1 = BoundingBox(points=[(10, 10), (100, 10), (100, 30), (10, 30)], normalized_points=[(0,0),(0,0),(0,0),(0,0)], width=90, height=20, area=1800)
    bbox2 = BoundingBox(points=[(10, 50), (100, 50), (100, 70), (10, 70)], normalized_points=[(0,0),(0,0),(0,0),(0,0)], width=90, height=20, area=1800)
    bbox_footer = BoundingBox(points=[(10, 400), (200, 400), (200, 430), (10, 430)], normalized_points=[(0,0),(0,0),(0,0),(0,0)], width=190, height=30, area=5700)

    # Pass A found header (bbox1, bbox2)
    pass_a = OCRResult(
        blocks=[
            TextBlock(box=bbox1, text="Company Header", confidence=0.90),
            TextBlock(box=bbox2, text="Invoice 1234", confidence=0.88)
        ],
        total_time_ms=80,
        average_confidence=0.89,
        image_width=500,
        image_height=500
    )

    # Pass B found header (overlapping) AND footer (bbox_footer)
    pass_b = OCRResult(
        blocks=[
            TextBlock(box=bbox1, text="Company Header", confidence=0.89),
            TextBlock(box=bbox_footer, text="Tax Registration: 987654321", confidence=0.92)
        ],
        total_time_ms=80,
        average_confidence=0.90,
        image_width=500,
        image_height=500
    )

    merged, strategy = select_or_merge_passes(pass_a, pass_b)
    assert strategy == "merged"
    # Merged should have 3 blocks: header + invoice + footer!
    assert len(merged.blocks) == 3
    assert any("Tax Registration" in b.text for b in merged.blocks)

# ---------------------------------------------------------
# 5. EasyOCR Engine Production Inference
# ---------------------------------------------------------
def test_easyocr_engine_rich_inference():
    # Synthetic image with Arabic and English
    img = np.ones((400, 800, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Tax Invoice 2024", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    cv2.putText(img, "Total: 1500 EGP", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)

    engine = get_ocr_engine()
    res = engine.process_image(img)
    assert res is not None
    assert len(res.blocks) >= 2

    # Check rich attributes
    for block in res.blocks:
        assert block.width > 0
        assert block.height > 0
        assert block.page == 1
        assert block.detection_order >= 1
        assert block.script in ["latin", "numeric", "mixed", "ar", "symbol"]


def test_easyocr_engine_preserves_raw_text_without_post_correction(monkeypatch):
    from app.infrastructure.ocr.easyocr_engine import EasyOCREngine
    bbox = [[10, 10], [150, 10], [150, 40], [10, 40]]
    engine = object.__new__(EasyOCREngine)
    engine._initialized = True

    class Reader:
        def readtext(self, *_args, **_kwargs):
            return [(bbox, "محمل", 0.91)]

    engine.reader = Reader()
    result = engine.process_image(np.ones((100, 200, 3), dtype=np.uint8) * 255)
    assert result.blocks[0].text == "محمل"
    assert result.blocks[0].raw_text == "محمل"
    assert result.blocks[0].normalized_text == "محمل"
