from pydantic import BaseModel, Field
from typing import Optional


class FAQCreate(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    category: Optional[str] = None


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None


class AboutUpdate(BaseModel):
    content: str = Field(..., min_length=1)


class KnowledgeAdd(BaseModel):
    text: str = Field(..., min_length=1)
    doc_type: Optional[str] = None
    metadata: Optional[dict] = None
