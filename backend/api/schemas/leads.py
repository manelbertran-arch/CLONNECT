from pydantic import BaseModel, Field
from typing import Optional, List


class LeadCreate(BaseModel):
    platform_user_id: str = Field(..., min_length=1)
    name: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    platform: str = Field(default="instagram")
    source: Optional[str] = None
    status: Optional[str] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    deal_value: Optional[float] = None
    source: Optional[str] = None
    assigned_to: Optional[str] = None


class LeadStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1)
    reason: Optional[str] = None
