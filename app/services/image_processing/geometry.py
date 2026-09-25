import cv2
import numpy as np
import logging
from typing import Tuple, Optional

logger = logging.getLogger("ocr_microservice")

def estimate_skew_angle(image: np.ndarray) -> float:
    """
    Estimates the corrective OpenCV rotation angle in [-45, 45] degrees.
    Returns 0.0 if image is already upright.
    """
    if image is None or image.size == 0:
        return 0.0

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Invert so text is white on black
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    # Dilate horizontally to connect text characters into lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 3))
    dilated = cv2.morphologyEx(thresh, cv2.MORPH_DILATE, kernel)

    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    
    angles = []
    min_area = (gray.shape[0] * gray.shape[1]) * 0.0005  # At least 0.05% of image

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        rect = cv2.minAreaRect(cnt)
        (w, h) = rect[1]
        angle = rect[2]

        if w < h:
            angle = -(90.0 - angle)
        else:
            angle = -angle

        # Normalize angle to [-45, 45]
        while angle < -45.0:
            angle += 90.0
        while angle > 45.0:
            angle -= 90.0

        # Discard extreme or vertical lines
        if abs(angle) < 45.0:
            angles.append(angle)

    if not angles:
        return 0.0

    median_angle = float(np.median(angles))
    
    # Ignore negligible angles (< 0.5 deg) to avoid interpolation blur
    if abs(median_angle) < 0.5:
        return 0.0

    # minAreaRect above gives the observed tilt. warpAffine needs the opposite
    # rotation; using the observed tilt again doubles the document skew.
    return round(-median_angle, 2)

def deskew_image(image: np.ndarray, angle: float) -> np.ndarray:
    """
    Rotates image by the given angle to correct document tilt.
    Uses cubic interpolation and white background padding.
    """
    if abs(angle) < 0.5 or image is None or image.size == 0:
        return image

    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)

    # Compute rotation matrix
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    
    # Calculate new bounding dimensions to avoid cropping corners
    cos = np.abs(matrix[0, 0])
    sin = np.abs(matrix[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))

    matrix[0, 2] += (new_w / 2.0) - center[0]
    matrix[1, 2] += (new_h / 2.0) - center[1]

    # White border for document padding
    border_val = (255, 255, 255) if len(image.shape) == 3 else 255

    deskewed = cv2.warpAffine(
        image,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_val
    )
    return deskewed

def rotate_cardinal(image: np.ndarray, degrees: int) -> np.ndarray:
    """
    Rotates image by 90, 180, or 270 degrees clockwise.
    """
    if degrees == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif degrees == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    elif degrees == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image

def correct_perspective(image: np.ndarray) -> Tuple[np.ndarray, bool]:
    """
    Detects document boundary quadrilateral against a background and warps perspective.
    Applies only if a clear, convex 4-corner polygon representing > 35% of the image area is found.
    Returns: (corrected_image, was_applied)
    """
    if image is None or image.size == 0:
        return image, False

    h, w = image.shape[:2]
    total_area = h * w

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 200)

    # Dilate edges to close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edged, kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < total_area * 0.35:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) == 4 and cv2.isContourConvex(approx):
            pts = approx.reshape(4, 2)
            
            # Order points: top-left, top-right, bottom-right, bottom-left
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]

            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]

            (tl, tr, br, bl) = rect

            width_a = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
            width_b = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
            max_width = max(int(width_a), int(width_b))

            height_a = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
            height_b = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
            max_height = max(int(height_a), int(height_b))

            if max_width < 150 or max_height < 150:
                continue

            dst = np.array([
                [0, 0],
                [max_width - 1, 0],
                [max_width - 1, max_height - 1],
                [0, max_height - 1]
            ], dtype="float32")

            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(image, M, (max_width, max_height), flags=cv2.INTER_CUBIC)
            logger.info(f"Perspective warp applied. Detected document bounds: {max_width}x{max_height}")
            return warped, True

    return image, False
