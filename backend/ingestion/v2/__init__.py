"""
Zero-Hallucination Ingestion System V2
Principle: "If I can't PROVE it's real, it DOESN'T EXIST"
"""

from .models import DetectedProduct, SignalResult, VerificationResult, IngestionResult
from .product_detector import ProductDetector
from .sanity_checker import SanityChecker
from .pipeline import IngestionPipeline

__all__ = [
    'DetectedProduct',
    'SignalResult',
    'VerificationResult',
    'IngestionResult',
    'ProductDetector',
    'SanityChecker',
    'IngestionPipeline'
]
