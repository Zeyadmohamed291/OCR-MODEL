import os
import mimetypes

# Must be set BEFORE importing gradio to disable SSR and React server-side rendering
os.environ["GRADIO_SSR_MODE"] = "False"

import time
import numpy as np
import cv2
import gradio as gr
import uvicorn

from app.core.config import settings
from app.core.logging import setup_logging
from app.main import app as fastapi_app
from app.api.dependencies.ocr import get_ocr_engine

# Ensure required directories exist
os.makedirs("logs", exist_ok=True)
os.makedirs(settings.MODEL_DIR, exist_ok=True)
logger = setup_logging()

# ---------------------------------------------------------------------------
# ZeroGPU support — required for Hugging Face Spaces zero-a10g hardware
# The @spaces.GPU decorator tells HF that this function CAN use the GPU.
# EasyOCR still runs in CPU mode (gpu=False) for stability.
# ---------------------------------------------------------------------------
try:
    import spaces  # type: ignore
except ImportError:
    # Local / non-HF environment: create a no-op decorator
    class spaces:  # type: ignore
        @staticmethod
        def GPU(fn=None, *args, **kwargs):
            if callable(fn):
                return fn
            def wrapper(f):
                return f
            return wrapper


# ---------------------------------------------------------------------------
# Gradio OCR Processing Function
# ---------------------------------------------------------------------------
@spaces.GPU
def run_gradio_ocr(input_image, input_file=None):
    """Runs the full OCR pipeline on the uploaded image and returns structured results."""
    if input_image is None and input_file is None:
        return "Please upload an image.", "Unknown", "0.0%", "0 ms", {}

    t0 = time.time()
    try:
        from app.services.ocr.pipeline import extract_document_pages, extract_image
        from app.services.image_processing.loader import validate_content
        if input_file:
            file_path = input_file if isinstance(input_file, str) else getattr(input_file, "path", getattr(input_file, "name", None))
            if not file_path:
                raise ValueError("Unable to access the uploaded document.")
            size = os.path.getsize(file_path)
            max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            if size > max_bytes:
                raise ValueError(f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB upload limit.")
            with open(file_path, "rb") as uploaded:
                contents = uploaded.read(max_bytes + 1)
            if len(contents) > max_bytes:
                raise ValueError(f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB upload limit.")
            mime = validate_content(contents, mimetypes.guess_type(file_path)[0], allow_pdf=True)
            result = extract_document_pages(contents, mime, os.path.basename(file_path), get_ocr_engine(), "gradio")
            page_fields = {f"page_{p.page_number}": p.result.fields or {} for p in result.pages}
            mean_confidence = sum(p.result.confidence for p in result.pages) / max(result.page_count, 1)
            review = " — راجع السطور منخفضة الثقة" if result.needs_review else ""
            return (result.text, f"{result.page_count} pages (EasyOCR)",
                    f"{round(mean_confidence * 100, 1)}%{review}",
                    f"{round((time.time() - t0) * 1000, 1)} ms", page_fields)

        # Convert the original image once, retaining alpha on white.
        if hasattr(input_image, 'convert'):
            from app.services.image_processing.loader import pil_to_bgr
            bgr_img = pil_to_bgr(input_image)
        else:
            bgr_img = np.array(input_image)

        response = extract_image(bgr_img, None, get_ocr_engine(), req_id="gradio", start_time=t0)
        review = " — راجع السطور منخفضة الثقة" if response.needs_review else ""
        return (
            response.text,
            f"{response.document.type.replace('_', ' ').title()} ({round(response.document.confidence * 100)}%)",
            f"{round(response.confidence * 100, 1)}%{review}",
            f"{response.processing_time_ms} ms",
            response.fields or {},
        )

    except Exception as e:
        logger.error(f"Gradio OCR error: {e}", exc_info=True)
        return f"Error processing image: {str(e)}", "Error", "0.0%", "0 ms", {}


# ---------------------------------------------------------------------------
# Build Gradio Blocks UI
# ---------------------------------------------------------------------------
with gr.Blocks(title="DocuExtract Studio | OmniOCR Pro") as demo:
    gr.Markdown(
        """
        # 📄 DocuExtract Studio (OmniOCR Pro)
        ### Enterprise Document Intelligence & Offline Arabic/English OCR Microservice

        👉 **Full Interactive Visual Studio:** [Open Full Studio Dashboard](/viewer)  
        👉 **Swagger REST API Docs:** [Interactive API Docs](/docs)  
        👉 **Health Check:** [Check Engine Health](/health)
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            image_input = gr.Image(
                type="pil",
                label="Upload Document (ID Card, Receipt, Invoice, Contract, etc.)"
            )
            document_input = gr.File(
                label="Or upload a PDF or multi-page TIFF (maximum 20 pages)",
                file_types=[".pdf", ".tif", ".tiff", ".bmp", ".jpg", ".jpeg", ".png", ".webp"],
                type="filepath"
            )
            extract_btn = gr.Button("🔍 Run OCR Extraction", variant="primary", size="lg")
        with gr.Column(scale=1):
            with gr.Row():
                out_type = gr.Textbox(label="Document Type", interactive=False)
                out_conf = gr.Textbox(label="OCR Confidence", interactive=False)
                out_time = gr.Textbox(label="Latency", interactive=False)
            out_fields = gr.JSON(label="Extracted Structured Fields")
            out_text = gr.TextArea(
                label="Extracted Full Text (Bidirectional Layout)",
                lines=8
            )

    extract_btn.click(
        fn=run_gradio_ocr,
        inputs=[image_input, document_input],
        outputs=[out_text, out_type, out_conf, out_time, out_fields]
    )


# ---------------------------------------------------------------------------
# Application Assembly
# ---------------------------------------------------------------------------
# Set root app reference
app = fastapi_app


# ---------------------------------------------------------------------------
# Entry Point — Hugging Face Spaces ZeroGPU compatible
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Hugging Face Spaces injects the PORT environment variable.
    # Default to 7860 for local Gradio-compatible development.
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"Starting OmniOCR Pro on http://0.0.0.0:{port}")

    # Launch Gradio interface (compatible with ZeroGPU runtime)
    launched_app, _, _ = demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=True,
        prevent_thread_lock=True,
    )

    # Attach all FastAPI routes (/docs, /health, /viewer, /ocr/extract, etc.)
    # so that studio viewer, Swagger docs, health checks, and REST APIs work without 404.
    for route in fastapi_app.routes:
        if getattr(route, "path", "") != "/":
            launched_app.routes.append(route)

    logger.info("OmniOCR Pro FastAPI routes and Gradio interface live.")
    demo.block_thread()
