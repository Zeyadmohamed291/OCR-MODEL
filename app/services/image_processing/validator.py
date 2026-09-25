import logging
from typing import Optional
from fastapi import UploadFile
from app.core.exceptions import UnsupportedFormatError, ValidationFailureError, PayloadTooLargeError, InvalidImageError
from app.core.config import settings

logger = logging.getLogger("ocr_microservice")

# Standard image magic byte signatures
MAGIC_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
    b"BM": "image/bmp"
}

def detect_image_magic_bytes(header: bytes) -> Optional[str]:
    """
    Inspects raw file header bytes to determine genuine image MIME type.
    Prevents trusting client-supplied file extensions or MIME headers alone.
    """
    if not header or len(header) < 4:
        return None

    for signature, mime in MAGIC_SIGNATURES.items():
        if header.startswith(signature):
            return mime

    # WebP signature: RIFF....WEBP
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"

    return None


def validate_image_metadata(file: UploadFile, header_bytes: Optional[bytes] = None) -> None:
    """
    Validates uploaded file filename, size, and media type.
    """
    if not file.filename or not file.filename.strip():
        raise ValidationFailureError("Filename cannot be empty.")

    # Check file extension / content-type against allowed types
    if file.content_type and file.content_type not in settings.ALLOWED_IMAGE_TYPES and file.content_type != "application/octet-stream":
        raise UnsupportedFormatError(
            f"Unsupported content type '{file.content_type}'. Allowed: {settings.ALLOWED_IMAGE_TYPES}"
        )

    # Match the decoder's policy to the API allowlist. Recognizing a signature
    # does not mean the service promises support for that format.
    if header_bytes:
        detected_mime = detect_image_magic_bytes(header_bytes)
        if not detected_mime or detected_mime not in settings.ALLOWED_IMAGE_TYPES:
            raise UnsupportedFormatError(
                f"Unsupported image format '{detected_mime or 'unknown'}'. Allowed: {settings.ALLOWED_IMAGE_TYPES}"
            )
        if file.content_type and file.content_type != "application/octet-stream" and file.content_type != detected_mime:
            raise UnsupportedFormatError(
                f"Declared content type '{file.content_type}' does not match detected format '{detected_mime}'."
            )

    # Check declared size if provided
    if file.size is not None and file.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise PayloadTooLargeError(
            f"File size exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB."
        )

    # Signature validation is performed after bounded read by `load_image`.
