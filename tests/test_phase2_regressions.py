import asyncio
import io

import numpy as np
import pytest
from fastapi import UploadFile

from app.core.exceptions import OCRFailureError, UnsupportedFormatError
from app.domain.schemas.core import ImageQualityMetrics
from app.infrastructure.ocr.easyocr_engine import EasyOCREngine
from app.services.extraction.validation import parse_and_validate_date, validate_egyptian_national_id
from app.services.image_processing.loader import load_image


def test_easyocr_rejects_empty_image():
    engine = object.__new__(EasyOCREngine)
    with pytest.raises(OCRFailureError):
        engine.process_image(np.zeros((0, 0, 3), dtype=np.uint8))


def test_easyocr_skips_malformed_detections_without_inflating_average_confidence():
    engine = object.__new__(EasyOCREngine)
    class Reader:
        def readtext(self, *_args, **_kwargs):
            return [(None, "bad-box", 0.99), ([[1, 1], [20, 1], [20, 10], [1, 10]], "OK", 0.8)]
    engine.reader = Reader()
    result = engine.process_image(np.full((40, 40, 3), 255, dtype=np.uint8))
    assert [block.text for block in result.blocks] == ["OK"]
    assert result.average_confidence == pytest.approx(0.8)


def test_unicode_digits_validate_for_ids_and_dates():
    valid, info, _ = validate_egyptian_national_id("٢٩٥٠١٠١١٢٣٤٥٦٧")
    assert valid is True
    assert info["birth_date"] == "1995-01-01"
    valid_date, parsed, _ = parse_and_validate_date("١٥/٠٥/٢٠٢٤")
    assert valid_date is True
    assert parsed.isoformat() == "2024-05-15"


def test_declared_content_type_mismatch_and_unsupported_signature_are_rejected():
    async def run():
        mismatch = UploadFile(filename="wrong.png", file=io.BytesIO(b"\xff\xd8\xff\xe0rest"), headers={"content-type": "image/png"})
        with pytest.raises(UnsupportedFormatError):
            await load_image(mismatch)
        unsupported = UploadFile(filename="animation.gif", file=io.BytesIO(b"GIF89arest"), headers={"content-type": "application/octet-stream"})
        with pytest.raises(UnsupportedFormatError):
            await load_image(unsupported)
    asyncio.run(run())

