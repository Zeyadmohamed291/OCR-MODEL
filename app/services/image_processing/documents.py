"""Sequential bounded PDF/TIFF/image page decoding. No external OCR service."""
import io
import math
import threading
import warnings
from PIL import Image, UnidentifiedImageError
from app.core.config import settings
from app.core.exceptions import InvalidImageError, PayloadTooLargeError, ConfigurationError
from app.services.image_processing.loader import pil_to_bgr, check_dimensions

# PDFium is not thread safe, including calls on different documents.
_pdf_lock = threading.Lock()
MAX_DOCUMENT_PIXELS = 100_000_000
MAX_PDF_PAGE_PIXELS = 12_000_000


def _check_pages(count):
    if count < 1:
        raise InvalidImageError("Document has no pages.")
    if count > settings.DOCUMENT_MAX_PAGES:
        raise PayloadTooLargeError(f"Document exceeds {settings.DOCUMENT_MAX_PAGES} page limit.")


def document_pages(contents, mime):
    if mime == "application/pdf":
        yield from _pdf_pages(contents)
        return
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contents)) as document:
                count = getattr(document, "n_frames", 1)
                _check_pages(count)
                pixels = 0
                for index in range(count):
                    document.seek(index)
                    check_dimensions(*document.size)
                    pixels += document.width * document.height
                    if pixels > MAX_DOCUMENT_PIXELS:
                        raise PayloadTooLargeError("Document exceeds total pixel limit.")
                    yield pil_to_bgr(document)
    except (Image.DecompressionBombWarning, Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("Image document is corrupted or exceeds safe decoding limits.") from exc


def _pdf_pages(contents):
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise ConfigurationError("PDF support requires pypdfium2; install project requirements.") from exc
    with _pdf_lock:
        try:
            with pdfium.PdfDocument(contents) as document:
                _check_pages(len(document))
                total_pixels = 0
                for index in range(len(document)):
                    page = document[index]
                    try:
                        width, height = page.get_size()
                        if not all(math.isfinite(n) and n > 0 for n in (width, height)):
                            raise InvalidImageError("PDF has invalid page dimensions.")
                        scale = min(settings.DOCUMENT_DPI / 72, settings.OCR_CANVAS_SIZE / max(width, height),
                                    math.sqrt(MAX_PDF_PAGE_PIXELS / (width * height)))
                        total_pixels += math.ceil(width * scale) * math.ceil(height * scale)
                        if total_pixels > MAX_DOCUMENT_PIXELS:
                            raise PayloadTooLargeError("PDF exceeds total rendered pixel limit.")
                        bitmap = page.render(scale=scale)
                        try:
                            pil_image = bitmap.to_pil()
                            try:
                                image = pil_to_bgr(pil_image)
                            finally:
                                pil_image.close()
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
                    yield image
        except pdfium.PdfiumError as exc:
            raise InvalidImageError("PDF is corrupted, encrypted or cannot be rendered.") from exc
