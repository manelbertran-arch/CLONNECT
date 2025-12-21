"""Lead schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = None
    platform: str = Field(default="manual")
    notes: Optional[str] = None

class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None
    score: Optional[int] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None

class LeadResponse(BaseModel):
    id: str
    platform_user_id: Optional[str] = None
    platform: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    status: str
    score: int
    purchase_intent: float
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
