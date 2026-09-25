import cv2
import numpy as np
import logging
from app.domain.schemas.core import ImageQualityMetrics
from app.services.image_processing.geometry import estimate_skew_angle

logger = logging.getLogger("ocr_microservice")

def analyze_image_quality(image: np.ndarray) -> ImageQualityMetrics:
    """
    Analyzes document image quality without blocking OCR execution.
    Computes dimensions, blur score, brightness, contrast, skew angle, and resolution health.
    """
    if image is None or image.size == 0:
        return ImageQualityMetrics(
            width=0,
            height=0,
            channels=0,
            is_blurry=True,
            blur_score=0.0,
            brightness=0.0,
            contrast=0.0,
            resolution_ok=False,
            skew_angle=0.0,
            detected_orientation=0,
            variants_evaluated=[],
            warnings=["Empty or invalid image."]
        )

    height, width = image.shape[:2]
    channels = image.shape[2] if len(image.shape) == 3 else 1

    # Convert to grayscale if necessary
    if channels == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    warnings = []

    # 1. Blur Detection via Laplacian Variance
    try:
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        blur_score = float(laplacian.var())
    except Exception as e:
        logger.warning(f"Failed to calculate blur score: {e}")
        blur_score = 100.0

    # Blur threshold: typically < 80 indicates blur on document scans
    is_blurry = blur_score < 80.0
    if is_blurry:
        warnings.append(f"Image may be blurry (variance: {blur_score:.1f}). Text recognition accuracy may be reduced.")

    # 2. Brightness and Contrast
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))

    if brightness < 40.0:
        warnings.append(f"Image appears underexposed (mean brightness: {brightness:.1f}/255).")
    elif brightness > 230.0:
        warnings.append(f"Image appears washed out or overexposed (mean brightness: {brightness:.1f}/255).")

    if contrast < 25.0:
        warnings.append(f"Low contrast detected ({contrast:.1f}). Text may blend with background.")

    # 3. Resolution Check
    min_dim = min(width, height)
    resolution_ok = min_dim >= 300
    if not resolution_ok:
        warnings.append(f"Low resolution image ({width}x{height}). Recommended minimum dimension is 300px.")

    # Cardinal orientation is not inferred from aspect ratio: that cannot
    # distinguish 90 from 270 degrees or portrait content from a rotated scan.
    detected_orientation = 0
    # 4. Skew Angle Estimation
    skew_angle = 0.0
    try:
        skew_angle = estimate_skew_angle(gray)
        if abs(skew_angle) >= 1.0:
            warnings.append(f"Document skew detected ({skew_angle:+.1f}°). Automatic deskew recommended.")
    except Exception as e:
        logger.debug(f"Skew estimation skipped: {e}")

    return ImageQualityMetrics(
        width=width,
        height=height,
        channels=channels,
        is_blurry=is_blurry,
        blur_score=round(blur_score, 2),
        brightness=round(brightness, 2),
        contrast=round(contrast, 2),
        resolution_ok=resolution_ok,
        skew_angle=skew_angle,
        detected_orientation=detected_orientation,
        variants_evaluated=[],
        warnings=warnings
    )
