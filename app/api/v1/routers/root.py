import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.config import settings
from app.domain.schemas.responses import VersionResponse
from app.api.v1.routers.viewer import get_viewer_html

router = APIRouter(tags=["Root"])

@router.get("/", response_class=HTMLResponse, summary="Root Endpoint - Interactive Web Viewer")
async def root_endpoint():
    # On Hugging Face Spaces, Gradio is mounted at /gradio
    # Serve the HTML viewer if it exists, otherwise redirect to /gradio
    html = get_viewer_html()
    if html:
        headers = {
            "Content-Security-Policy": "frame-ancestors *",
            "X-Frame-Options": "ALLOWALL"
        }
        return HTMLResponse(content=html, headers=headers)
    # Fallback: redirect to Gradio UI or API docs
    return RedirectResponse(url="/gradio")

@router.get("/info", summary="Application Metadata")
async def info_endpoint():
    return {
        "app": settings.PROJECT_NAME,
        "description": settings.PROJECT_DESCRIPTION,
        "version": settings.PROJECT_VERSION,
        "viewer_url": "/viewer",
        "docs_url": "/docs"
    }

@router.get("/version", response_model=VersionResponse, summary="Get Application Version")
async def version_endpoint():
    return VersionResponse(version=settings.PROJECT_VERSION)
