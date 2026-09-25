"""Bounded uploads and in-memory image decoding."""
import io
import warnings
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import UploadFile
from app.core.config import settings
from app.core.exceptions import InvalidImageError, UnsupportedFormatError, PayloadTooLargeError
from app.domain.schemas.core import ImageMetadata
from app.services.image_processing.validator import detect_image_magic_bytes

MAX_IMAGE_DIMENSION = 10_000
MAX_IMAGE_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

async def read_upload(file: UploadFile) -> bytes:
    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    chunks, total = [], 0
    try:
        while total <= limit:
            chunk = await file.read(min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise PayloadTooLargeError(f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB upload limit.")
            chunks.append(chunk)
    finally:
        await file.seek(0)
    if not total:
        raise InvalidImageError("Empty file uploaded.")
    return b"".join(chunks)

def validate_content(contents: bytes, declared_type: str | None, allow_pdf=False) -> str:
    mime = "application/pdf" if allow_pdf and contents.startswith(b"%PDF-") else detect_image_magic_bytes(contents[:32])
    allowed = list(settings.ALLOWED_IMAGE_TYPES) + (["application/pdf"] if allow_pdf else [])
    if mime not in allowed:
        raise UnsupportedFormatError(f"Unsupported file contents. Allowed: {allowed}")
    declared_type = {"image/jpg": "image/jpeg", "image/x-ms-bmp": "image/bmp"}.get(declared_type, declared_type)
    if declared_type and declared_type not in ("application/octet-stream", mime):
        raise UnsupportedFormatError(f"Declared content type '{declared_type}' does not match '{mime}'.")
    return mime

def check_dimensions(width, height):
    if width < 1 or height < 1 or max(width, height) > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
        raise InvalidImageError("Image exceeds supported dimensions or pixel limit.")

def pil_to_bgr(image: Image.Image) -> np.ndarray:
    # Check headers before convert()/np.array() allocate decoded pixel buffers.
    check_dimensions(*image.size)
    transposed = ImageOps.exif_transpose(image)
    try:
        # Removing alpha without compositing can hide black text on transparency.
        if "A" in transposed.getbands() or "transparency" in transposed.info:
            rgba = transposed.convert("RGBA")
            try:
                background = Image.new("RGBA", rgba.size, "white")
                try:
                    background.alpha_composite(rgba)
                    rgb = np.array(background.convert("RGB"))
                finally:
                    background.close()
            finally:
                rgba.close()
        else:
            rgb = np.array(transposed.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    finally:
        transposed.close()

async def load_image(file: UploadFile) -> tuple[np.ndarray, ImageMetadata]:
    contents = await read_upload(file)
    mime = validate_content(contents, file.content_type)
    from starlette.concurrency import run_in_threadpool
    image = await run_in_threadpool(decode_image, contents)
    height, width = image.shape[:2]
    return image, ImageMetadata(filename=file.filename or "unknown", width=width, height=height,
                                content_type=mime, size_bytes=len(contents))

def decode_image(contents: bytes) -> np.ndarray:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contents)) as image:
                if getattr(image, "n_frames", 1) != 1:
                    raise InvalidImageError("Multi-page images require /ocr/document; no pages were silently discarded.")
                return pil_to_bgr(image)
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise InvalidImageError("Image exceeds safe decoding pixel limit.") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("File is corrupted or cannot be decoded as an image.") from exc
