"""
Pydantic schemas for Clonnect API.
"""
from api.schemas.audience import FollowerDetailResponse
from api.schemas.requests import CreateCreatorRequest, CreateProductRequest

# New validated request schemas (HIGH-7)
from api.schemas.products import ProductCreate, ProductUpdate
from api.schemas.leads import LeadCreate, LeadUpdate, LeadStatusUpdate
from api.schemas.knowledge import FAQCreate, FAQUpdate, AboutUpdate, KnowledgeAdd
from api.schemas.messages import SendMessage, FollowerStatusUpdate
from api.schemas.payments import PurchaseRecord

__all__ = [
    "CreateCreatorRequest",
    "CreateProductRequest",
    "FollowerDetailResponse",
    "ProductCreate", "ProductUpdate",
    "LeadCreate", "LeadUpdate", "LeadStatusUpdate",
    "FAQCreate", "FAQUpdate", "AboutUpdate", "KnowledgeAdd",
    "SendMessage", "FollowerStatusUpdate",
    "PurchaseRecord",
]
