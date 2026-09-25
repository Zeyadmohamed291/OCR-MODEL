import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, FileResponse

router = APIRouter(tags=["Document Viewer & Samples"])

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../"))
HTML_PATH = os.path.join(BASE_DIR, "public", "index.html")
TESTS_DIR = os.path.join(BASE_DIR, "tests")

def get_viewer_html() -> str:
    if os.path.exists(HTML_PATH):
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return ""

@router.get("/viewer", response_class=HTMLResponse, summary="OmniOCR Pro Interactive Intelligence Dashboard")
async def document_viewer():
    """Serves the state-of-the-art visual document intelligence web viewer."""
    html_content = get_viewer_html()
    if not html_content:
        raise HTTPException(status_code=404, detail="Viewer template not found.")
    headers = {
        "Content-Security-Policy": "frame-ancestors *",
        "X-Frame-Options": "ALLOWALL"
    }
    return HTMLResponse(content=html_content, headers=headers)

@router.get("/samples/{image_name}", summary="Serve sample document images for 1-click UI demos")
@router.get("/api/v1/samples/{image_name}", summary="Serve sample document images for 1-click UI demos")
async def get_sample_image(image_name: str):
    """Securely serves sample test images (e.g. Egyptian IDs, English documents) for immediate UI testing."""
    # Prevent directory traversal
    clean_name = os.path.basename(image_name)
    sample_path = os.path.join(TESTS_DIR, clean_name)
    
    if not os.path.exists(sample_path) or not os.path.isfile(sample_path):
        raise HTTPException(status_code=404, detail=f"Sample image '{clean_name}' not found.")
    
    # Determine content type
    ext = os.path.splitext(clean_name)[1].lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(sample_path, media_type=media_type)
