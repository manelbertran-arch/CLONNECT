from pydantic import BaseModel, Field
from typing import Optional


class PurchaseRecord(BaseModel):
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    amount: Optional[float] = Field(None, ge=0)
    currency: str = Field(default="EUR", max_length=10)
    platform: Optional[str] = None
    follower_id: Optional[str] = None
    external_id: Optional[str] = None
