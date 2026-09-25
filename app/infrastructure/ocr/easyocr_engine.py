import time
import logging
import threading
import psutil
import os
import numpy as np
from app.domain.interfaces.ocr_engine import AbstractOCREngine
from app.domain.schemas.core import OCRResult, TextBlock, BoundingBox
from app.utils.bounding_boxes import sort_text_blocks
from app.core.exceptions import ModelLoadingError, OCRFailureError
from app.core.config import settings

logger = logging.getLogger("ocr_microservice")

class EasyOCREngine(AbstractOCREngine):
    _instance = None
    _lock = threading.Lock()
    _inference_lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EasyOCREngine, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # Singleton pattern to prevent reloading models for every request
        if self._initialized:
            return
            
        with self._lock:
            if not self._initialized:
                logger.info("Initializing EasyOCR models (ar, en). This occurs only once per application lifecycle.")
                start_time = time.time()
                try:
                    import easyocr
                    # Lazy loading EasyOCR Engine
                    self.reader = easyocr.Reader(
                        ['ar', 'en'],
                        gpu=False,
                        model_storage_directory=settings.MODEL_DIR,
                        download_enabled=True, # Automatically download if not present
                        verbose=False
                    )
                    self._initialized = True
                    
                    load_time = (time.time() - start_time) * 1000
                    process = psutil.Process(os.getpid())
                    mem_usage = process.memory_info().rss / (1024 * 1024)
                    logger.info(f"EasyOCR models loaded successfully in {load_time:.2f} ms. Current OS Memory: {mem_usage:.2f} MB")
                except ImportError:
                    logger.error("EasyOCR package not found.", exc_info=True)
                    raise ModelLoadingError("Failed to initialize OCR engine: EasyOCR not installed.")
                except Exception as e:
                    logger.error("Failed to load EasyOCR models.", exc_info=True)
                    raise ModelLoadingError(f"Failed to initialize OCR engine: {str(e)}")

    def process_image(self, image: np.ndarray) -> OCRResult:
        if image is None or image.size == 0:
            raise OCRFailureError("OCR input image is empty.")
        img_height, img_width = image.shape[:2]
        if image.dtype != np.uint8:
            raise OCRFailureError("OCR input image must use uint8 pixel values.")
        start_time = time.time()
        
        try:
            # Tuned Production Inference Execution
            # The shared CPU model must not allocate inference buffers for
            # several pages concurrently. Detection stays at preprocessing
            # resolution instead of silently shrinking 3200px pages to 2560px.
            with self._inference_lock:
                result = self.reader.readtext(
                    image,
                    text_threshold=0.55,
                    low_text=0.35,
                    link_threshold=0.35,
                    add_margin=0.12,
                    batch_size=4,
                    min_size=10,
                    bbox_min_score=0.15,
                    canvas_size=settings.OCR_CANVAS_SIZE,
                    width_ths=settings.OCR_WIDTH_THRESHOLD,
                )
        except Exception as e:
            logger.error("OCR inference failed.", exc_info=True)
            raise OCRFailureError(f"Inference failure: {str(e)}")
            
        inference_time = (time.time() - start_time) * 1000
        
        if not result:
            logger.warning("OCR returned empty result. No text found in the image.")
            return OCRResult(
                blocks=[],
                total_time_ms=inference_time,
                average_confidence=0.0,
                image_width=img_width,
                image_height=img_height,
                raw_output=None
            )
            
        from app.services.ocr.evaluator import detect_script
        blocks = []
        total_conf = 0.0
        valid_detection_count = 0
        
        for idx, element in enumerate(result):
            # EasyOCR output format: ([[x1,y1], [x2,y2], [x3,y3], [x4,y4]], text, confidence)
            if not isinstance(element, (list, tuple)) or len(element) < 3:
                logger.warning("Skipping malformed EasyOCR detection at index %s", idx)
                continue
            box_coords, text, raw_confidence = element[0], element[1], element[2]
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                logger.warning("Skipping EasyOCR detection with invalid confidence at index %s", idx)
                continue
            if not np.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                logger.warning("Skipping EasyOCR detection with out-of-range confidence at index %s", idx)
                continue
            try:
                pts = [(float(pt[0]), float(pt[1])) for pt in box_coords]
            except (TypeError, ValueError, IndexError):
                logger.warning("Skipping EasyOCR detection with malformed box at index %s", idx)
                continue
            if len(pts) != 4 or not all(np.isfinite(v) for pt in pts for v in pt):
                logger.warning("Skipping EasyOCR detection with invalid box at index %s", idx)
                continue
            # Extract and normalize coordinates
            norm_pts = [(pt[0]/img_width, pt[1]/img_height) for pt in pts]
            
            x_coords = [p[0] for p in pts]
            y_coords = [p[1] for p in pts]
            min_x = min(x_coords)
            min_y = min(y_coords)

            # Short numeric/symbol detections may be page numbers, amounts or
            # punctuation. Proximity to an image edge is not evidence of noise.
            w = max(x_coords) - min_x
            h = max(y_coords) - min_y
            area = w * h
            
            bbox = BoundingBox(
                points=pts,
                normalized_points=norm_pts,
                width=w,
                height=h,
                area=area
            )
            
            script = detect_script(text)
            
            blocks.append(TextBlock(
                box=bbox,
                text=text,
                raw_text=text,
                normalized_text=text,
                confidence=confidence,
                x=round(min_x, 1),
                y=round(min_y, 1),
                width=round(w, 1),
                height=round(h, 1),
                page=1,
                detection_order=idx + 1,
                script=script
            ))
            total_conf += confidence
            valid_detection_count += 1
            
        # Apply strict mathematical reading order formatting
        sorted_blocks = sort_text_blocks(blocks)

        # Preserve source transcription. Any cleanup belongs in downstream
        # normalized fields and must never silently mutate the raw OCR value.
        for block in sorted_blocks:
            block.raw_text = block.text
            block.normalized_text = block.text
        
        avg_conf = total_conf / valid_detection_count if valid_detection_count else 0.0
        total_time = (time.time() - start_time) * 1000
        
        # Memory tracking
        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss / (1024 * 1024)
        
        logger.info(f"Processed {len(blocks)} blocks. Avg Confidence: {avg_conf:.2f}. Inference Time: {total_time:.2f} ms. App RAM Usage: {mem_mb:.2f} MB")
        
        return OCRResult(
            blocks=sorted_blocks,
            total_time_ms=total_time,
            average_confidence=avg_conf,
            image_width=img_width,
            image_height=img_height,
            raw_output=result
        )
