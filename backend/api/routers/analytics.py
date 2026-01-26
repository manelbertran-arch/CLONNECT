"""
Analytics API endpoints for Business Intelligence.

Provides comprehensive analytics across:
- Summary: 6 KPIs with period comparison
- Instagram: Posts, engagement, correlation to DMs
- Audience: Intents, objections, FAQ, funnel
- Sales: Revenue, products, trends
- Predictions: Hot leads, churn, recommendations
- Reports: Weekly reports history
- Trends: Time series data for charts
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text, distinct, or_
from datetime import datetime, timedelta
from typing import Optional
from collections import Counter
import logging

from api.database import get_db
from api.models import (
    Lead, Product, Creator, ConversationEmbedding,
    RAGDocument, WeeklyReport, CreatorMetricsDaily,
    InstagramPost
)
from core.sales_tracker import get_sales_tracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


# ============================================================================
# HELPERS
# ============================================================================

def get_date_range(period: str) -> tuple:
    """Convert period string to date range."""
    now = datetime.utcnow()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    elif period == "90d":
        start = now - timedelta(days=90)
    elif period == "year":
        start = now - timedelta(days=365)
    else:
        start = now - timedelta(days=30)
    return start, now


def get_previous_range(start: datetime, end: datetime) -> tuple:
    """Calculate equivalent previous period for comparison."""
    duration = end - start
    prev_end = start
    prev_start = prev_end - duration
    return prev_start, prev_end


def calc_change(current: float, previous: float) -> float:
    """Calculate percentage change."""
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


def get_creator_name(db: Session, creator_id: str) -> str:
    """Get creator name from UUID or return as-is if string name."""
    creator = db.query(Creator).filter(Creator.name == creator_id).first()
    if creator:
        return creator.name
    try:
        creator = db.query(Creator).filter(Creator.id == creator_id).first()
        if creator:
            return creator.name
    except:
        pass
    return creator_id


# ============================================================================
# LEGACY SALES ENDPOINTS (preserved)
# ============================================================================

@router.get("/{creator_id}/sales/stats")
async def get_sales_stats(creator_id: str, days: int = 30):
    """Get sales and conversion statistics"""
    tracker = get_sales_tracker()
    stats = tracker.get_stats(creator_id, days)
    return {"status": "ok", "creator_id": creator_id, "stats": stats}


@router.get("/{creator_id}/sales/activity")
async def get_recent_activity(creator_id: str, limit: int = 20):
    """Get recent clicks and sales activity"""
    tracker = get_sales_tracker()
    activity = tracker.get_recent_activity(creator_id, limit)
    return {"status": "ok", "creator_id": creator_id, "activity": activity, "count": len(activity)}


@router.get("/{creator_id}/sales/follower/{follower_id}")
async def get_follower_journey(creator_id: str, follower_id: str):
    """Get purchase journey for a specific follower"""
    tracker = get_sales_tracker()
    journey = tracker.get_follower_journey(creator_id, follower_id)
    return {"status": "ok", "follower_id": follower_id, "journey": journey}


@router.post("/{creator_id}/sales/click")
async def record_click(
    creator_id: str,
    product_id: str,
    follower_id: str,
    product_name: str = "",
    link_url: str = ""
):
    """Manually record a product link click"""
    tracker = get_sales_tracker()
    tracker.record_click(creator_id, product_id, follower_id, product_name, link_url)
    return {"status": "ok", "message": "Click recorded"}


# ============================================================================
# SUMMARY ENDPOINT - 6 Main KPIs
# ============================================================================

@router.get("/{creator_id}/summary")
async def get_summary(
    creator_id: str,
    period: str = Query("30d", regex="^(today|7d|30d|90d|year)$"),
    db: Session = Depends(get_db)
):
    """
    Executive summary with 6 main KPIs + comparisons.
    """
    start, end = get_date_range(period)
    prev_start, prev_end = get_previous_range(start, end)
    creator_name = get_creator_name(db, creator_id)

    try:
        # Revenue from leads marked as customers
        revenue_q = text("""
            SELECT COALESCE(SUM(deal_value), 0) FROM leads
            WHERE creator_id IN (SELECT id FROM creators WHERE name = :cid OR id::text = :cid)
            AND status = 'cliente' AND last_contact_at >= :s AND last_contact_at <= :e
        """)
        revenue_current = float(db.execute(revenue_q, {"cid": creator_id, "s": start, "e": end}).scalar() or 0)
        revenue_previous = float(db.execute(revenue_q, {"cid": creator_id, "s": prev_start, "e": prev_end}).scalar() or 0)

        # Conversions
        conv_q = text("""
            SELECT COUNT(*) FROM leads
            WHERE creator_id IN (SELECT id FROM creators WHERE name = :cid OR id::text = :cid)
            AND status = 'cliente' AND last_contact_at >= :s AND last_contact_at <= :e
        """)
        conv_current = int(db.execute(conv_q, {"cid": creator_id, "s": start, "e": end}).scalar() or 0)
        conv_previous = int(db.execute(conv_q, {"cid": creator_id, "s": prev_start, "e": prev_end}).scalar() or 0)

        # New Leads
        leads_q = text("""
            SELECT COUNT(*) FROM leads
            WHERE creator_id IN (SELECT id FROM creators WHERE name = :cid OR id::text = :cid)
            AND first_contact_at >= :s AND first_contact_at <= :e
        """)
        leads_current = int(db.execute(leads_q, {"cid": creator_id, "s": start, "e": end}).scalar() or 0)
        leads_previous = int(db.execute(leads_q, {"cid": creator_id, "s": prev_start, "e": prev_end}).scalar() or 0)

        # DMs
        dms_current = db.query(func.count(ConversationEmbedding.id)).filter(
            ConversationEmbedding.creator_id == creator_name,
            ConversationEmbedding.message_role == 'user',
            ConversationEmbedding.created_at >= start,
            ConversationEmbedding.created_at <= end
        ).scalar() or 0

        dms_previous = db.query(func.count(ConversationEmbedding.id)).filter(
            ConversationEmbedding.creator_id == creator_name,
            ConversationEmbedding.message_role == 'user',
            ConversationEmbedding.created_at >= prev_start,
            ConversationEmbedding.created_at <= prev_end
        ).scalar() or 0

        # Posts
        posts_current = db.query(func.count(InstagramPost.id)).filter(
            InstagramPost.creator_id == creator_name,
            InstagramPost.created_at >= start,
            InstagramPost.created_at <= end
        ).scalar() or 0

        posts_previous = db.query(func.count(InstagramPost.id)).filter(
            InstagramPost.creator_id == creator_name,
            InstagramPost.created_at >= prev_start,
            InstagramPost.created_at <= prev_end
        ).scalar() or 0

        # Sentiment from daily metrics
        sent_q = text("""
            SELECT AVG(sentiment_score) FROM creator_metrics_daily
            WHERE creator_id = :cid AND date >= :s::date AND date <= :e::date
        """)
        sent_current = float(db.execute(sent_q, {"cid": creator_name, "s": start, "e": end}).scalar() or 0)
        sent_previous = float(db.execute(sent_q, {"cid": creator_name, "s": prev_start, "e": prev_end}).scalar() or 0)

        db.rollback()

        return {
            "status": "ok",
            "period": period,
            "date_range": {"start": start.isoformat(), "end": end.isoformat()},
            "kpis": {
                "revenue": {"value": revenue_current, "change": calc_change(revenue_current, revenue_previous), "previous": revenue_previous},
                "conversions": {"value": conv_current, "change": calc_change(conv_current, conv_previous), "previous": conv_previous},
                "leads": {"value": leads_current, "change": calc_change(leads_current, leads_previous), "previous": leads_previous},
                "dms": {"value": dms_current, "change": calc_change(dms_current, dms_previous), "previous": dms_previous},
                "posts": {"value": posts_current, "change": calc_change(posts_current, posts_previous), "previous": posts_previous},
                "sentiment": {"value": round(sent_current, 2), "change": round(sent_current - sent_previous, 2), "previous": round(sent_previous, 2)}
            }
        }

    except Exception as e:
        logger.error(f"Error in summary: {e}")
        db.rollback()
        return {"status": "error", "error": str(e), "kpis": {
            "revenue": {"value": 0, "change": 0, "previous": 0},
            "conversions": {"value": 0, "change": 0, "previous": 0},
            "leads": {"value": 0, "change": 0, "previous": 0},
            "dms": {"value": 0, "change": 0, "previous": 0},
            "posts": {"value": 0, "change": 0, "previous": 0},
            "sentiment": {"value": 0, "change": 0, "previous": 0}
        }}


# ============================================================================
# INSTAGRAM TAB
# ============================================================================

@router.get("/{creator_id}/instagram")
async def get_instagram_analytics(
    creator_id: str,
    period: str = Query("30d"),
    db: Session = Depends(get_db)
):
    """Instagram analytics: posts, engagement, best times, post→DM correlation."""
    start, end = get_date_range(period)
    creator_name = get_creator_name(db, creator_id)

    try:
        posts = db.query(InstagramPost).filter(
            InstagramPost.creator_id == creator_name,
            InstagramPost.created_at >= start,
            InstagramPost.created_at <= end
        ).all()

        posts_by_type = {}
        all_posts_data = []
        hour_engagement = {}
        day_engagement = {}

        for post in posts:
            media_type = post.media_type or 'IMAGE'
            likes = post.likes_count or 0
            comments = post.comments_count or 0
            engagement = likes + comments

            if media_type not in posts_by_type:
                posts_by_type[media_type] = {'count': 0, 'total_likes': 0, 'total_comments': 0, 'total_engagement': 0}

            posts_by_type[media_type]['count'] += 1
            posts_by_type[media_type]['total_likes'] += likes
            posts_by_type[media_type]['total_comments'] += comments
            posts_by_type[media_type]['total_engagement'] += engagement

            all_posts_data.append({
                'id': str(post.id),
                'media_type': media_type,
                'caption': (post.caption or '')[:100],
                'likes': likes,
                'comments': comments,
                'engagement': engagement,
                'created_at': post.created_at.isoformat() if post.created_at else None,
                'permalink': post.permalink
            })

            if post.created_at:
                hour = post.created_at.hour
                day = post.created_at.weekday()
                hour_engagement.setdefault(hour, {'total': 0, 'count': 0})
                hour_engagement[hour]['total'] += engagement
                hour_engagement[hour]['count'] += 1
                day_engagement.setdefault(day, {'total': 0, 'count': 0})
                day_engagement[day]['total'] += engagement
                day_engagement[day]['count'] += 1

        # Calculate averages
        for mt in posts_by_type:
            c = posts_by_type[mt]['count']
            posts_by_type[mt]['avg_engagement'] = round(posts_by_type[mt]['total_engagement'] / c, 1) if c > 0 else 0

        top_posts = sorted(all_posts_data, key=lambda x: x['engagement'], reverse=True)[:10]

        # Best time
        best_hour = max(hour_engagement, key=lambda h: hour_engagement[h]['total'] / hour_engagement[h]['count'] if hour_engagement[h]['count'] > 0 else 0, default=None)
        day_names = ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo']
        best_day = max(day_engagement, key=lambda d: day_engagement[d]['total'] / day_engagement[d]['count'] if day_engagement[d]['count'] > 0 else 0, default=None)
        best_day_name = day_names[best_day] if best_day is not None else None

        # Post to DM correlation
        post_dm_correlation = []
        for post in posts[:5]:
            if post.created_at:
                dm_count = db.query(func.count(ConversationEmbedding.id)).filter(
                    ConversationEmbedding.creator_id == creator_name,
                    ConversationEmbedding.message_role == 'user',
                    ConversationEmbedding.created_at >= post.created_at,
                    ConversationEmbedding.created_at <= post.created_at + timedelta(hours=48)
                ).scalar() or 0
                post_dm_correlation.append({
                    'post_id': str(post.id),
                    'caption': (post.caption or '')[:50],
                    'dms_generated': dm_count,
                    'media_type': post.media_type
                })

        db.rollback()

        return {
            "status": "ok",
            "period": period,
            "total_posts": len(posts),
            "by_type": posts_by_type,
            "top_posts": top_posts,
            "best_time": {
                "hour": f"{best_hour}:00" if best_hour is not None else None,
                "day": best_day_name,
                "insight": f"Posts a las {best_hour}:00 los {best_day_name} tienen mejor engagement" if best_hour and best_day_name else None
            },
            "post_to_dm_correlation": post_dm_correlation
        }

    except Exception as e:
        logger.error(f"Error in instagram analytics: {e}")
        db.rollback()
        return {"status": "error", "error": str(e), "total_posts": 0, "by_type": {}, "top_posts": [], "best_time": {}}


# ============================================================================
# AUDIENCE TAB
# ============================================================================

@router.get("/{creator_id}/audience")
async def get_audience_analytics(
    creator_id: str,
    period: str = Query("30d"),
    db: Session = Depends(get_db)
):
    """Audience analytics: intents, objections, questions, funnel."""
    start, end = get_date_range(period)
    creator_name = get_creator_name(db, creator_id)

    try:
        messages = db.query(ConversationEmbedding).filter(
            ConversationEmbedding.creator_id == creator_name,
            ConversationEmbedding.message_role == 'user',
            ConversationEmbedding.created_at >= start,
            ConversationEmbedding.created_at <= end
        ).all()

        total_messages = len(messages)
        unique_users = db.query(func.count(distinct(ConversationEmbedding.follower_id))).filter(
            ConversationEmbedding.creator_id == creator_name,
            ConversationEmbedding.message_role == 'user',
            ConversationEmbedding.created_at >= start,
            ConversationEmbedding.created_at <= end
        ).scalar() or 0

        # Intent distribution
        intent_counts = Counter()
        objections = []
        questions = []

        for msg in messages:
            metadata = msg.msg_metadata or {}
            intent = metadata.get('intent', 'unknown')
            intent_counts[intent] += 1

            if 'objection' in intent.lower() or 'precio' in (msg.content or '').lower():
                objections.append({'type': intent, 'content': (msg.content or '')[:100]})
            if msg.content and '?' in msg.content:
                questions.append({'content': msg.content[:150]})

        total_intents = sum(intent_counts.values())
        intent_distribution = [
            {"intent": i, "count": c, "percentage": round((c / total_intents) * 100, 1) if total_intents > 0 else 0}
            for i, c in intent_counts.most_common(10)
        ]

        # Objections summary
        obj_types = Counter(o['type'] for o in objections)
        obj_examples = {}
        for o in objections:
            if o['type'] not in obj_examples:
                obj_examples[o['type']] = []
            if len(obj_examples[o['type']]) < 3:
                obj_examples[o['type']].append(o['content'])

        objections_summary = [
            {"type": t, "count": c, "percentage": round((c / len(objections)) * 100, 1) if objections else 0, "examples": obj_examples.get(t, [])}
            for t, c in obj_types.most_common(5)
        ]

        # Funnel
        user_msg_counts = Counter(msg.follower_id for msg in messages)
        users_engaged = len([u for u, c in user_msg_counts.items() if c >= 2])
        users_interested = len([u for u, c in user_msg_counts.items() if c >= 3])

        leads_count = db.execute(text("""
            SELECT COUNT(*) FROM leads
            WHERE creator_id IN (SELECT id FROM creators WHERE name = :cid OR id::text = :cid)
            AND first_contact_at >= :s AND first_contact_at <= :e
        """), {"cid": creator_id, "s": start, "e": end}).scalar() or 0

        customers_count = db.execute(text("""
            SELECT COUNT(*) FROM leads
            WHERE creator_id IN (SELECT id FROM creators WHERE name = :cid OR id::text = :cid)
            AND status = 'cliente' AND last_contact_at >= :s AND last_contact_at <= :e
        """), {"cid": creator_id, "s": start, "e": end}).scalar() or 0

        funnel = [
            {"stage": "DMs Recibidos", "count": total_messages, "percentage": 100},
            {"stage": "Usuarios Unicos", "count": unique_users, "percentage": 100},
            {"stage": "Respondieron (2+ msgs)", "count": users_engaged, "percentage": round((users_engaged / unique_users) * 100, 1) if unique_users > 0 else 0},
            {"stage": "Interes Real (3+ msgs)", "count": users_interested, "percentage": round((users_interested / unique_users) * 100, 1) if unique_users > 0 else 0},
            {"stage": "Leads", "count": int(leads_count), "percentage": round((leads_count / unique_users) * 100, 1) if unique_users > 0 else 0},
            {"stage": "Clientes", "count": int(customers_count), "percentage": round((customers_count / unique_users) * 100, 1) if unique_users > 0 else 0},
        ]

        # Sentiment
        sent = db.query(func.avg(CreatorMetricsDaily.sentiment_score)).filter(
            CreatorMetricsDaily.creator_id == creator_name,
            CreatorMetricsDaily.date >= start.date(),
            CreatorMetricsDaily.date <= end.date()
        ).scalar() or 0

        db.rollback()

        return {
            "status": "ok",
            "period": period,
            "total_messages": total_messages,
            "unique_users": unique_users,
            "avg_messages_per_user": round(total_messages / unique_users, 1) if unique_users > 0 else 0,
            "sentiment": {"average": round(float(sent), 2), "label": "Positivo" if sent > 0.3 else "Neutral" if sent > -0.3 else "Negativo"},
            "intent_distribution": intent_distribution,
            "objections": objections_summary,
            "questions": {"total": len(questions), "samples": questions[:10]},
            "funnel": funnel
        }

    except Exception as e:
        logger.error(f"Error in audience analytics: {e}")
        db.rollback()
        return {"status": "error", "error": str(e), "total_messages": 0, "unique_users": 0, "intent_distribution": [], "objections": [], "funnel": []}


# ============================================================================
# SALES TAB (full analytics)
# ============================================================================

@router.get("/{creator_id}/sales")
async def get_sales_analytics(
    creator_id: str,
    period: str = Query("30d"),
    db: Session = Depends(get_db)
):
    """Sales analytics: revenue, products, trends."""
    start, end = get_date_range(period)
    prev_start, prev_end = get_previous_range(start, end)
    creator_name = get_creator_name(db, creator_id)

    try:
        sales_q = text("""
            SELECT COUNT(*), COALESCE(SUM(deal_value), 0) FROM leads
            WHERE creator_id IN (SELECT id FROM creators WHERE name = :cid OR id::text = :cid)
            AND status = 'cliente' AND last_contact_at >= :s AND last_contact_at <= :e
        """)
        result = db.execute(sales_q, {"cid": creator_id, "s": start, "e": end}).fetchone()
        total_sales = result[0] if result else 0
        total_revenue = float(result[1]) if result else 0

        prev_result = db.execute(sales_q, {"cid": creator_id, "s": prev_start, "e": prev_end}).fetchone()
        prev_sales = prev_result[0] if prev_result else 0
        prev_revenue = float(prev_result[1]) if prev_result else 0

        # Products
        products = db.query(Product).filter(
            Product.creator_id.in_(db.query(Creator.id).filter(or_(Creator.name == creator_id, Creator.id == creator_id)))
        ).all()

        product_analytics = []
        for p in products:
            mentions = db.query(func.count(ConversationEmbedding.id)).filter(
                ConversationEmbedding.creator_id == creator_name,
                ConversationEmbedding.created_at >= start,
                ConversationEmbedding.created_at <= end,
                ConversationEmbedding.content.ilike(f'%{p.name}%')
            ).scalar() or 0
            product_analytics.append({
                'id': str(p.id), 'name': p.name, 'price': p.price,
                'mentions': mentions, 'category': p.category, 'is_active': p.is_active
            })

        product_analytics.sort(key=lambda x: x['mentions'], reverse=True)

        # Revenue trend
        trend_q = text("""
            SELECT date, revenue, conversions FROM creator_metrics_daily
            WHERE creator_id = :cid AND date >= :s::date AND date <= :e::date ORDER BY date
        """)
        trend_results = db.execute(trend_q, {"cid": creator_name, "s": start, "e": end}).fetchall()
        revenue_trend = [{"date": r[0].isoformat(), "revenue": float(r[1] or 0), "conversions": int(r[2] or 0)} for r in trend_results]

        db.rollback()

        return {
            "status": "ok",
            "period": period,
            "summary": {
                "total_revenue": total_revenue,
                "previous_revenue": prev_revenue,
                "revenue_change": calc_change(total_revenue, prev_revenue),
                "total_sales": total_sales,
                "previous_sales": prev_sales,
                "sales_change": calc_change(total_sales, prev_sales),
                "avg_ticket": round(total_revenue / total_sales, 2) if total_sales > 0 else 0
            },
            "by_product": product_analytics,
            "revenue_trend": revenue_trend
        }

    except Exception as e:
        logger.error(f"Error in sales analytics: {e}")
        db.rollback()
        return {"status": "error", "error": str(e), "summary": {"total_revenue": 0, "total_sales": 0, "avg_ticket": 0}, "by_product": [], "revenue_trend": []}


# ============================================================================
# PREDICTIONS TAB
# ============================================================================

@router.get("/{creator_id}/predictions")
async def get_predictions(creator_id: str, db: Session = Depends(get_db)):
    """AI Predictions: hot leads, churn risks, recommendations."""
    try:
        from core.intelligence.engine import IntelligenceEngine
        engine = IntelligenceEngine(creator_id)

        hot_leads = await engine.predict_conversions(db)
        churn_risks = await engine.predict_churn_risk(db)
        revenue_forecast = await engine.forecast_revenue(db, weeks_ahead=4)
        content_recs = await engine.generate_content_recommendations(db)
        action_recs = await engine.generate_action_recommendations(db)
        product_recs = await engine.generate_product_recommendations(db)

        return {
            "status": "ok",
            "hot_leads": hot_leads[:10],
            "total_hot_leads": len(hot_leads),
            "churn_risks": churn_risks[:10],
            "total_at_risk": len(churn_risks),
            "revenue_forecast": revenue_forecast,
            "recommendations": {"content": content_recs[:5], "actions": action_recs[:5], "products": product_recs[:3]}
        }

    except Exception as e:
        logger.error(f"Error in predictions: {e}")
        db.rollback()
        return {"status": "error", "error": str(e), "hot_leads": [], "churn_risks": [], "revenue_forecast": {}, "recommendations": {}}


# ============================================================================
# REPORTS TAB
# ============================================================================

@router.get("/{creator_id}/reports")
async def get_reports(creator_id: str, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    """Get list of generated reports."""
    creator_name = get_creator_name(db, creator_id)
    try:
        reports = db.query(WeeklyReport).filter(WeeklyReport.creator_id == creator_name).order_by(WeeklyReport.week_end.desc()).limit(limit).all()
        return {
            "status": "ok",
            "count": len(reports),
            "reports": [{
                "id": r.id,
                "week_start": r.week_start.isoformat() if r.week_start else None,
                "week_end": r.week_end.isoformat() if r.week_end else None,
                "metrics_summary": r.metrics_summary,
                "executive_summary": r.executive_summary,
                "key_wins": r.key_wins,
                "areas_to_improve": r.areas_to_improve,
                "created_at": r.created_at.isoformat() if r.created_at else None
            } for r in reports]
        }
    except Exception as e:
        logger.error(f"Error getting reports: {e}")
        db.rollback()
        return {"status": "error", "error": str(e), "reports": []}


@router.post("/{creator_id}/reports/generate")
async def generate_report(creator_id: str, report_type: str = Query("weekly", regex="^(daily|weekly|monthly)$"), db: Session = Depends(get_db)):
    """Generate a new report on demand."""
    try:
        from core.intelligence.engine import IntelligenceEngine
        engine = IntelligenceEngine(creator_id)
        report = await engine.generate_weekly_report(db)
        return {"status": "ok", "report_type": report_type, "report": report}
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        db.rollback()
        return {"status": "error", "error": str(e)}


# ============================================================================
# TRENDS ENDPOINT
# ============================================================================

@router.get("/{creator_id}/trends")
async def get_trends(
    creator_id: str,
    metric: str = Query("revenue", regex="^(revenue|leads|dms|sentiment|conversions)$"),
    period: str = Query("30d"),
    db: Session = Depends(get_db)
):
    """Get time series data for charts."""
    start, end = get_date_range(period)
    creator_name = get_creator_name(db, creator_id)

    days = (end - start).days
    date_trunc = "day" if days <= 90 else "week"

    try:
        if metric == "revenue":
            q = text(f"SELECT DATE_TRUNC('{date_trunc}', date) as p, SUM(revenue) as v FROM creator_metrics_daily WHERE creator_id = :cid AND date >= :s::date AND date <= :e::date GROUP BY p ORDER BY p")
        elif metric == "leads":
            q = text(f"SELECT DATE_TRUNC('{date_trunc}', date) as p, SUM(new_leads) as v FROM creator_metrics_daily WHERE creator_id = :cid AND date >= :s::date AND date <= :e::date GROUP BY p ORDER BY p")
        elif metric == "dms":
            q = text(f"SELECT DATE_TRUNC('{date_trunc}', date) as p, SUM(total_messages) as v FROM creator_metrics_daily WHERE creator_id = :cid AND date >= :s::date AND date <= :e::date GROUP BY p ORDER BY p")
        elif metric == "sentiment":
            q = text(f"SELECT DATE_TRUNC('{date_trunc}', date) as p, AVG(sentiment_score) as v FROM creator_metrics_daily WHERE creator_id = :cid AND date >= :s::date AND date <= :e::date AND sentiment_score IS NOT NULL GROUP BY p ORDER BY p")
        else:  # conversions
            q = text(f"SELECT DATE_TRUNC('{date_trunc}', date) as p, SUM(conversions) as v FROM creator_metrics_daily WHERE creator_id = :cid AND date >= :s::date AND date <= :e::date GROUP BY p ORDER BY p")

        results = db.execute(q, {"cid": creator_name, "s": start, "e": end}).fetchall()
        data = [{"date": r[0].isoformat(), "value": round(float(r[1] or 0), 2) if metric == "sentiment" else float(r[1] or 0)} for r in results]

        db.rollback()
        return {"status": "ok", "metric": metric, "period": period, "group_by": date_trunc, "data": data}

    except Exception as e:
        logger.error(f"Error getting trends: {e}")
        db.rollback()
        return {"status": "error", "error": str(e), "data": []}
