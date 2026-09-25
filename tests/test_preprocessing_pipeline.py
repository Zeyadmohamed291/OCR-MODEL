import pytest
import numpy as np
import cv2
from app.services.image_processing.quality import analyze_image_quality
from app.services.image_processing.geometry import (
    estimate_skew_angle, deskew_image, rotate_cardinal, correct_perspective
)
from app.services.image_processing.preprocessor import (
    AdaptivePreprocessor, preprocess_for_ocr
)

# ---------------------------------------------------------
# 1. Clean Scan (Preservation of Quality & Minimal Ops)
# ---------------------------------------------------------
def test_clean_scan_preprocessing():
    # Clean high contrast image (like a digital PDF export)
    clean_img = np.ones((1000, 800, 3), dtype=np.uint8) * 255
    # Add clear black text lines
    cv2.putText(clean_img, "Official Invoice INV-2024", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cv2.putText(clean_img, "Total: 15000.00 EGP", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    quality = analyze_image_quality(clean_img)
    assert quality.is_blurry is False
    assert quality.resolution_ok is True
    assert quality.skew_angle == 0.0

    primary, variants = AdaptivePreprocessor.preprocess_adaptive(clean_img, quality)
    assert "primary" in variants
    assert "original" in variants
    assert primary.shape == clean_img.shape

# ---------------------------------------------------------
# 2. Tilted / Skewed Document (Deskew)
# ---------------------------------------------------------
def test_skew_estimation_and_deskew():
    # Create an image with tilted text lines (+5 degrees)
    img = np.ones((600, 800, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Contract Agreement First Party", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cv2.putText(img, "Second Party Terms and Conditions", (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cv2.putText(img, "Articles 1 2 3 4 5 6 7", (100, 400), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    # Rotate by 5 degrees
    center = (400, 300)
    matrix = cv2.getRotationMatrix2D(center, 5.0, 1.0)
    tilted = cv2.warpAffine(img, matrix, (800, 600), borderValue=(255, 255, 255))

    skew = estimate_skew_angle(tilted)
    assert abs(skew) > 1.0  # Successfully detected tilt

    deskewed = deskew_image(tilted, skew)
    assert deskewed is not None
    assert deskewed.shape[0] >= tilted.shape[0]

# ---------------------------------------------------------
# 3. Cardinal Rotation (90, 180, 270)
# ---------------------------------------------------------
def test_cardinal_rotations():
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    r90 = rotate_cardinal(img, 90)
    assert r90.shape == (600, 400, 3)

    r180 = rotate_cardinal(img, 180)
    assert r180.shape == (400, 600, 3)

    r270 = rotate_cardinal(img, 270)
    assert r270.shape == (600, 400, 3)

# ---------------------------------------------------------
# 4. Low-Resolution Upscaling & Massive Downscaling
# ---------------------------------------------------------
def test_resolution_adaptive_scaling():
    # Low-res image (e.g. 300x200 cropped label)
    low_res = np.ones((200, 300, 3), dtype=np.uint8) * 255
    q_low = analyze_image_quality(low_res)
    assert q_low.resolution_ok is False
    primary_up, _ = AdaptivePreprocessor.preprocess_adaptive(low_res, q_low)
    # Upscaled
    assert primary_up.shape[0] > low_res.shape[0]
    assert primary_up.shape[1] > low_res.shape[1]

    # Massive image (e.g. 4000x3500)
    massive = np.ones((4000, 3500, 3), dtype=np.uint8) * 255
    q_massive = analyze_image_quality(massive)
    primary_down, _ = AdaptivePreprocessor.preprocess_adaptive(massive, q_massive)
    assert max(primary_down.shape[:2]) <= AdaptivePreprocessor.MAX_DIM

# ---------------------------------------------------------
# 5. Blur Detection & Controlled Sharpening
# ---------------------------------------------------------
def test_blurry_image_sharpening():
    # Blurred image (800x800 so optimal resolution)
    sharp = np.ones((800, 800, 3), dtype=np.uint8) * 255
    cv2.putText(sharp, "Blurred Text Test", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    blurry = cv2.GaussianBlur(sharp, (15, 15), 0)

    quality = analyze_image_quality(blurry)
    assert quality.is_blurry is True

    primary, _ = AdaptivePreprocessor.preprocess_adaptive(blurry, quality)
    assert primary.shape == blurry.shape
    assert primary is not None


def test_clean_sharp_image_is_not_smoothed_by_denoising_branch():
    img = np.full((800, 800, 3), 255, dtype=np.uint8)
    cv2.putText(img, "SHARP", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 3)
    quality = analyze_image_quality(img)
    # The fixture is sparse text; page-wide variance is not a fixed >300.
    assert quality.is_blurry is False
    primary, _ = AdaptivePreprocessor.preprocess_adaptive(img, quality)
    gray = cv2.cvtColor(primary, cv2.COLOR_BGR2GRAY)
    # Primary does grayscale conversion, but the clean high-contrast branch
    # should not run bilateral smoothing or thresholding.
    assert np.mean(np.abs(gray.astype(np.int16) - cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.int16))) == 0

# ---------------------------------------------------------
# 6. Uneven Lighting & Shadow Flattening
# ---------------------------------------------------------
def test_shadow_gradient_removal():
    # Create image with harsh shadow gradient from left (dark) to right (bright)
    img = np.ones((800, 800, 3), dtype=np.uint8) * 200
    for x in range(400):
        img[:, x] = img[:, x] - 140  # Dark shadow on left half
    cv2.putText(img, "Payment Receipt", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    quality = analyze_image_quality(img)
    primary, variants = AdaptivePreprocessor.preprocess_adaptive(img, quality)
    assert primary is not None
    assert "primary" in variants


def test_preprocessor_does_not_build_unused_threshold_variant():
    img = np.full((800, 800, 3), 255, dtype=np.uint8)
    img[:, :400] = 80
    quality = analyze_image_quality(img)
    _, variants = AdaptivePreprocessor.preprocess_adaptive(img, quality)
    assert "primary" in variants
    assert "original" in variants
    assert "enhanced" not in variants

# ---------------------------------------------------------
# 7. Arabic Dots and Diacritics Preservation
# ---------------------------------------------------------
def test_arabic_dots_and_thin_strokes_preservation():
    # Create image with simulated fine dots (800x800 so no scaling shift)
    img = np.ones((800, 800, 3), dtype=np.uint8) * 255
    # Simulate dots as tiny black squares (3x3 pixels)
    img[150:154, 150:154] = 0
    img[150:154, 158:162] = 0
    # Simulate a thin stroke (2px width)
    img[170:172, 140:180] = 0

    quality = analyze_image_quality(img)
    primary, _ = AdaptivePreprocessor.preprocess_adaptive(img, quality)

    # Convert primary to gray and verify the dots are not smoothed out/erased
    gray = cv2.cvtColor(primary, cv2.COLOR_BGR2GRAY)
    dot1_val = np.min(gray[150:154, 150:154])
    stroke_val = np.min(gray[170:172, 140:180])
    
    # Text pixels should remain dark (< 100), not washed out into background (255)
    assert dot1_val < 120, "Arabic dot was destroyed by preprocessing!"
    assert stroke_val < 120, "Thin stroke was destroyed by preprocessing!"

# ---------------------------------------------------------
# 8. Perspective Correction Detection
# ---------------------------------------------------------
def test_perspective_detection():
    # Create a white document rectangle inside a dark background
    bg = np.zeros((800, 800, 3), dtype=np.uint8)
    # Tilted 4-corner document inside the background
    doc_pts = np.array([[120, 150], [680, 120], [700, 680], [100, 650]], dtype=np.int32)
    cv2.fillPoly(bg, [doc_pts], (255, 255, 255))
    cv2.putText(bg, "Sample Contract", (200, 400), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    warped, applied = correct_perspective(bg)
    assert applied is True
    assert warped.shape[0] > 300
    assert warped.shape[1] > 300
