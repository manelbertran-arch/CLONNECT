#!/usr/bin/env python3
"""
Jobs programados para el sistema de inteligencia.

Cron sugerido (añadir a Railway o sistema de cron):
- Daily aggregation: 0 2 * * * python scripts/intelligence_jobs.py daily
- Weekly report: 0 9 * * 1 python scripts/intelligence_jobs.py weekly
- Predictions update: 0 6 * * * python scripts/intelligence_jobs.py predictions

Uso manual:
    python scripts/intelligence_jobs.py daily
    python scripts/intelligence_jobs.py weekly
    python scripts/intelligence_jobs.py weekly --creator creator_123
    python scripts/intelligence_jobs.py predictions
"""
import asyncio
import argparse
import logging
import sys
import os

# Añadir path del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("intelligence_jobs")


def get_db_session():
    """Get database session."""
    try:
        from api.database import get_db_session as _get_session
        return _get_session()
    except ImportError:
        from api.database import SessionLocal
        return SessionLocal()


async def get_active_creators(db) -> list:
    """Obtiene creadores con actividad reciente."""
    try:
        query = text("""
            SELECT DISTINCT creator_id
            FROM conversation_embeddings
            WHERE created_at > NOW() - INTERVAL '7 days'
        """)
        results = db.execute(query).fetchall()
        return [r[0] for r in results]
    except Exception as e:
        logger.warning(f"Could not get active creators from embeddings: {e}")
        # Fallback to leads table
        try:
            query = text("""
                SELECT DISTINCT c.name
                FROM creators c
                JOIN leads l ON l.creator_id = c.id
                WHERE l.created_at > NOW() - INTERVAL '7 days'
            """)
            results = db.execute(query).fetchall()
            return [r[0] for r in results]
        except Exception:
            return []


async def run_daily_aggregation(creator_id: str = None):
    """
    Ejecuta agregación diaria de métricas.
    Se ejecuta a las 2am para procesar el día anterior.
    """
    logger.info("Starting daily aggregation...")
    db = get_db_session()

    try:
        from core.intelligence.engine import IntelligenceEngine

        if creator_id:
            creators = [creator_id]
        else:
            creators = await get_active_creators(db)

        if not creators:
            logger.info("No active creators found")
            return

        logger.info(f"Processing {len(creators)} creators")

        for cid in creators:
            try:
                engine = IntelligenceEngine(cid)
                patterns = await engine.analyze_patterns(db, days=1)
                logger.info(f"✅ {cid}: Daily aggregation complete - {patterns.get('temporal', {}).get('best_hours', [])[:1]}")
            except Exception as e:
                logger.error(f"❌ {cid}: {e}")

    finally:
        db.close()

    logger.info("Daily aggregation finished")


