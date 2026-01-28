"""
InsightsEngine - Generates actionable insights for "Hoy" page

SPRINT3-T3.1: Daily mission, weekly insights, and metrics
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from collections import Counter

from sqlalchemy import func, and_, or_, desc, text
from sqlalchemy.orm import Session

from api.schemas.insights import (
    TodayMission,
    HotLeadAction,
    BookingInfo,
    WeeklyInsights,
    WeeklyMetrics,
    ContentInsight,
    TrendInsight,
    ProductInsight,
    CompetitionInsight,
)

logger = logging.getLogger(__name__)


class InsightsEngine:
    """
    Generates actionable insights for the "Hoy" dashboard page.

    Features:
    - Today's mission with hot leads to close
    - Pending responses count
    - Today's bookings
    - Weekly content/trend/product/competition insights
    - Weekly metrics with deltas
    """

    def __init__(self, creator_id: str, db: Session):
        """
        Initialize InsightsEngine.

        Args:
            creator_id: Creator identifier (can be UUID or string like "manel")
            db: SQLAlchemy session
        """
        self.creator_id = creator_id
        self.db = db

    def get_today_mission(self) -> TodayMission:
        """
        Get today's actionable mission.

        Returns:
            TodayMission with:
            - hot_leads: Top 5 leads ready to close (intent > 0.7)
            - potential_revenue: Sum of deal values
            - pending_responses: Conversations awaiting reply
            - today_bookings: Today's scheduled meetings
        """
        try:
            # Get hot leads
            hot_leads = self._get_hot_leads(limit=5)

            # Calculate potential revenue
            potential_revenue = sum(lead.deal_value for lead in hot_leads)

            # Count pending responses
            pending_responses = self._count_pending_responses()

            # Get today's bookings
            today_bookings = self._get_today_bookings()

            # Count ghosts to reactivate
            ghost_count = self._count_ghosts_to_reactivate()

            return TodayMission(
                potential_revenue=potential_revenue,
                hot_leads=hot_leads,
                pending_responses=pending_responses,
                today_bookings=today_bookings,
                ghost_reactivation_count=ghost_count,
            )
        except Exception as e:
            logger.error(f"Error getting today mission: {e}")
            return TodayMission(
                potential_revenue=0.0,
                hot_leads=[],
                pending_responses=0,
                today_bookings=[],
                ghost_reactivation_count=0,
            )

    def get_weekly_insights(self) -> WeeklyInsights:
        """
        Get weekly insight cards.

        Returns:
            WeeklyInsights with 4 cards:
            - content: Most asked topic
            - trend: Emerging term (+% growth)
            - product: Most requested product
            - competition: Competitor mentions
        """
        try:
            return WeeklyInsights(
                content=self._get_content_insight(),
                trend=self._get_trend_insight(),
                product=self._get_product_insight(),
                competition=self._get_competition_insight(),
            )
        except Exception as e:
            logger.error(f"Error getting weekly insights: {e}")
            return WeeklyInsights()

    def get_weekly_metrics(self) -> WeeklyMetrics:
        """
        Get weekly metrics with deltas vs previous week.

        Returns:
            WeeklyMetrics with revenue, sales, response rate, etc.
        """
        try:
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            two_weeks_ago = now - timedelta(days=14)

            # Current week metrics
            current = self._get_metrics_for_period(week_ago, now)

            # Previous week metrics
            previous = self._get_metrics_for_period(two_weeks_ago, week_ago)

            # Calculate deltas
            revenue_delta = 0.0
            if previous["revenue"] > 0:
                revenue_delta = ((current["revenue"] - previous["revenue"]) / previous["revenue"]) * 100

            response_delta = current["response_rate"] - previous["response_rate"]

            return WeeklyMetrics(
                revenue=current["revenue"],
                revenue_delta=round(revenue_delta, 1),
                sales_count=current["sales_count"],
                sales_delta=current["sales_count"] - previous["sales_count"],
                response_rate=round(current["response_rate"], 2),
                response_delta=round(response_delta, 2),
                hot_leads_count=current["hot_leads_count"],
                conversations_count=current["conversations_count"],
                new_leads_count=current["new_leads_count"],
            )
        except Exception as e:
            logger.error(f"Error getting weekly metrics: {e}")
            return WeeklyMetrics()

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _get_hot_leads(self, limit: int = 5) -> List[HotLeadAction]:
        """
        Get hot leads ready to close.

        Query criteria:
        - purchase_intent_score > 0.7
        - status NOT IN (customer, fantasma)
        - Ordered by intent DESC, last_contact DESC
        """
        try:
            from api.models import FollowerMemoryDB

            # Query hot followers
            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.purchase_intent_score >= 0.7,
                FollowerMemoryDB.status.notin_(["customer", "cliente"]),
                FollowerMemoryDB.is_customer == False,
            ).order_by(
                desc(FollowerMemoryDB.purchase_intent_score),
                desc(FollowerMemoryDB.last_contact),
            ).limit(limit)

            results = query.all()
            hot_leads = []

            for follower in results:
                # Calculate hours ago
                hours_ago = 0
                if follower.last_contact:
                    try:
                        last_contact = datetime.fromisoformat(follower.last_contact.replace("Z", "+00:00"))
                        hours_ago = int((datetime.now(timezone.utc) - last_contact).total_seconds() / 3600)
                    except (ValueError, TypeError):
                        pass

                # Get last message
                last_message = ""
                if follower.last_messages:
                    # Get last user message
                    for msg in reversed(follower.last_messages):
                        if isinstance(msg, dict) and msg.get("role") == "user":
                            last_message = msg.get("content", "")[:100]
                            break

                # Build context from interests and objections
                context_parts = []
                if follower.interests:
                    context_parts.append(f"Interesado en: {', '.join(follower.interests[:2])}")
                if follower.objections_raised:
                    context_parts.append(f"Objeciones: {', '.join(follower.objections_raised[:2])}")
                context = ". ".join(context_parts) if context_parts else "Lead caliente"

                # Build action based on status
                action = self._get_recommended_action(follower)

                # Get deal value (estimate from product price if not set)
                deal_value = self._estimate_deal_value(follower)

                # Get product discussed
                product = follower.products_discussed[0] if follower.products_discussed else None

                hot_leads.append(HotLeadAction(
                    follower_id=follower.follower_id,
                    name=follower.name or "",
                    username=follower.username or follower.follower_id,
                    last_message=last_message,
                    hours_ago=hours_ago,
                    product=product,
                    deal_value=deal_value,
                    context=context,
                    action=action,
                    purchase_intent_score=follower.purchase_intent_score,
                ))

            return hot_leads

        except Exception as e:
            logger.error(f"Error getting hot leads: {e}")
            return []

    def _count_pending_responses(self) -> int:
        """
        Count conversations where last message is from user (awaiting response).
        """
        try:
            from api.models import FollowerMemoryDB

            # Query followers with messages
            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_messages.isnot(None),
            )

            count = 0
            for follower in query.all():
                if follower.last_messages:
                    # Check if last message is from user
                    last_msg = follower.last_messages[-1] if follower.last_messages else None
                    if isinstance(last_msg, dict) and last_msg.get("role") == "user":
                        count += 1

            return count

        except Exception as e:
            logger.error(f"Error counting pending responses: {e}")
            return 0

    def _get_today_bookings(self) -> List[BookingInfo]:
        """
        Get bookings scheduled for today.
        """
        try:
            from api.models import CalendarBooking

            today = datetime.now(timezone.utc).date()
            tomorrow = today + timedelta(days=1)

            query = self.db.query(CalendarBooking).filter(
                CalendarBooking.creator_id == self.creator_id,
                CalendarBooking.scheduled_at >= datetime.combine(today, datetime.min.time()),
                CalendarBooking.scheduled_at < datetime.combine(tomorrow, datetime.min.time()),
                CalendarBooking.status.in_(["scheduled", "confirmed"]),
            ).order_by(CalendarBooking.scheduled_at)

            bookings = []
            for booking in query.all():
                bookings.append(BookingInfo(
                    id=str(booking.id),
                    title=booking.meeting_type or "Meeting",
                    time=booking.scheduled_at.strftime("%H:%M") if booking.scheduled_at else "",
                    attendee_name=booking.guest_name or "Unknown",
                    attendee_email=booking.guest_email,
                    platform=booking.platform or "manual",
                ))

            return bookings

        except Exception as e:
            logger.error(f"Error getting today bookings: {e}")
            return []

    def _count_ghosts_to_reactivate(self) -> int:
        """
        Count ghost leads (inactive 7+ days) that could be reactivated.
        """
        try:
            from api.models import FollowerMemoryDB

            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            week_ago_str = week_ago.isoformat()

            # Count followers inactive for 7+ days
            query = self.db.query(func.count(FollowerMemoryDB.id)).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.status.in_(["ghost", "fantasma", "active", "interesado"]),
                FollowerMemoryDB.is_customer == False,
                FollowerMemoryDB.last_contact < week_ago_str,
            )

            return query.scalar() or 0

        except Exception as e:
            logger.error(f"Error counting ghosts: {e}")
            return 0

    def _get_content_insight(self) -> Optional[ContentInsight]:
        """
        Find the most asked topic this week.
        """
        try:
            from api.models import FollowerMemoryDB

            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            week_ago_str = week_ago.isoformat()

            # Get all interests from this week's conversations
            query = self.db.query(FollowerMemoryDB.interests).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_contact >= week_ago_str,
                FollowerMemoryDB.interests.isnot(None),
            )

            all_interests = []
            for row in query.all():
                if row.interests:
                    all_interests.extend(row.interests)

            if not all_interests:
                return None

            # Count occurrences
            counter = Counter(all_interests)
            most_common = counter.most_common(1)

            if not most_common:
                return None

            topic, count = most_common[0]
            total = len(all_interests)
            percentage = (count / total) * 100 if total > 0 else 0

            return ContentInsight(
                topic=topic,
                count=count,
                percentage=round(percentage, 1),
                quotes=[],  # Could extract from messages
                suggestion=f"Crea contenido sobre {topic}",
            )

        except Exception as e:
            logger.error(f"Error getting content insight: {e}")
            return None

    def _get_trend_insight(self) -> Optional[TrendInsight]:
        """
        Find emerging terms with highest growth vs last week.
        """
        try:
            from api.models import FollowerMemoryDB

            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            two_weeks_ago = now - timedelta(days=14)

            # This week's products discussed
            this_week = self.db.query(FollowerMemoryDB.products_discussed).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_contact >= week_ago.isoformat(),
            )

            # Last week's products discussed
            last_week = self.db.query(FollowerMemoryDB.products_discussed).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_contact >= two_weeks_ago.isoformat(),
                FollowerMemoryDB.last_contact < week_ago.isoformat(),
            )

            this_week_items = []
            for row in this_week.all():
                if row.products_discussed:
                    this_week_items.extend(row.products_discussed)

            last_week_items = []
            for row in last_week.all():
                if row.products_discussed:
                    last_week_items.extend(row.products_discussed)

            if not this_week_items:
                return None

            this_counter = Counter(this_week_items)
            last_counter = Counter(last_week_items)

            # Find term with highest growth
            best_term = None
            best_growth = 0

            for term, count in this_counter.items():
                last_count = last_counter.get(term, 0)
                if last_count == 0:
                    growth = 100  # New term
                else:
                    growth = ((count - last_count) / last_count) * 100

                if growth > best_growth:
                    best_growth = growth
                    best_term = term

            if not best_term:
                return None

            growth_str = "nuevo" if best_growth >= 100 else f"+{int(best_growth)}%"

            return TrendInsight(
                term=best_term,
                count=this_counter[best_term],
                growth=growth_str,
                suggestion=f"Menciona más sobre {best_term}",
            )

        except Exception as e:
            logger.error(f"Error getting trend insight: {e}")
            return None

    def _get_product_insight(self) -> Optional[ProductInsight]:
        """
        Find most requested product.
        """
        try:
            from api.models import FollowerMemoryDB

            week_ago = datetime.now(timezone.utc) - timedelta(days=7)

            query = self.db.query(FollowerMemoryDB.products_discussed).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_contact >= week_ago.isoformat(),
            )

            all_products = []
            for row in query.all():
                if row.products_discussed:
                    all_products.extend(row.products_discussed)

            if not all_products:
                return None

            counter = Counter(all_products)
            most_common = counter.most_common(1)

            if not most_common:
                return None

            product_name, count = most_common[0]

            # Estimate revenue (assuming default price)
            potential_revenue = count * 97.0  # Default price

            return ProductInsight(
                product_name=product_name,
                count=count,
                potential_revenue=potential_revenue,
                suggestion=f"Promociona {product_name}",
            )

        except Exception as e:
            logger.error(f"Error getting product insight: {e}")
            return None

    def _get_competition_insight(self) -> Optional[CompetitionInsight]:
        """
        Find competitor mentions in conversations.
        """
        try:
            # This is a placeholder - would need to scan messages for @mentions
            # or competitor names. For now, return None.
            return None

        except Exception as e:
            logger.error(f"Error getting competition insight: {e}")
            return None

    def _get_metrics_for_period(self, start: datetime, end: datetime) -> dict:
        """
        Get metrics for a specific time period.
        """
        try:
            from api.models import FollowerMemoryDB

            start_str = start.isoformat()
            end_str = end.isoformat()

            # Query followers active in period
            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_contact >= start_str,
                FollowerMemoryDB.last_contact < end_str,
            )

            followers = query.all()

            # Calculate metrics
            revenue = 0.0
            sales_count = 0
            hot_leads_count = 0
            total_messages = 0
            responses = 0

            for f in followers:
                if f.is_customer or f.status in ["customer", "cliente"]:
                    sales_count += 1
                    revenue += 97.0  # Default price

                if f.purchase_intent_score >= 0.7:
                    hot_leads_count += 1

                total_messages += f.total_messages or 0

                # Estimate response rate from messages
                if f.last_messages:
                    for msg in f.last_messages:
                        if isinstance(msg, dict) and msg.get("role") == "assistant":
                            responses += 1

            # Response rate
            response_rate = responses / total_messages if total_messages > 0 else 0.0

            return {
                "revenue": revenue,
                "sales_count": sales_count,
                "response_rate": min(response_rate, 1.0),
                "hot_leads_count": hot_leads_count,
                "conversations_count": len(followers),
                "new_leads_count": sum(1 for f in followers if f.status in ["new", "nuevo"]),
            }

        except Exception as e:
            logger.error(f"Error getting metrics for period: {e}")
            return {
                "revenue": 0.0,
                "sales_count": 0,
                "response_rate": 0.0,
                "hot_leads_count": 0,
                "conversations_count": 0,
                "new_leads_count": 0,
            }

    def _get_recommended_action(self, follower) -> str:
        """
        Get recommended action based on follower state.
        """
        # Check for objections
        if follower.objections_raised:
            last_objection = follower.objections_raised[-1]
            if "precio" in last_objection.lower() or "caro" in last_objection.lower():
                return "Ofrece plan de pagos o descuento"
            if "tiempo" in last_objection.lower():
                return "Destaca el formato flexible"
            return f"Resuelve objeción: {last_objection}"

        # Check intent level
        if follower.purchase_intent_score >= 0.9:
            return "Envía el link de pago"
        elif follower.purchase_intent_score >= 0.8:
            return "Agenda una llamada de cierre"
        elif follower.purchase_intent_score >= 0.7:
            return "Envía más información del producto"

        return "Continúa la conversación"

    def _estimate_deal_value(self, follower) -> float:
        """
        Estimate deal value from products discussed or default price.
        """
        # Try to get creator's product price
        try:
            from api.models import Creator
            creator = self.db.query(Creator).filter(
                Creator.name == self.creator_id
            ).first()

            if creator and creator.product_price:
                return float(creator.product_price)
        except Exception:
            pass

        # Default value
        return 97.0
