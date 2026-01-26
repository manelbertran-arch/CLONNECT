"""
Intelligence Engine - Core analytics and prediction engine for Clonnect.

Analyzes patterns across all data sources and generates:
- Predictions (conversion probability, churn risk, revenue forecast)
- Recommendations (content ideas, actions, product suggestions)
- Insights (temporal patterns, conversation patterns, conversion patterns)
"""

import os
import logging
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from collections import Counter

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("clonnect.intelligence")

ENABLE_INTELLIGENCE = os.getenv("ENABLE_INTELLIGENCE", "true").lower() == "true"


class IntelligenceEngine:
    """
    Main intelligence engine for pattern analysis, predictions, and recommendations.

    Usage:
        engine = IntelligenceEngine(creator_id="manel")
        patterns = await engine.analyze_patterns(db, days=30)
        predictions = await engine.predict_conversions(db)
        recommendations = await engine.generate_content_recommendations(db)
    """

    def __init__(self, creator_id: str):
        self.creator_id = creator_id

    # =========================================
    # PATTERN ANALYSIS
    # =========================================

    async def analyze_patterns(self, db: Session, days: int = 30) -> Dict[str, Any]:
        """
        Analyze patterns across all data sources.

        Returns:
            Dict with temporal, conversation, content, and conversion patterns.
        """
        patterns = {}

        patterns['temporal'] = await self._analyze_temporal_patterns(db, days)
        patterns['conversation'] = await self._analyze_conversation_patterns(db, days)
        patterns['conversion'] = await self._analyze_conversion_patterns(db, days)

        return patterns

    async def _analyze_temporal_patterns(self, db: Session, days: int) -> Dict:
        """Analyze when activity/conversions peak."""
        try:
            # Best hour for receiving DMs
            hour_query = text("""
                SELECT
                    EXTRACT(HOUR FROM created_at) as hour,
                    COUNT(*) as messages,
                    COUNT(DISTINCT follower_id) as unique_users
                FROM conversation_embeddings
                WHERE creator_id = :creator_id
                AND created_at > NOW() - :days * INTERVAL '1 day'
                AND message_role = 'user'
                GROUP BY EXTRACT(HOUR FROM created_at)
                ORDER BY messages DESC
            """)

            hour_results = db.execute(hour_query, {
                "creator_id": self.creator_id,
                "days": days
            }).fetchall()

            # Best day of week
            day_query = text("""
                SELECT
                    EXTRACT(DOW FROM created_at) as day_of_week,
                    COUNT(*) as messages,
                    COUNT(DISTINCT follower_id) as unique_users
                FROM conversation_embeddings
                WHERE creator_id = :creator_id
                AND created_at > NOW() - :days * INTERVAL '1 day'
                GROUP BY EXTRACT(DOW FROM created_at)
                ORDER BY unique_users DESC
            """)

            day_results = db.execute(day_query, {
                "creator_id": self.creator_id,
                "days": days
            }).fetchall()

            day_names = ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']

            return {
                "best_hours": [
                    {"hour": int(r[0]), "messages": r[1], "users": r[2]}
                    for r in hour_results[:5]
                ] if hour_results else [],
                "best_days": [
                    {"day": day_names[int(r[0])], "messages": r[1], "users": r[2]}
                    for r in day_results[:3]
                ] if day_results else [],
                "peak_activity_hour": int(hour_results[0][0]) if hour_results else 12,
                "peak_activity_day": day_names[int(day_results[0][0])] if day_results else "Lunes"
            }
        except Exception as e:
            logger.error(f"Error analyzing temporal patterns: {e}")
            return {"error": str(e)}

    async def _analyze_conversation_patterns(self, db: Session, days: int) -> Dict:
        """Analyze conversation patterns."""
        try:
            # Intent distribution
            intent_query = text("""
                SELECT
                    COALESCE(msg_metadata->>'intent', 'unknown') as intent,
                    COUNT(*) as count
                FROM conversation_embeddings
                WHERE creator_id = :creator_id
                AND created_at > NOW() - :days * INTERVAL '1 day'
                AND message_role = 'user'
                GROUP BY COALESCE(msg_metadata->>'intent', 'unknown')
                ORDER BY count DESC
                LIMIT 10
            """)

            intent_results = db.execute(intent_query, {
                "creator_id": self.creator_id,
                "days": days
            }).fetchall()

            # Average messages per conversation
            conv_stats_query = text("""
                SELECT
                    AVG(msg_count) as avg_messages,
                    MAX(msg_count) as max_messages
                FROM (
                    SELECT follower_id, COUNT(*) as msg_count
                    FROM conversation_embeddings
                    WHERE creator_id = :creator_id
                    AND created_at > NOW() - :days * INTERVAL '1 day'
                    GROUP BY follower_id
                ) sub
            """)

            conv_stats = db.execute(conv_stats_query, {
                "creator_id": self.creator_id,
                "days": days
            }).fetchone()

            return {
                "intent_distribution": {r[0]: r[1] for r in intent_results} if intent_results else {},
                "avg_messages_per_user": round(conv_stats[0] or 0, 1) if conv_stats else 0,
                "max_messages_per_user": conv_stats[1] if conv_stats else 0
            }
        except Exception as e:
            logger.error(f"Error analyzing conversation patterns: {e}")
            return {"error": str(e)}

    async def _analyze_conversion_patterns(self, db: Session, days: int) -> Dict:
        """Analyze conversion patterns."""
        try:
            # Products mentioned - join with creators to match by name
            product_query = text("""
                SELECT
                    p.name,
                    COUNT(DISTINCT ce.follower_id) as mentions
                FROM products p
                JOIN creators c ON c.id = p.creator_id
                LEFT JOIN conversation_embeddings ce
                    ON LOWER(ce.content) LIKE '%' || LOWER(p.name) || '%'
                    AND ce.creator_id = c.name
                    AND ce.created_at > NOW() - :days * INTERVAL '1 day'
                WHERE c.name = :creator_id
                GROUP BY p.id, p.name
                HAVING COUNT(DISTINCT ce.follower_id) > 0
                ORDER BY mentions DESC
                LIMIT 5
            """)

            product_results = db.execute(product_query, {
                "creator_id": self.creator_id,
                "days": days
            }).fetchall()

            return {
                "top_products_mentioned": [
                    {"name": r[0], "mentions": r[1]}
                    for r in product_results
                ] if product_results else []
            }
        except Exception as e:
            logger.error(f"Error analyzing conversion patterns: {e}")
            return {"error": str(e)}

    # =========================================
    # PREDICTIONS
    # =========================================

    async def predict_conversions(self, db: Session) -> List[Dict]:
        """
        Predict which leads are most likely to convert.

        Uses a simple scoring model based on:
        - Message count (engagement)
        - Interest signals in messages
        - Recency of activity
        """
        try:
            leads_query = text("""
                SELECT
                    l.id,
                    l.platform_user_id as lead_id,
                    l.status,
                    l.score as current_score,
                    l.username,
                    COUNT(ce.id) as message_count,
                    MAX(ce.created_at) as last_activity
                FROM leads l
                LEFT JOIN conversation_embeddings ce
                    ON ce.follower_id = l.platform_user_id
                    AND ce.creator_id = :creator_id
                WHERE l.creator_id = :creator_id
                AND l.status NOT IN ('customer', 'lost')
                AND l.created_at > NOW() - INTERVAL '30 days'
                GROUP BY l.id, l.platform_user_id, l.status, l.score, l.username
                HAVING COUNT(ce.id) >= 2
                ORDER BY l.score DESC, COUNT(ce.id) DESC
                LIMIT 20
            """)

            leads = db.execute(leads_query, {"creator_id": self.creator_id}).fetchall()

            predictions = []
            now = datetime.now()

            for lead in leads:
                base_score = float(lead[3] or 0.3)
                message_count = lead[5] or 0
                last_activity = lead[6]

                # Calculate conversion probability
                engagement_boost = min(message_count / 20, 0.25)
                recency_boost = 0
                days_since_active = 30

                if last_activity:
                    days_since_active = (now - last_activity).days
                    if days_since_active < 3:
                        recency_boost = 0.15
                    elif days_since_active < 7:
                        recency_boost = 0.08

                conversion_prob = min(base_score + engagement_boost + recency_boost, 0.95)

                if conversion_prob > 0.4:
                    predictions.append({
                        "lead_id": lead[1],
                        "username": lead[4] or "Unknown",
                        "status": lead[2],
                        "conversion_probability": round(conversion_prob, 2),
                        "confidence": round(0.5 + min(message_count / 30, 0.4), 2),
                        "factors": {
                            "engagement_level": message_count,
                            "current_score": round(base_score, 2),
                            "days_since_last_activity": days_since_active
                        },
                        "recommended_action": self._get_recommended_action(
                            message_count, days_since_active, base_score
                        )
                    })

            return sorted(predictions, key=lambda x: x['conversion_probability'], reverse=True)

        except Exception as e:
            logger.error(f"Error predicting conversions: {e}")
            return []

    def _get_recommended_action(self, messages: int, days_inactive: int, score: float) -> str:
        """Determine best action for a lead."""
        if days_inactive > 7:
            return "Enviar mensaje de reactivacion"
        elif score > 0.7:
            return "Contactar con oferta directa"
        elif messages > 10:
            return "Proponer llamada de cierre"
        elif messages > 5:
            return "Enviar caso de exito"
        else:
            return "Enviar contenido de valor"

    async def predict_churn_risk(self, db: Session) -> List[Dict]:
        """Predict which leads are at risk of being lost."""
        try:
            query = text("""
                SELECT
                    l.platform_user_id as lead_id,
                    l.username,
                    l.status,
                    l.score,
                    MAX(ce.created_at) as last_activity,
                    COUNT(ce.id) as total_messages
                FROM leads l
                LEFT JOIN conversation_embeddings ce
                    ON ce.follower_id = l.platform_user_id
                    AND ce.creator_id = :creator_id
                WHERE l.creator_id = :creator_id
                AND l.status NOT IN ('customer', 'lost')
                GROUP BY l.id, l.platform_user_id, l.username, l.status, l.score
                HAVING MAX(ce.created_at) < NOW() - INTERVAL '5 days'
                   OR MAX(ce.created_at) IS NULL
                ORDER BY last_activity ASC NULLS FIRST
                LIMIT 10
            """)

            leads = db.execute(query, {"creator_id": self.creator_id}).fetchall()

            churn_risks = []
            now = datetime.now()

            for lead in leads:
                last_activity = lead[4]
                days_inactive = 30

                if last_activity:
                    days_inactive = (now - last_activity).days

                churn_risk = min(0.3 + (days_inactive / 20) * 0.5, 0.95)

                churn_risks.append({
                    "lead_id": lead[0],
                    "username": lead[1] or "Unknown",
                    "status": lead[2],
                    "churn_risk": round(churn_risk, 2),
                    "days_inactive": days_inactive,
                    "recovery_action": "Oferta especial" if days_inactive > 10 else "Seguimiento personalizado"
                })

            return churn_risks

        except Exception as e:
            logger.error(f"Error predicting churn: {e}")
            return []

    async def forecast_revenue(self, db: Session, weeks_ahead: int = 4) -> Dict:
        """Forecast revenue for upcoming weeks."""
        try:
            history_query = text("""
                SELECT
                    DATE_TRUNC('week', date) as week,
                    SUM(revenue) as weekly_revenue,
                    SUM(conversions) as weekly_conversions
                FROM creator_metrics_daily
                WHERE creator_id = :creator_id
                AND date > NOW() - INTERVAL '12 weeks'
                GROUP BY DATE_TRUNC('week', date)
                ORDER BY week DESC
            """)

            history = db.execute(history_query, {"creator_id": self.creator_id}).fetchall()

            if len(history) < 2:
                return {
                    "error": "Insufficient historical data",
                    "current_weekly_avg": 0,
                    "forecasts": []
                }

            revenues = [float(h[1] or 0) for h in history]
            recent_avg = sum(revenues[:4]) / min(len(revenues), 4)
            older_avg = sum(revenues[4:8]) / max(len(revenues[4:8]), 1) if len(revenues) > 4 else recent_avg

            growth_rate = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0

            forecasts = []
            for i in range(1, weeks_ahead + 1):
                projected = recent_avg * (1 + growth_rate * i * 0.3)
                forecasts.append({
                    "week": i,
                    "projected_revenue": round(max(projected, 0), 2),
                    "confidence": round(max(0.9 - (i * 0.15), 0.4), 2)
                })

            return {
                "current_weekly_avg": round(recent_avg, 2),
                "growth_trend": round(growth_rate * 100, 1),
                "forecasts": forecasts
            }

        except Exception as e:
            logger.error(f"Error forecasting revenue: {e}")
            return {"error": str(e), "forecasts": []}

    # =========================================
    # RECOMMENDATIONS
    # =========================================

    async def generate_content_recommendations(self, db: Session) -> List[Dict]:
        """Generate content recommendations based on conversation analysis."""
        recommendations = []

        try:
            # Find frequently asked topics
            topics_query = text("""
                SELECT
                    LEFT(content, 150) as sample,
                    COUNT(*) as mentions
                FROM conversation_embeddings
                WHERE creator_id = :creator_id
                AND created_at > NOW() - INTERVAL '14 days'
                AND message_role = 'user'
                AND LENGTH(content) > 30
                GROUP BY LEFT(content, 150)
                HAVING COUNT(*) >= 2
                ORDER BY mentions DESC
                LIMIT 5
            """)

            topics = db.execute(topics_query, {"creator_id": self.creator_id}).fetchall()

            if topics:
                recommendations.append({
                    "category": "content",
                    "priority": "high",
                    "title": "Crear contenido sobre temas frecuentes",
                    "description": f"{len(topics)} temas se repiten en conversaciones recientes",
                    "reasoning": f"Ejemplo: '{topics[0][0][:80]}...' ({topics[0][1]} veces)",
                    "action_data": {
                        "topic_examples": [t[0][:100] for t in topics[:3]],
                        "suggested_format": "carrusel"
                    },
                    "expected_impact": {
                        "estimated_engagement": "Alto",
                        "addresses_questions": sum(t[1] for t in topics)
                    }
                })

            # Best posting time
            temporal = await self._analyze_temporal_patterns(db, 14)
            if temporal.get('best_hours'):
                best_hour = temporal['best_hours'][0]
                recommendations.append({
                    "category": "timing",
                    "priority": "medium",
                    "title": f"Publica a las {best_hour['hour']}:00",
                    "description": "Tu audiencia esta mas activa a esta hora",
                    "reasoning": f"{best_hour['users']} usuarios unicos activos",
                    "action_data": {
                        "best_hour": best_hour['hour'],
                        "best_day": temporal.get('peak_activity_day', 'Lunes')
                    },
                    "expected_impact": {
                        "engagement_boost": "15-25%"
                    }
                })

        except Exception as e:
            logger.error(f"Error generating content recommendations: {e}")

        return recommendations

    async def generate_action_recommendations(self, db: Session) -> List[Dict]:
        """Generate action recommendations for immediate follow-up."""
        recommendations = []

        try:
            # Hot leads to contact
            hot_leads = await self.predict_conversions(db)
            if hot_leads:
                top_leads = [l for l in hot_leads if l['conversion_probability'] > 0.6][:5]
                if top_leads:
                    recommendations.append({
                        "category": "action",
                        "priority": "high",
                        "title": f"Contacta {len(top_leads)} leads calientes hoy",
                        "description": "Estos leads tienen alta probabilidad de conversion",
                        "reasoning": f"Probabilidad promedio: {sum(l['conversion_probability'] for l in top_leads) / len(top_leads) * 100:.0f}%",
                        "action_data": {
                            "leads": [
                                {"id": l['lead_id'], "prob": l['conversion_probability'], "action": l['recommended_action']}
                                for l in top_leads
                            ]
                        },
                        "expected_impact": {
                            "potential_conversions": len([l for l in top_leads if l['conversion_probability'] > 0.7])
                        }
                    })

            # Churn risk leads
            churn_risks = await self.predict_churn_risk(db)
            if churn_risks:
                recommendations.append({
                    "category": "action",
                    "priority": "medium" if len(churn_risks) < 5 else "high",
                    "title": f"Recupera {len(churn_risks)} leads en riesgo",
                    "description": "Estos leads pueden perderse sin accion",
                    "reasoning": f"Promedio dias inactivos: {sum(l['days_inactive'] for l in churn_risks) / len(churn_risks):.0f}",
                    "action_data": {
                        "leads": churn_risks[:5]
                    },
                    "expected_impact": {
                        "leads_recovered": round(len(churn_risks) * 0.3)
                    }
                })

        except Exception as e:
            logger.error(f"Error generating action recommendations: {e}")

        return recommendations

    async def generate_product_recommendations(self, db: Session) -> List[Dict]:
        """Generate product-related recommendations."""
        recommendations = []

        try:
            # Detect unmet demand
            demand_query = text("""
                SELECT content, COUNT(*) as mentions
                FROM conversation_embeddings
                WHERE creator_id = :creator_id
                AND created_at > NOW() - INTERVAL '30 days'
                AND message_role = 'user'
                AND (
                    LOWER(content) LIKE '%tienes algo%'
                    OR LOWER(content) LIKE '%ofreces%'
                    OR LOWER(content) LIKE '%hay algun%'
                    OR LOWER(content) LIKE '%me gustaria%'
                )
                GROUP BY content
                HAVING COUNT(*) >= 2
                ORDER BY mentions DESC
                LIMIT 5
            """)

            demands = db.execute(demand_query, {"creator_id": self.creator_id}).fetchall()

            if demands:
                recommendations.append({
                    "category": "product",
                    "priority": "high",
                    "title": "Oportunidad de nuevo producto",
                    "description": "Tu audiencia pide algo que aun no ofreces",
                    "reasoning": f"Ejemplo: '{demands[0][0][:80]}...'",
                    "action_data": {
                        "demand_examples": [d[0][:100] for d in demands[:3]],
                        "total_requests": sum(d[1] for d in demands)
                    },
                    "expected_impact": {
                        "potential_customers": sum(d[1] for d in demands)
                    }
                })

        except Exception as e:
            logger.error(f"Error generating product recommendations: {e}")

        return recommendations

    # =========================================
    # WEEKLY REPORT
    # =========================================

    async def generate_weekly_report(self, db: Session, week_end: date = None) -> Dict:
        """Generate comprehensive weekly report with predictions and recommendations."""
        if week_end is None:
            today = date.today()
            week_end = today - timedelta(days=today.weekday() + 1)

        week_start = week_end - timedelta(days=6)

        logger.info(f"Generating weekly report for {self.creator_id}: {week_start} to {week_end}")

        # Gather all data
        metrics = await self._get_weekly_metrics(db, week_start, week_end)
        patterns = await self.analyze_patterns(db, 30)
        conversion_predictions = await self.predict_conversions(db)
        churn_risks = await self.predict_churn_risk(db)
        revenue_forecast = await self.forecast_revenue(db, 4)

        content_recs = await self.generate_content_recommendations(db)
        action_recs = await self.generate_action_recommendations(db)
        product_recs = await self.generate_product_recommendations(db)

        vs_previous = await self._get_comparison(db, week_start, 7)

        # Generate LLM summary
        llm_summary = await self._generate_llm_summary({
            "period": f"{week_start} a {week_end}",
            "metrics": metrics,
            "predictions": {
                "hot_leads": len(conversion_predictions),
                "at_risk": len(churn_risks),
                "revenue_trend": revenue_forecast.get('growth_trend', 0)
            },
            "vs_previous_week": vs_previous
        })

        return {
            "period": {"start": str(week_start), "end": str(week_end)},
            "metrics_summary": metrics,
            "vs_previous_week": vs_previous,
            "patterns": patterns,
            "predictions": {
                "hot_leads": conversion_predictions[:10],
                "churn_risks": churn_risks[:10],
                "revenue_forecast": revenue_forecast
            },
            "recommendations": {
                "content": content_recs,
                "actions": action_recs,
                "products": product_recs
            },
            "executive_summary": llm_summary.get("executive_summary", ""),
            "key_wins": llm_summary.get("key_wins", []),
            "areas_to_improve": llm_summary.get("areas_to_improve", []),
            "this_week_focus": llm_summary.get("this_week_focus", [])
        }

    async def _get_weekly_metrics(self, db: Session, start: date, end: date) -> Dict:
        """Get aggregated metrics for a week."""
        try:
            query = text("""
                SELECT
                    COALESCE(SUM(total_conversations), 0),
                    COALESCE(SUM(total_messages), 0),
                    COALESCE(SUM(new_leads), 0),
                    COALESCE(SUM(conversions), 0),
                    COALESCE(SUM(revenue), 0)
                FROM creator_metrics_daily
                WHERE creator_id = :creator_id
                AND date >= :start AND date <= :end
            """)

            result = db.execute(query, {
                "creator_id": self.creator_id,
                "start": start,
                "end": end
            }).fetchone()

            if result:
                conversion_rate = 0
                if result[2] > 0:
                    conversion_rate = round(result[3] / result[2] * 100, 1)

                return {
                    "conversations": result[0],
                    "messages": result[1],
                    "new_leads": result[2],
                    "conversions": result[3],
                    "revenue": float(result[4]),
                    "conversion_rate": conversion_rate
                }

            return {
                "conversations": 0, "messages": 0, "new_leads": 0,
                "conversions": 0, "revenue": 0, "conversion_rate": 0
            }

        except Exception as e:
            logger.error(f"Error getting weekly metrics: {e}")
            return {}

    async def _get_comparison(self, db: Session, current_start: date, days_back: int) -> Dict:
        """Compare current period with previous period."""
        previous_start = current_start - timedelta(days=days_back)
        previous_end = current_start - timedelta(days=1)
        current_end = current_start + timedelta(days=6)

        current = await self._get_weekly_metrics(db, current_start, current_end)
        previous = await self._get_weekly_metrics(db, previous_start, previous_end)

        def calc_change(curr, prev):
            if prev == 0:
                return 100 if curr > 0 else 0
            return round((curr - prev) / prev * 100, 1)

        return {
            "conversations": calc_change(current.get("conversations", 0), previous.get("conversations", 0)),
            "leads": calc_change(current.get("new_leads", 0), previous.get("new_leads", 0)),
            "conversions": calc_change(current.get("conversions", 0), previous.get("conversions", 0)),
            "revenue": calc_change(current.get("revenue", 0), previous.get("revenue", 0))
        }

    async def _generate_llm_summary(self, data: Dict) -> Dict:
        """Generate executive summary using LLM."""
        try:
            from core.llm import get_llm_client

            prompt = f"""Eres un consultor de negocios para un creador de contenido digital.
Genera un informe BREVE y ACCIONABLE.

PERIODO: {data['period']}
METRICAS: {json.dumps(data['metrics'], ensure_ascii=False)}
VS SEMANA ANTERIOR: {json.dumps(data['vs_previous_week'], ensure_ascii=False)}
PREDICCIONES: {data['predictions']['hot_leads']} leads calientes, {data['predictions']['at_risk']} en riesgo

Responde en JSON valido:
{{
    "executive_summary": "Resumen de 2-3 frases. Que paso, que significa, que hacer.",
    "key_wins": ["Victoria 1", "Victoria 2"],
    "areas_to_improve": ["Area 1"],
    "this_week_focus": ["Prioridad 1", "Prioridad 2"]
}}"""

            client = get_llm_client()
            response = await client.chat([
                {"role": "system", "content": "Responde SOLO en JSON valido."},
                {"role": "user", "content": prompt}
            ], max_tokens=800)

            # Parse JSON from response
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            return json.loads(response)

        except Exception as e:
            logger.error(f"LLM summary failed: {e}")
            return {
                "executive_summary": "No se pudo generar resumen automatico.",
                "key_wins": [],
                "areas_to_improve": [],
                "this_week_focus": []
            }


# Factory function
def get_intelligence_engine(creator_id: str) -> IntelligenceEngine:
    """Get an IntelligenceEngine instance for a creator."""
    return IntelligenceEngine(creator_id)
