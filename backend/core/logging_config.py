"""
Centralized logging configuration for Clonnect.

Usage:
    from core.logging_config import setup_logging, get_logger

    # At app startup (once):
    setup_logging()

    # In each module:
    logger = get_logger(__name__)
    logger.info("Something happened")
"""

import logging
import logging.config
import os
from typing import Optional


def setup_logging(level: Optional[str] = None) -> None:
    """
    Configure logging for the entire application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to LOG_LEVEL env var or INFO.

    Uses dictConfig to avoid conflicts with uvicorn/fastapi logging.
    """
    log_level = level or os.getenv("LOG_LEVEL", "INFO").upper()

    # Validate log level
    numeric_level = getattr(logging, log_level, None)
    if not isinstance(numeric_level, int):
        log_level = "INFO"
        numeric_level = logging.INFO

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            # Root logger
            "": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            # Clonnect application loggers
            "core": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "api": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "services": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "ingestion": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            # Third-party loggers - reduce noise
            "httpx": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "urllib3": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(config)

    # Log the configuration
    root_logger = logging.getLogger()
    root_logger.debug(f"Logging configured: level={log_level}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
