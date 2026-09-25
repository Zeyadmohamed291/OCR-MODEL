# ==============================================================================
# Production Dockerfile for High-Performance CPU OCR Microservice
# FastAPI + PyTorch (CPU-only) + EasyOCR + OpenCV Headless
# MLOps & Production Hardened
# ==============================================================================

FROM python:3.11-slim-bookworm AS runtime

# ------------------------------------------------------------------------------
# 1. Environment Configurations
# ------------------------------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # PyTorch CPU thread management (prevents thread thrashing on multi-core CPUs)
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    # Application settings
    MODEL_DIR="/app/models/easyocr" \
    PORT=7860 \
    WEB_CONCURRENCY=1 \
    LOGGING_LEVEL="INFO"

# ------------------------------------------------------------------------------
# 2. System Dependencies (OpenCV, PyTorch math, and healthcheck utilities)
# ------------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ------------------------------------------------------------------------------
# 3. Security: Non-root User & Directory Initialization
# ------------------------------------------------------------------------------
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser && \
    mkdir -p /app/logs /app/models/easyocr /home/appuser/.EasyOCR && \
    chown -R appuser:appgroup /app /home/appuser

# ------------------------------------------------------------------------------
# 4. Dependency Installation with Layer Caching
# ------------------------------------------------------------------------------
# Pre-install CPU-only PyTorch & Torchvision from official PyTorch CPU wheel index
# This slashes Docker image size by ~4GB by eliminating CUDA 12 GPU runtimes.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install application requirements while enforcing the CPU wheel index for any sub-dependencies
COPY --chown=appuser:appgroup requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# ------------------------------------------------------------------------------
# 5. Pre-caching EasyOCR Weights (Eliminates Cold-Start Penalty)
# Executed as appuser to guarantee proper permissions on cached weights
# ------------------------------------------------------------------------------
USER appuser
RUN python -c "import easyocr; reader = easyocr.Reader(['ar', 'en'], gpu=False, model_storage_directory='/app/models/easyocr', download_enabled=True)"

# ------------------------------------------------------------------------------
# 6. Copy Application Source Code
# ------------------------------------------------------------------------------
# Code is copied after dependencies and model weights to maximize Docker layer caching
COPY --chown=appuser:appgroup . .

# Ensure runtime directory permissions
RUN mkdir -p /app/logs

EXPOSE 7860

# ------------------------------------------------------------------------------
# 7. Production Healthcheck
# ------------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# ------------------------------------------------------------------------------
# 8. Production Server Execution
# Includes proxy headers for cloud reverse proxies and keep-alive timeout
# ------------------------------------------------------------------------------
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers ${WEB_CONCURRENCY:-1} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\" --timeout-keep-alive 65"]
