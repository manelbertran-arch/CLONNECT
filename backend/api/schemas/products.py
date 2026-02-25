from pydantic import BaseModel, Field
from typing import Optional


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    short_description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    currency: str = Field(default="EUR", max_length=10)
    category: Optional[str] = None
    product_type: Optional[str] = None
    url: Optional[str] = None
    payment_link: Optional[str] = None
    source_url: Optional[str] = None
    is_free: Optional[bool] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    short_description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=10)
    category: Optional[str] = None
    product_type: Optional[str] = None
    url: Optional[str] = None
    payment_link: Optional[str] = None
    source_url: Optional[str] = None
    is_free: Optional[bool] = None
    is_active: Optional[bool] = None
