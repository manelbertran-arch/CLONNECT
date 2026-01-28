"""
Audiencia API Schemas

SPRINT4-T4.1: Schemas for aggregated audience data endpoints
"""
from pydantic import BaseModel
from typing import List, Optional


class TopicAggregation(BaseModel):
    """Aggregated conversation topic"""
    topic: str
    count: int
    percentage: float
    quotes: List[str]  # Real examples (max 5)
    users: List[str]   # Usernames who mentioned it


class ObjectionAggregation(BaseModel):
    """Aggregated objection"""
    objection: str
    count: int
    percentage: float
    quotes: List[str]
    suggestion: str
    resolved_count: int = 0
    pending_count: int = 0


class CompetitionMention(BaseModel):
    """Competition mention"""
    competitor: str  # @username
    count: int
    sentiment: str   # "positivo", "neutral", "negativo"
    context: List[str]  # Phrases where mentioned
    suggestion: str


class TrendItem(BaseModel):
    """Emerging trend"""
    term: str
    count_this_week: int
    count_last_week: int
    growth_percentage: float
    quotes: List[str]


class ContentRequest(BaseModel):
    """Content requested by audience"""
    topic: str
    count: int
    questions: List[str]  # Specific questions
    suggestion: str


class ProductRequest(BaseModel):
    """Product requested that doesn't exist"""
    product_name: str
    count: int
    quotes: List[str]
    potential_revenue: float


class PerceptionItem(BaseModel):
    """What they think about you"""
    aspect: str  # "expertise", "precio", "atencion"
    positive_count: int
    negative_count: int
    quotes_positive: List[str]
    quotes_negative: List[str]


# Response models
class TopicsResponse(BaseModel):
    """Response for topics endpoint"""
    total_conversations: int
    topics: List[TopicAggregation]


class ObjectionsResponse(BaseModel):
    """Response for objections endpoint"""
    total_with_objections: int
    objections: List[ObjectionAggregation]


class CompetitionResponse(BaseModel):
    """Response for competition endpoint"""
    total_mentions: int
    competitors: List[CompetitionMention]


class TrendsResponse(BaseModel):
    """Response for trends endpoint"""
    period: str = "week"
    trends: List[TrendItem]


class ContentRequestsResponse(BaseModel):
    """Response for content requests endpoint"""
    total_requests: int
    requests: List[ContentRequest]


class ProductRequestsResponse(BaseModel):
    """Response for product requests endpoint"""
    total_requests: int
    products: List[ProductRequest]


class PerceptionResponse(BaseModel):
    """Response for perception endpoint"""
    total_analyzed: int
    perceptions: List[PerceptionItem]
