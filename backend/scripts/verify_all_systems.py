#!/usr/bin/env python3
"""
verify_all_systems.py - Test Masivo de Integración Clonnect

Verifica que TODOS los sistemas funcionan con data REAL de producción.
Genera un reporte detallado de qué funciona y qué no.

Usage:
    cd backend
    DATABASE_URL="postgresql://..." python -m scripts.verify_all_systems
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy import text

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class TestResult:
    """Result of a single test."""
    category: str
    test_name: str
    passed: bool
    expected: str
    actual: str
    details: str = ""


class SystemVerifier:
    """Verifier for all Clonnect systems."""

    def __init__(self, database_url: str, creator_id: str):
        self.database_url = database_url
        self.creator_id = creator_id
        self.engine = sa.create_engine(database_url)
        self.results: List[TestResult] = []

    def log(self, msg: str):
        """Print timestamped log."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def add_result(self, category: str, test_name: str, passed: bool,
                   expected: str, actual: str, details: str = ""):
        """Add a test result."""
        self.results.append(TestResult(
            category=category,
            test_name=test_name,
            passed=passed,
            expected=expected,
            actual=actual,
            details=details
        ))
        status = "✅ PASS" if passed else "❌ FAIL"
        self.log(f"{status} [{category}] {test_name}")

    # =========================================================================
    # CATEGORY 1: DATABASE TABLES - Row Counts
    # =========================================================================

    def verify_tables(self):
        """Verify all expected tables exist and have data."""
        self.log("\n" + "=" * 60)
        self.log("CATEGORÍA 1: TABLAS DE BASE DE DATOS")
        self.log("=" * 60)

        tables = [
            ("messages", 1000, "Mensajes de conversación"),
            ("leads", 100, "Leads del CRM"),
            ("relationship_dna", 50, "DNA de relaciones"),
            ("follower_memories", 100, "Memorias de seguidores"),
            ("conversation_states", 50, "Estados de conversación"),
            ("products", 1, "Productos del creador"),
            ("knowledge_base", 1, "Base de conocimiento"),
            ("calendar_bookings", 1, "Reservas de calendario"),
        ]

        with self.engine.connect() as conn:
            for table_name, min_expected, description in tables:
                try:
                    result = conn.execute(text(f"""
                        SELECT COUNT(*) FROM {table_name}
                        WHERE creator_id = :creator_id OR creator_id::text = :creator_id
                    """), {"creator_id": self.creator_id})
                    count = result.scalar() or 0
                except Exception:
                    # Try without creator_id filter
                    try:
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        count = result.scalar() or 0
                    except Exception as e:
                        self.add_result(
                            "1_TABLES", f"table_{table_name}",
                            False, f">= {min_expected}", f"ERROR: {e}",
                            description
                        )
                        continue

                passed = count >= min_expected
                self.add_result(
                    "1_TABLES", f"table_{table_name}",
                    passed, f">= {min_expected}", str(count),
                    description
                )

    # =========================================================================
    # CATEGORY 2: FOLLOWER MEMORY
    # =========================================================================

    def verify_follower_memory(self):
        """Verify follower memory data quality."""
        self.log("\n" + "=" * 60)
        self.log("CATEGORÍA 2: FOLLOWER MEMORY")
        self.log("=" * 60)

        with self.engine.connect() as conn:
            # Check for memories with data
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN total_messages > 0 THEN 1 END) as with_messages,
                    COUNT(CASE WHEN interests::text != '[]' THEN 1 END) as with_interests,
                    COUNT(CASE WHEN products_discussed::text != '[]' THEN 1 END) as with_products,
                    COUNT(CASE WHEN purchase_intent_score > 0 THEN 1 END) as with_intent,
                    AVG(total_messages) as avg_messages
                FROM follower_memories
                WHERE creator_id = :creator_id
            """), {"creator_id": self.creator_id})
            row = result.fetchone()

            if row:
                total, with_messages, with_interests, with_products, with_intent, avg_messages = row

                self.add_result(
                    "2_MEMORY", "memories_with_message_count",
                    with_messages > 0, "> 0", str(with_messages),
                    "Memorias con total_messages poblado"
                )

                self.add_result(
                    "2_MEMORY", "memories_with_interests",
                    with_interests > 0, "> 0", str(with_interests),
                    "Memorias con interests poblados"
                )

                self.add_result(
                    "2_MEMORY", "memories_with_products_discussed",
                    with_products > 0, "> 0", str(with_products),
                    "Memorias con products_discussed"
                )

                self.add_result(
                    "2_MEMORY", "memories_with_intent_score",
                    with_intent > 0, "> 0", str(with_intent),
                    "Memorias con purchase_intent_score > 0"
                )

    # =========================================================================
    # CATEGORY 3: RELATIONSHIP DNA
    # =========================================================================

    def verify_relationship_dna(self):
        """Verify RelationshipDNA data quality."""
        self.log("\n" + "=" * 60)
        self.log("CATEGORÍA 3: RELATIONSHIP DNA")
        self.log("=" * 60)

        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN relationship_type != 'DESCONOCIDO' THEN 1 END) as classified,
                    COUNT(CASE WHEN trust_score > 0 THEN 1 END) as with_trust,
                    COUNT(CASE WHEN vocabulary_uses::text != '[]' THEN 1 END) as with_vocab,
                    COUNT(CASE WHEN bot_instructions IS NOT NULL AND bot_instructions != '' THEN 1 END) as with_instructions,
                    COUNT(CASE WHEN golden_examples::text != '[]' THEN 1 END) as with_examples
                FROM relationship_dna
                WHERE creator_id = :creator_id
            """), {"creator_id": self.creator_id})
            row = result.fetchone()

            if row:
                total, classified, with_trust, with_vocab, with_instructions, with_examples = row

                self.add_result(
                    "3_DNA", "dna_total",
                    total > 0, "> 0", str(total),
                    "Total RelationshipDNA entries"
                )

                self.add_result(
                    "3_DNA", "dna_classified",
                    classified > 0, "> 0", str(classified),
                    "DNA con relationship_type != DESCONOCIDO"
                )

                self.add_result(
                    "3_DNA", "dna_with_trust_score",
                    with_trust > 0, "> 0", str(with_trust),
                    "DNA con trust_score > 0"
                )

                self.add_result(
                    "3_DNA", "dna_with_vocabulary",
                    with_vocab > 0, "> 0", str(with_vocab),
                    "DNA con vocabulary_uses poblado"
                )

                self.add_result(
                    "3_DNA", "dna_with_bot_instructions",
                    with_instructions > 0, "> 0", str(with_instructions),
                    "DNA con bot_instructions generadas"
                )

                # Check relationship type distribution
                result2 = conn.execute(text("""
                    SELECT relationship_type, COUNT(*) as cnt
                    FROM relationship_dna
                    WHERE creator_id = :creator_id
                    GROUP BY relationship_type
                    ORDER BY cnt DESC
                """), {"creator_id": self.creator_id})

                types = {row[0]: row[1] for row in result2}
                self.log(f"   Distribución: {types}")

    # =========================================================================
    # CATEGORY 4: LEADS AND CRM
    # =========================================================================

    def verify_leads(self):
        """Verify leads data quality."""
        self.log("\n" + "=" * 60)
        self.log("CATEGORÍA 4: LEADS Y CRM")
        self.log("=" * 60)

        with self.engine.connect() as conn:
            # Lead status distribution
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'nuevo' THEN 1 END) as nuevo,
                    COUNT(CASE WHEN status = 'interesado' THEN 1 END) as interesado,
                    COUNT(CASE WHEN status = 'caliente' THEN 1 END) as caliente,
                    COUNT(CASE WHEN status = 'cliente' THEN 1 END) as cliente,
                    COUNT(CASE WHEN status = 'fantasma' THEN 1 END) as fantasma,
                    COUNT(CASE WHEN purchase_intent > 0.5 THEN 1 END) as high_intent,
                    COUNT(CASE WHEN score > 50 THEN 1 END) as high_score
                FROM leads
                WHERE creator_id = :creator_id
            """), {"creator_id": self.creator_id})
            row = result.fetchone()

            if row:
                total, nuevo, interesado, caliente, cliente, fantasma, high_intent, high_score = row

                self.add_result(
                    "4_LEADS", "leads_total",
                    total > 0, "> 0", str(total),
                    "Total leads"
                )

                # Verify funnel distribution
                has_progression = (interesado > 0 or caliente > 0 or cliente > 0)
                self.add_result(
                    "4_LEADS", "leads_funnel_progression",
                    has_progression, "Leads en múltiples etapas",
                    f"nuevo={nuevo}, interesado={interesado}, caliente={caliente}, cliente={cliente}",
                    "Leads progresan por el funnel"
                )

                self.add_result(
                    "4_LEADS", "leads_with_high_intent",
                    high_intent > 0, "> 0", str(high_intent),
                    "Leads con purchase_intent > 0.5"
                )

                self.add_result(
                    "4_LEADS", "leads_with_high_score",
                    high_score > 0, "> 0", str(high_score),
                    "Leads con score > 50"
                )

    # =========================================================================
    # CATEGORY 5: MESSAGES
    # =========================================================================

    def verify_messages(self):
        """Verify messages data quality."""
        self.log("\n" + "=" * 60)
        self.log("CATEGORÍA 5: MENSAJES")
        self.log("=" * 60)

        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN role = 'user' THEN 1 END) as user_msgs,
                    COUNT(CASE WHEN role = 'assistant' THEN 1 END) as assistant_msgs,
                    COUNT(CASE WHEN intent IS NOT NULL THEN 1 END) as with_intent,
                    COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
                    COUNT(CASE WHEN approved_by = 'creator' THEN 1 END) as approved_by_creator,
                    COUNT(CASE WHEN approved_by = 'auto' THEN 1 END) as auto_approved
                FROM messages m
                JOIN leads l ON m.lead_id = l.id
                WHERE l.creator_id = :creator_id
            """), {"creator_id": self.creator_id})
            row = result.fetchone()

            if row:
                total, user_msgs, assistant_msgs, with_intent, sent, by_creator, auto = row

                self.add_result(
                    "5_MESSAGES", "messages_total",
                    total > 1000, "> 1000", str(total),
                    "Total mensajes"
                )

                self.add_result(
                    "5_MESSAGES", "messages_bidirectional",
                    user_msgs > 0 and assistant_msgs > 0,
                    "user > 0 AND assistant > 0",
                    f"user={user_msgs}, assistant={assistant_msgs}",
                    "Hay mensajes de ambos roles"
                )

                self.add_result(
                    "5_MESSAGES", "messages_with_intent",
                    with_intent > 0, "> 0", str(with_intent),
                    "Mensajes con intent clasificado"
                )

                # Intent distribution
                result2 = conn.execute(text("""
                    SELECT intent, COUNT(*) as cnt
                    FROM messages m
                    JOIN leads l ON m.lead_id = l.id
                    WHERE l.creator_id = :creator_id AND intent IS NOT NULL
                    GROUP BY intent
                    ORDER BY cnt DESC
                    LIMIT 10
                """), {"creator_id": self.creator_id})

                intents = {row[0]: row[1] for row in result2}
                self.log(f"   Top intents: {intents}")

    # =========================================================================
    # CATEGORY 6: PRODUCTS
    # =========================================================================

    def verify_products(self):
        """Verify products data quality."""
        self.log("\n" + "=" * 60)
        self.log("CATEGORÍA 6: PRODUCTOS")
        self.log("=" * 60)

        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN is_active = true THEN 1 END) as active,
                    COUNT(CASE WHEN price IS NOT NULL AND price > 0 THEN 1 END) as with_price,
                    COUNT(CASE WHEN payment_link IS NOT NULL AND payment_link != '' THEN 1 END) as with_link,
                    COUNT(CASE WHEN price_verified = true THEN 1 END) as verified
                FROM products
                WHERE creator_id = :creator_id
            """), {"creator_id": self.creator_id})
            row = result.fetchone()

            if row:
                total, active, with_price, with_link, verified = row

                self.add_result(
                    "6_PRODUCTS", "products_total",
                    total > 0, "> 0", str(total),
                    "Total productos"
                )

                self.add_result(
                    "6_PRODUCTS", "products_active",
                    active > 0, "> 0", str(active),
                    "Productos activos"
                )

                self.add_result(
                    "6_PRODUCTS", "products_with_price",
                    with_price > 0, "> 0", str(with_price),
                    "Productos con precio"
                )

                self.add_result(
                    "6_PRODUCTS", "products_with_payment_link",
                    with_link > 0, "> 0", str(with_link),
                    "Productos con link de pago"
                )

                # List products
                result2 = conn.execute(text("""
                    SELECT name, price, is_active
                    FROM products
                    WHERE creator_id = :creator_id
                    ORDER BY is_active DESC, price DESC
                """), {"creator_id": self.creator_id})

                for row in result2:
                    status = "✓" if row[2] else "✗"
                    self.log(f"   {status} {row[0]}: €{row[1] or 'N/A'}")

    # =========================================================================
    # CATEGORY 7: CONVERSATION STATES
    # =========================================================================

    def verify_conversation_states(self):
        """Verify conversation state machine data."""
        self.log("\n" + "=" * 60)
        self.log("CATEGORÍA 7: CONVERSATION STATES")
        self.log("=" * 60)

        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT
                    phase,
                    COUNT(*) as cnt,
                    AVG(message_count) as avg_msgs
                FROM conversation_states
                WHERE creator_id = :creator_id
                GROUP BY phase
                ORDER BY cnt DESC
            """), {"creator_id": self.creator_id})

            phases = {}
            for row in result:
                phases[row[0]] = {"count": row[1], "avg_msgs": round(row[2] or 0, 1)}

            total = sum(p["count"] for p in phases.values())

            self.add_result(
                "7_STATES", "states_total",
                total > 0, "> 0", str(total),
                "Total conversation states"
            )

            # Verify multiple phases exist
            has_progression = len(phases) > 1
            self.add_result(
                "7_STATES", "states_multiple_phases",
                has_progression, "Múltiples fases",
                str(list(phases.keys())),
                "Conversaciones en diferentes fases"
            )

            self.log(f"   Fases: {phases}")

    # =========================================================================
    # CATEGORY 8: CALENDAR AND BOOKINGS
    # =========================================================================

    def verify_calendar(self):
        """Verify calendar and booking data."""
        self.log("\n" + "=" * 60)
        self.log("CATEGORÍA 8: CALENDARIO Y RESERVAS")
        self.log("=" * 60)

        with self.engine.connect() as conn:
            # Booking links
            result = conn.execute(text("""
                SELECT COUNT(*), COUNT(CASE WHEN is_active THEN 1 END)
                FROM booking_links
                WHERE creator_id = :creator_id
            """), {"creator_id": self.creator_id})
            row = result.fetchone()
            total_links, active_links = row if row else (0, 0)

            self.add_result(
                "8_CALENDAR", "booking_links_exist",
                total_links > 0, "> 0", str(total_links),
                "Booking links configurados"
            )

            # Calendar bookings
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'scheduled' THEN 1 END) as scheduled,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                    COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled
                FROM calendar_bookings
                WHERE creator_id = :creator_id
            """), {"creator_id": self.creator_id})
            row = result.fetchone()

            if row:
                total, scheduled, completed, cancelled = row

                self.add_result(
                    "8_CALENDAR", "bookings_exist",
                    total > 0, "> 0", str(total),
                    "Reservas en el sistema"
                )

                if total > 0:
                    self.log(f"   scheduled={scheduled}, completed={completed}, cancelled={cancelled}")

    # =========================================================================
    # CATEGORY 9: KNOWLEDGE BASE
    # =========================================================================

    def verify_knowledge_base(self):
        """Verify knowledge base data."""
        self.log("\n" + "=" * 60)
        self.log("CATEGORÍA 9: KNOWLEDGE BASE")
        self.log("=" * 60)

        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*)
                FROM knowledge_base
                WHERE creator_id = :creator_id
            """), {"creator_id": self.creator_id})
            count = result.scalar() or 0

            self.add_result(
                "9_KB", "knowledge_base_entries",
                count > 0, "> 0", str(count),
                "Entradas en knowledge base"
            )

            # RAG Documents
            try:
                result = conn.execute(text("""
                    SELECT COUNT(*)
                    FROM rag_documents
                    WHERE creator_id = :creator_id
                """), {"creator_id": self.creator_id})
                rag_count = result.scalar() or 0

                self.add_result(
                    "9_KB", "rag_documents",
                    rag_count > 0, "> 0", str(rag_count),
                    "Documentos RAG indexados"
                )
            except Exception:
                self.log("   RAG documents table not found or empty")

    # =========================================================================
    # GENERATE REPORT
    # =========================================================================

    def generate_report(self) -> str:
        """Generate final verification report."""
        self.log("\n" + "=" * 60)
        self.log("REPORTE FINAL")
        self.log("=" * 60)

        # Group by category
        by_category = defaultdict(list)
        for r in self.results:
            by_category[r.category].append(r)

        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        percentage = (passed / total * 100) if total > 0 else 0

        report_lines = [
            "# 📊 REPORTE DE VERIFICACIÓN CLONNECT",
            f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Creator ID:** {self.creator_id}",
            "",
            f"## Resumen: {passed}/{total} tests pasados ({percentage:.1f}%)",
            "",
        ]

        for category in sorted(by_category.keys()):
            tests = by_category[category]
            cat_passed = sum(1 for t in tests if t.passed)
            cat_total = len(tests)
            status = "✅" if cat_passed == cat_total else "⚠️"

            report_lines.append(f"### {status} {category} ({cat_passed}/{cat_total})")
            report_lines.append("")
            report_lines.append("| Test | Status | Expected | Actual |")
            report_lines.append("|------|--------|----------|--------|")

            for t in tests:
                status = "✅" if t.passed else "❌"
                report_lines.append(f"| {t.test_name} | {status} | {t.expected} | {t.actual} |")

            report_lines.append("")

        # Summary
        report_lines.extend([
            "## 🎯 Conclusión",
            "",
            f"- **Tests pasados:** {passed}/{total} ({percentage:.1f}%)",
            f"- **Tests fallidos:** {total - passed}",
            "",
        ])

        if percentage >= 90:
            report_lines.append("✅ **SISTEMA VERIFICADO** - Todos los sistemas críticos funcionan correctamente")
        elif percentage >= 70:
            report_lines.append("⚠️ **REVISIÓN NECESARIA** - Algunos sistemas requieren atención")
        else:
            report_lines.append("❌ **PROBLEMAS CRÍTICOS** - Se requiere intervención urgente")

        return "\n".join(report_lines)

    def run_all(self):
        """Run all verifications."""
        self.log("=" * 60)
        self.log("VERIFICACIÓN TOTAL DE SISTEMAS CLONNECT")
        self.log("=" * 60)
        self.log(f"Creator ID: {self.creator_id}")
        self.log(f"Database: {self.database_url[:50]}...")

        self.verify_tables()
        self.verify_follower_memory()
        self.verify_relationship_dna()
        self.verify_leads()
        self.verify_messages()
        self.verify_products()
        self.verify_conversation_states()
        self.verify_calendar()
        self.verify_knowledge_base()

        report = self.generate_report()
        print("\n" + report)

        # Save report
        report_path = Path(__file__).parent / "verification_report.md"
        with open(report_path, "w") as f:
            f.write(report)
        self.log(f"\nReporte guardado en: {report_path}")

        return self.results


def main():
    """Main entry point."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        print("Usage: DATABASE_URL='postgresql://...' python -m scripts.verify_all_systems")
        sys.exit(1)

    # Default to Stefano's creator ID
    creator_id = os.environ.get(
        "CREATOR_ID",
        "5e5c2364-c99a-4484-b986-741bb84a11cf"
    )

    verifier = SystemVerifier(database_url, creator_id)
    verifier.run_all()


if __name__ == "__main__":
    main()