async def run_weekly_report(creator_id: str = None):
    """
    Genera informes semanales.
    Se ejecuta los lunes a las 9am.
    """
    logger.info("Starting weekly report generation...")
    db = get_db_session()

    try:
        from core.intelligence.engine import IntelligenceEngine
        import json

        if creator_id:
            creators = [creator_id]
        else:
            creators = await get_active_creators(db)

        if not creators:
            logger.info("No active creators found")
            return

        logger.info(f"Generating reports for {len(creators)} creators")

        for cid in creators:
            try:
                engine = IntelligenceEngine(cid)
                report = await engine.generate_weekly_report(db)

                # Guardar en BD
                try:
                    insert_query = text("""
                        INSERT INTO weekly_reports (
                            creator_id, week_start, week_end,
                            metrics_summary, vs_previous_week,
                            conversion_predictions, churn_risks,
                            content_recommendations, action_recommendations,
                            executive_summary, key_wins, areas_to_improve, this_week_focus
                        ) VALUES (
                            :creator_id, :week_start, :week_end,
                            :metrics_summary, :vs_previous_week,
                            :conversion_predictions, :churn_risks,
                            :content_recommendations, :action_recommendations,
                            :executive_summary, :key_wins, :areas_to_improve, :this_week_focus
                        )
                        ON CONFLICT (creator_id, week_start) DO UPDATE SET
                            metrics_summary = EXCLUDED.metrics_summary,
                            vs_previous_week = EXCLUDED.vs_previous_week,
                            conversion_predictions = EXCLUDED.conversion_predictions,
                            churn_risks = EXCLUDED.churn_risks,
                            content_recommendations = EXCLUDED.content_recommendations,
                            action_recommendations = EXCLUDED.action_recommendations,
                            executive_summary = EXCLUDED.executive_summary,
                            key_wins = EXCLUDED.key_wins,
                            areas_to_improve = EXCLUDED.areas_to_improve,
                            this_week_focus = EXCLUDED.this_week_focus
                    """)

                    db.execute(insert_query, {
                        "creator_id": cid,
                        "week_start": report['period']['start'],
                        "week_end": report['period']['end'],
                        "metrics_summary": json.dumps(report.get('metrics_summary', {})),
                        "vs_previous_week": json.dumps(report.get('vs_previous_week', {})),
                        "conversion_predictions": json.dumps(report.get('predictions', {}).get('hot_leads', [])),
                        "churn_risks": json.dumps(report.get('predictions', {}).get('churn_risks', [])),
                        "content_recommendations": json.dumps(report.get('recommendations', {}).get('content', [])),
                        "action_recommendations": json.dumps(report.get('recommendations', {}).get('actions', [])),
                        "executive_summary": report.get('executive_summary', ''),
                        "key_wins": json.dumps(report.get('key_wins', [])),
                        "areas_to_improve": json.dumps(report.get('areas_to_improve', [])),
                        "this_week_focus": json.dumps(report.get('this_week_focus', []))
                    })
                    db.commit()
                    logger.info(f"✅ {cid}: Weekly report generated and saved")
                except Exception as db_err:
                    logger.warning(f"Could not save report to DB: {db_err}")
                    db.rollback()
                    logger.info(f"✅ {cid}: Weekly report generated (not saved)")

            except Exception as e:
                logger.error(f"❌ {cid}: {e}")
                db.rollback()

    finally:
        db.close()

    logger.info("Weekly report generation finished")


async def run_predictions_update(creator_id: str = None):
    """
    Actualiza predicciones de conversión y churn.
    Se puede ejecutar diariamente o bajo demanda.
    """
    logger.info("Starting predictions update...")
    db = get_db_session()

    try:
        from core.intelligence.engine import IntelligenceEngine

        if creator_id:
            creators = [creator_id]
        else:
            creators = await get_active_creators(db)

        if not creators:
            logger.info("No active creators found")
            return

        for cid in creators:
            try:
                engine = IntelligenceEngine(cid)

                # Predicciones de conversión
                conversions = await engine.predict_conversions(db)

                # Predicciones de churn
                churn = await engine.predict_churn_risk(db)

                logger.info(f"✅ {cid}: {len(conversions)} hot leads, {len(churn)} at risk")

            except Exception as e:
                logger.error(f"❌ {cid}: {e}")

    finally:
        db.close()

    logger.info("Predictions update finished")


def main():
    parser = argparse.ArgumentParser(description="Intelligence system jobs")
    parser.add_argument(
        "job",
        choices=["daily", "weekly", "predictions"],
        help="Job to run"
    )
    parser.add_argument(
        "--creator",
        help="Specific creator ID (optional, runs for all if not specified)"
    )

    args = parser.parse_args()

    if args.job == "daily":
        asyncio.run(run_daily_aggregation(args.creator))
    elif args.job == "weekly":
        asyncio.run(run_weekly_report(args.creator))
    elif args.job == "predictions":
        asyncio.run(run_predictions_update(args.creator))


if __name__ == "__main__":
    main()
