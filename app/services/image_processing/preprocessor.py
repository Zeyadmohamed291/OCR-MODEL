import cv2
import numpy as np
import logging
from typing import Dict, Tuple, Optional
from app.domain.schemas.core import ImageQualityMetrics
from app.services.image_processing.geometry import deskew_image, correct_perspective

logger = logging.getLogger("ocr_microservice")

class AdaptivePreprocessor:
    """
    Production-grade adaptive image preprocessor.
    Applies targeted, non-destructive transformations based on image quality metrics.
    Preserves Arabic dots, thin strokes, numbers, and clean digital scans.
    """

    MAX_DIM = 3200
    MIN_OPTIMAL_DIM = 750

    @classmethod
    def preprocess_adaptive(
        cls,
        image: np.ndarray,
        quality: ImageQualityMetrics
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Executes adaptive preprocessing based on image metrics.
        Returns:
            primary_image: The optimal image for OCR inference
            variants: Dict containing 'primary', 'original', and transform metadata.
        """
        if image is None or image.size == 0:
            return image, {"original": image, "primary": image}

        # 1. Perspective Correction (if document quad clearly detected)
        geo_img, applied_perspective = correct_perspective(image)

        # 2. Deskew (if tilt detected)
        if abs(quality.skew_angle) >= 0.6:
            geo_img = deskew_image(geo_img, quality.skew_angle)

        # Keep geometry-corrected original
        original_variant = geo_img.copy()

        # 3. Controlled Resolution Scaling. Preserve small text by avoiding
        # gratuitous enlargement of narrow crops; only scale truly small images.
        curr_h, curr_w = geo_img.shape[:2]
        scaled_img = geo_img

        # Safe downscale for massive images to prevent OOM / excessive CPU usage
        if max(curr_w, curr_h) > cls.MAX_DIM:
            scale = cls.MAX_DIM / max(curr_w, curr_h)
            new_w, new_h = int(curr_w * scale), int(curr_h * scale)
            scaled_img = cv2.resize(geo_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            logger.info(f"Downscaled massive image from {curr_w}x{curr_h} to {new_w}x{new_h}")
        # Controlled upscale for small/low-resolution documents
        elif max(curr_w, curr_h) < 900:
            scale = max(1.0, min(2.0, cls.MIN_OPTIMAL_DIM / max(min(curr_w, curr_h), 1)))
            if scale > 1.0:
                new_w, new_h = int(curr_w * scale), int(curr_h * scale)
                scaled_img = cv2.resize(geo_img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
                logger.info(f"Upscaled low-res image from {curr_w}x{curr_h} to {new_w}x{new_h}")

        # 4. Color & Illumination Analysis
        if len(scaled_img.shape) == 3:
            gray = cv2.cvtColor(scaled_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = scaled_img

        # 5. Shadow Removal / Illumination Flattening (only for uneven lighting)
        # Check standard deviation of quadrant means to detect shadow gradients
        h_mid, w_mid = gray.shape[0] // 2, gray.shape[1] // 2
        q_means = [
            np.mean(gray[:h_mid, :w_mid]),
            np.mean(gray[:h_mid, w_mid:]),
            np.mean(gray[h_mid:, :w_mid]),
            np.mean(gray[h_mid:, w_mid:])
        ]
        has_shadow_gradient = (max(q_means) - min(q_means)) > 45.0

        if has_shadow_gradient:
            # Estimate background illumination with large blur and divide
            bg_est = cv2.GaussianBlur(gray, (51, 51), 0)
            norm = np.clip((gray.astype(np.float32) / (bg_est.astype(np.float32) + 1e-5)) * 255.0, 0, 255).astype(np.uint8)
            working_gray = norm
        else:
            working_gray = gray

        # 6. Denoise only when measurable image noise is present. A high
        # Laplacian variance indicates sharp edges, not blur/noise by itself.
        if has_shadow_gradient:
            denoised = cv2.bilateralFilter(working_gray, d=5, sigmaColor=35, sigmaSpace=35)
        else:
            denoised = working_gray

        # 7. Adaptive Contrast Enhancement (CLAHE)
        # Clean scans (contrast >= 55.0) do NOT need aggressive contrast modification
        # Page-wide variance is low even for crisp black text on a mostly
        # white page. Preserve such sparse text rather than amplifying JPEG
        # artifacts and altering Arabic dots with unnecessary CLAHE.
        threshold, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        dark = gray[gray <= threshold]
        light = gray[gray > threshold]
        text_contrast = float(np.median(light) - np.median(dark)) if dark.size and light.size else 0.0
        preserve_contrast = text_contrast >= 100.0 or float(np.ptp(gray)) == 0.0
        if not preserve_contrast and quality.contrast < 45.0:
            # Faded or low contrast: apply CLAHE
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            contrast_enhanced = clahe.apply(denoised)
        elif not preserve_contrast and quality.contrast < 55.0:
            clahe = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8))
            contrast_enhanced = clahe.apply(denoised)
        else:
            contrast_enhanced = denoised

        # Do not sharpen blurred text: sharpening cannot recover lost detail and
        # often amplifies Arabic dots/noise. Keep the conservative enhanced image.
        final_gray = contrast_enhanced

        # Convert primary back to 3 channels for OCR engine compatibility
        primary_bgr = cv2.cvtColor(final_gray, cv2.COLOR_GRAY2BGR)

        primary_transform = {
            "source_width": int(image.shape[1]),
            "source_height": int(image.shape[0]),
            "width": int(primary_bgr.shape[1]),
            "height": int(primary_bgr.shape[0]),
            # Perspective/deskew changes are not represented by a simple affine
            # scale. `geometry_corrected` marks the coordinate frame explicitly.
            "geometry_corrected": bool(applied_perspective or abs(quality.skew_angle) >= 0.6 or quality.detected_orientation in (90, 180, 270)),
        }
        variants: Dict[str, np.ndarray] = {
            "primary": primary_bgr,
            "original": original_variant,
            "primary_transform": primary_transform,
            "original_transform": {
                "source_width": int(image.shape[1]), "source_height": int(image.shape[0]),
                "width": int(original_variant.shape[1]), "height": int(original_variant.shape[0]),
                "geometry_corrected": bool(applied_perspective or abs(quality.skew_angle) >= 0.6 or quality.detected_orientation in (90, 180, 270)),
            },
        }

        return primary_bgr, variants

def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Backwards-compatible entrypoint.
    Computes quality and returns the optimal primary preprocessed image.
    """
    from app.services.image_processing.quality import analyze_image_quality
    quality = analyze_image_quality(image)
    primary, _ = AdaptivePreprocessor.preprocess_adaptive(image, quality)
    return primary
