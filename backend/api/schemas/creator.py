"""Creator schemas"""
from pydantic import BaseModel
from typing import Optional, Dict, Any

class CreatorConfig(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    bot_active: bool = False
    clone_name: Optional[str] = None
    clone_tone: Optional[str] = "friendly"
    clone_style: Optional[str] = None
    welcome_message: Optional[str] = None

class CreatorUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    bot_active: Optional[bool] = None
    clone_name: Optional[str] = None
    clone_tone: Optional[str] = None
    clone_style: Optional[str] = None
    clone_vocabulary: Optional[str] = None
    welcome_message: Optional[str] = None
    personality: Optional[Dict[str, Any]] = None
