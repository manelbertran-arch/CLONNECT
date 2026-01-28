"""
Request Pydantic schemas.
Extracted from main.py following TDD.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CreateCreatorRequest(BaseModel):
    """Request schema for creating a new creator."""
    id: str
    name: str
    instagram_handle: str
    personality: Optional[Dict[str, Any]] = None
    emoji_style: Optional[str] = "moderate"
    sales_style: Optional[str] = "soft"


class CreateProductRequest(BaseModel):
    """Request schema for creating a new product."""
    id: str
    name: str
    description: str
    price: float
    currency: str = "EUR"
    payment_link: str = ""
    category: str = ""
    features: List[str] = []
    keywords: List[str] = []
