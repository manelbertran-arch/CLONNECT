"""
Ingestion V2 - Zero Hallucination System

Principio fundamental: "Si no puedo PROBAR que es real, NO EXISTE"

Este módulo implementa:
- Detección de productos con sistema de señales (mínimo 3)
- Sanity checks que abortan si algo es sospechoso
- Re-verificación de cada producto
- NUNCA inventa datos - si no está, es NULL
"""

from .product_detector import (
    ProductSignal,
    DetectedProduct,
    ProductDetector,
    SuspiciousExtractionError
)

from .sanity_checker import (
    CheckResult,
    VerificationResult,
    SanityChecker
)

from .pipeline import (
    IngestionV2Result,
    IngestionV2Pipeline,
    ingest_website_v2
)

from .instagram_ingestion import (
    InstagramSanityResult,
    InstagramIngestionResult,
    InstagramPostSanityChecker,
    InstagramIngestionV2,
    ingest_instagram_v2
)

__all__ = [
    # Website ingestion
    'ProductSignal',
    'DetectedProduct',
    'ProductDetector',
    'SuspiciousExtractionError',
    'CheckResult',
    'VerificationResult',
    'SanityChecker',
    'IngestionV2Result',
    'IngestionV2Pipeline',
    'ingest_website_v2',
    # Instagram ingestion
    'InstagramSanityResult',
    'InstagramIngestionResult',
    'InstagramPostSanityChecker',
    'InstagramIngestionV2',
    'ingest_instagram_v2',
]
