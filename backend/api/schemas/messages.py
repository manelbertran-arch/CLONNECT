from pydantic import BaseModel, Field
from typing import Optional


class SendMessage(BaseModel):
    follower_id: Optional[str] = None
    message: str = Field(..., min_length=1)
    lead_id: Optional[str] = None


class FollowerStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1)
