"""
Logging configuration for Clonnect API
"""
import logging
import sys
from typing import Optional
import uuid

class RequestIdFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.request_id: Optional[str] = None
    
    def filter(self, record):
        record.request_id = self.request_id or "no-request"
        return True

request_id_filter = RequestIdFilter()

def setup_logging(level: str = "INFO"):
    log_format = "%(asctime)s | %(levelname)s | %(request_id)s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logging.getLogger().addFilter(request_id_filter)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

def set_request_id(request_id: Optional[str] = None):
    request_id_filter.request_id = request_id or str(uuid.uuid4())[:8]

def get_request_id() -> Optional[str]:
    return request_id_filter.request_id

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if request_id_filter not in logger.filters:
        logger.addFilter(request_id_filter)
    return logger
