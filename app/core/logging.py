import logging
import json
import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage()
        }
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
            
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def setup_logging():
    logging_level = getattr(logging, settings.LOGGING_LEVEL.upper(), logging.INFO)
    
    json_formatter = JSONFormatter()
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(json_formatter)
    
    file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
    file_handler.setFormatter(json_formatter)
    
    logging.basicConfig(
        level=logging_level,
        handlers=[console_handler, file_handler],
        force=True
    )
    
    logger = logging.getLogger("ocr_microservice")
    logger.setLevel(logging_level)
    return logger

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger = logging.getLogger("ocr_microservice")
        
        # Inject global Request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        start_time = time.time()
        logger.info(f"[{request_id}] Incoming request: {request.method} {request.url.path}")
        
        try:
            response = await call_next(request)
            process_time = (time.time() - start_time) * 1000.0
            
            # Inject headers for tracking
            response.headers["X-Process-Time-Ms"] = str(round(process_time, 2))
            response.headers["X-Request-ID"] = request_id
            
            logger.info(f"[{request_id}] Request completed: {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.2f}ms")
            return response
        except Exception as e:
            process_time = (time.time() - start_time) * 1000.0
            logger.error(f"[{request_id}] Request failed: {request.method} {request.url.path} - Error: {str(e)} - Time: {process_time:.2f}ms", exc_info=True)
            raise
