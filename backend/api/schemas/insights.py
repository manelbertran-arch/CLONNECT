"""
Insights API Schemas

SPRINT3-T3.1: Schemas for InsightsEngine and /insights/* endpoints
"""
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class HotLeadAction(BaseModel):
    """Lead ready to close with actionable context"""
    follower_id: str
    name: str
    username: str
    profile_pic_url: Optional[str] = None
    last_message: str
    hours_ago: int
    product: Optional[str] = None
    deal_value: float = 0.0
    context: str  # "Madre de 3, ya aceptó cuotas"
    action: str   # "Envíale el link de pago"
    purchase_intent_score: float = 0.0


class BookingInfo(BaseModel):
    """Today's booking info"""
    id: str
    title: str
    time: str
    attendee_name: str
    attendee_email: Optional[str] = None
    platform: str


class TodayMission(BaseModel):
    """Daily mission with actionable priorities"""
    potential_revenue: float
    hot_leads: List[HotLeadAction]
    pending_responses: int
    today_bookings: List[BookingInfo]
    ghost_reactivation_count: int = 0


class ContentInsight(BaseModel):
    """Most asked topic insight"""
    topic: str
    count: int
    percentage: float
    quotes: List[str]
    suggestion: str


class TrendInsight(BaseModel):
    """Emerging trend insight"""
    term: str
    count: int
    growth: str  # "+50%" or "new"
    suggestion: str


class ProductInsight(BaseModel):
    """Product demand insight"""
    product_name: str
    count: int
    potential_revenue: float
    suggestion: str


class CompetitionInsight(BaseModel):
    """Competitor mentions insight"""
    competitor: str
    count: int
    sentiment: str  # "positive", "neutral", "negative"
    suggestion: str


class WeeklyInsights(BaseModel):
    """Four insight cards for weekly analysis"""
    content: Optional[ContentInsight] = None
    trend: Optional[TrendInsight] = None
    product: Optional[ProductInsight] = None
    competition: Optional[CompetitionInsight] = None


class WeeklyMetrics(BaseModel):
    """Weekly metrics with deltas vs previous week"""
    revenue: float = 0.0
    revenue_delta: float = 0.0  # percentage change
    sales_count: int = 0
    sales_delta: int = 0  # absolute change
    response_rate: float = 0.0  # 0-1
    response_delta: float = 0.0  # percentage points
    hot_leads_count: int = 0
    conversations_count: int = 0
    new_leads_count: int = 0
