"""
CloneScore Engine — 6-dimension quality evaluation for creator clones.

Dimensions (weights):
  1. style_fidelity (0.20)     — Stylometric similarity, no LLM
  2. knowledge_accuracy (0.20) — LLM judge (GPT-4o-mini)
  3. persona_consistency (0.20)— LLM judge
  4. tone_appropriateness (0.15)— LLM judge
  5. sales_effectiveness (0.15)— Data-driven, no LLM
  6. safety_score (0.10)       — Rule-based, no LLM

Entry points:
  - evaluate_single()  — real-time, lightweight (style only by default)
  - evaluate_batch()   — daily job, all 6 dimensions

Feature flag: ENABLE_CLONE_SCORE (default: false)
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENABLE_CLONE_SCORE = os.getenv("ENABLE_CLONE_SCORE", "false").lower() == "true"

DIMENSION_WEIGHTS = {
    "style_fidelity": 0.20,
    "knowledge_accuracy": 0.20,
    "persona_consistency": 0.20,
    "tone_appropriateness": 0.15,
    "sales_effectiveness": 0.15,
    "safety_score": 0.10,
}

# Safety rule-based patterns
_PROMISE_PATTERNS = [
    r"te\s+garantizo", r"100%\s+garantizado", r"seguro\s+que",
    r"sin\s+duda\s+funciona", r"te\s+prometo", r"garantia\s+total",
    r"resultados?\s+asegurados?",
]

_OFFENSIVE_WORDS = [
    "idiota", "estupido", "imbecil", "mierda", "puta", "cabron",
    "pendejo", "gilipollas", "joder",
]

_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_REGEX = re.compile(r"\+?\d[\d\s\-]{7,14}\d")


class CloneScoreEngine:
    """Main engine for CloneScore evaluation."""

    def __init__(self):
        self._baseline_cache: Dict[str, Dict] = {}
        self._baseline_cache_ts: Dict[str, float] = {}
        self._BASELINE_CACHE_TTL = 300  # 5 minutes

    # =====================================================================
    # PUBLIC: evaluate_single (real-time, style_fidelity only)
    # =====================================================================
    async def evaluate_single(
        self,
        creator_id: str,
        message: str,
        bot_response: str,
        context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Evaluate a single bot response (real-time, lightweight).

        Returns dict with per-dimension scores. Only computes style_fidelity
        by default (free). Set context["full_eval"]=True for all dimensions.
        """
        context = context or {}
        result = {"creator_id": creator_id, "eval_type": "single"}

        try:
            baseline = self._get_style_baseline(creator_id)
            style_score = self._compute_style_fidelity(bot_response, baseline)
            result["dimension_scores"] = {"style_fidelity": style_score}

            if context.get("full_eval"):
                ka = await self._compute_knowledge_accuracy(
                    bot_response, creator_id, context,
                )
                pc = await self._compute_persona_consistency(
                    bot_response, creator_id,
                    context.get("conversation_history", []),
                )
                ta = await self._compute_tone_appropriateness(
                    bot_response,
                    context.get("lead_stage", "nuevo"),
                    context.get("relationship_type", "nuevo"),
                    context.get("intent", "unknown"),
                    message,
                )
                ss = self._compute_safety_score_sync(bot_response, creator_id)

                result["dimension_scores"].update({
                    "knowledge_accuracy": ka,
                    "persona_consistency": pc,
                    "tone_appropriateness": ta,
                    "safety_score": ss,
                })

            result["overall_score"] = self._aggregate(result["dimension_scores"])
            return result

        except Exception as e:
            logger.error(f"[CLONE_SCORE] evaluate_single error: {e}")
            return {"error": str(e), "overall_score": 50.0, "dimension_scores": {}}

    # =====================================================================
    # PUBLIC: evaluate_batch (daily job, all 6 dimensions)
    # =====================================================================
    async def evaluate_batch(
        self,
        creator_id: str,
        creator_db_id,
        sample_size: int = 50,
    ) -> Dict[str, Any]:
        """Evaluate a batch of recent bot responses for a creator.

        Samples up to `sample_size` bot responses from the last 7 days,
        evaluates all 6 dimensions, stores the result in DB.
        """
        import time

        from api.database import SessionLocal
        from api.models import Lead, Message

        start_time = time.monotonic()
        session = SessionLocal()

        try:
            since = datetime.now(timezone.utc) - timedelta(days=7)
            samples = (
                session.query(
                    Message.id,
                    Message.content,
                    Message.intent,
                    Message.lead_id,
                    Message.suggested_response,
                    Message.copilot_action,
                    Message.created_at,
                )
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator_db_id,
                    Message.role == "assistant",
                    Message.content.isnot(None),
                    Message.status == "sent",
                    Message.created_at >= since,
                )
                .order_by(Message.created_at.desc())
                .limit(sample_size)
                .all()
            )

            if not samples:
                logger.info(f"[CLONE_SCORE] No samples for {creator_id}, skipping batch")
                return {"skipped": True, "reason": "no_samples"}

            # Compute free dimensions for ALL samples
            baseline = self._get_style_baseline(creator_id)
            style_scores = []
            safety_scores = []
            knowledge_scores = []
            persona_scores = []
            tone_scores = []

            for sample in samples:
                msg_content = sample.content or ""
                style_scores.append(
                    self._compute_style_fidelity(msg_content, baseline)
                )
                safety_scores.append(
                    self._compute_safety_score_sync(msg_content, creator_id)
                )

            # Compute LLM dimensions for a SUBSET (max 50 to cap cost)
            llm_sample_count = min(len(samples), 50)
            llm_samples = samples[:llm_sample_count]

            for sample in llm_samples:
                msg_content = sample.content or ""
                intent = sample.intent or "unknown"

                lead_context = self._get_lead_context(session, sample.lead_id)
                conv_history = self._get_conversation_snippet(
                    session, sample.lead_id, before=sample.created_at,
                )

                try:
                    ka = await self._compute_knowledge_accuracy(
                        msg_content, creator_id,
                        {"conversation_context": conv_history},
                        creator_db_id=creator_db_id,
                    )
                    knowledge_scores.append(ka)
                except Exception:
                    knowledge_scores.append(50.0)

                try:
                    pc = await self._compute_persona_consistency(
                        msg_content, creator_id, conv_history,
                    )
                    persona_scores.append(pc)
                except Exception:
                    persona_scores.append(50.0)

                try:
                    ta = await self._compute_tone_appropriateness(
                        msg_content,
                        lead_context.get("status", "nuevo"),
                        lead_context.get("relationship_type", "nuevo"),
                        intent,
                        lead_context.get("last_user_message", ""),
                    )
                    tone_scores.append(ta)
                except Exception:
                    tone_scores.append(50.0)

            # Compute sales_effectiveness (data-driven)
            sales_score = self._compute_sales_effectiveness(
                session, creator_db_id, days=30,
            )

            # Aggregate
            dimension_scores = {
                "style_fidelity": round(
                    sum(style_scores) / len(style_scores), 1
                ) if style_scores else 50.0,
                "knowledge_accuracy": round(
                    sum(knowledge_scores) / len(knowledge_scores), 1
                ) if knowledge_scores else 50.0,
                "persona_consistency": round(
                    sum(persona_scores) / len(persona_scores), 1
                ) if persona_scores else 50.0,
                "tone_appropriateness": round(
                    sum(tone_scores) / len(tone_scores), 1
                ) if tone_scores else 50.0,
                "sales_effectiveness": sales_score,
                "safety_score": round(
                    sum(safety_scores) / len(safety_scores), 1
                ) if safety_scores else 50.0,
            }

            overall = self._aggregate(dimension_scores)
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            # Store in DB
            self._store_evaluation(
                session,
                creator_db_id=creator_db_id,
                eval_type="daily",
                overall_score=overall,
                dimension_scores=dimension_scores,
                sample_size=len(samples),
                metadata={
                    "llm_samples": llm_sample_count,
                    "elapsed_ms": elapsed_ms,
                    "estimated_cost_usd": round(llm_sample_count * 0.02 * 3, 4),
                },
            )

            # Alerting
            if overall < 60:
                logger.warning(
                    f"[CLONE_SCORE] WARNING: {creator_id} score={overall:.1f} "
                    f"(below 60 threshold)"
                )
            for dim, score in dimension_scores.items():
                if score < 40:
                    logger.critical(
                        f"[CLONE_SCORE] CRITICAL: {creator_id} {dim}={score:.1f} "
                        f"(below 40 threshold)"
                    )

            logger.info(
                f"[CLONE_SCORE] Batch eval for {creator_id}: "
                f"overall={overall:.1f}, samples={len(samples)}, "
                f"llm_evals={llm_sample_count}, elapsed={elapsed_ms}ms"
            )

            return {
                "creator_id": creator_id,
                "eval_type": "daily",
                "overall_score": overall,
                "dimension_scores": dimension_scores,
                "sample_size": len(samples),
                "llm_samples": llm_sample_count,
                "elapsed_ms": elapsed_ms,
            }

        except Exception as e:
            logger.error(f"[CLONE_SCORE] evaluate_batch error for {creator_id}: {e}")
            session.rollback()
            return {"error": str(e)}
        finally:
            session.close()

    # =====================================================================
    # DIMENSION 1: style_fidelity (no LLM, ~0ms)
    # =====================================================================
    def _compute_style_fidelity(
        self,
        bot_response: str,
        creator_baseline: Dict,
    ) -> float:
        """Compute stylometric similarity between bot response and creator baseline."""
        if not bot_response.strip():
            return 0.0

        if not creator_baseline:
            return 50.0

        avg_len = creator_baseline.get("avg_message_length", 80)
        if avg_len > 0:
            ratio = len(bot_response) / avg_len
            length_score = max(0, 100 - abs(1.0 - ratio) * 150)
        else:
            length_score = 50.0

        bot_emoji_count = len(re.findall(
            r"[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff"
            r"\U0001f680-\U0001f6ff\U0001f1e0-\U0001f1ff"
            r"\u2600-\u26ff\u2700-\u27bf]",
            bot_response,
        ))
        bot_emoji_rate = bot_emoji_count / max(len(bot_response.split()), 1)
        creator_emoji_rate = creator_baseline.get("emoji_rate", 0.0)
        emoji_diff = abs(bot_emoji_rate - creator_emoji_rate)
        emoji_score = max(0, 100 - emoji_diff * 500)

        bot_questions = bot_response.count("?")
        bot_sentences = max(1, len(re.split(r"[.!?\n]", bot_response)))
        bot_q_rate = bot_questions / bot_sentences
        creator_q_rate = creator_baseline.get("question_rate", 0.2)
        q_diff = abs(bot_q_rate - creator_q_rate)
        question_score = max(0, 100 - q_diff * 300)

        informal_markers = creator_baseline.get("informal_markers", [])
        if informal_markers:
            bot_lower = bot_response.lower()
            matches = sum(1 for m in informal_markers if m.lower() in bot_lower)
            informal_score = min(100, (matches / max(1, len(informal_markers) * 0.3)) * 100)
        else:
            informal_score = 70.0

        creator_vocab = set(creator_baseline.get("top_vocabulary", []))
        if creator_vocab:
            bot_words = set(bot_response.lower().split())
            overlap = len(creator_vocab & bot_words)
            vocab_score = min(100, (overlap / max(1, len(creator_vocab) * 0.15)) * 100)
        else:
            vocab_score = 50.0

        total = (
            length_score * 0.25
            + emoji_score * 0.20
            + question_score * 0.20
            + informal_score * 0.15
            + vocab_score * 0.20
        )

        return round(max(0.0, min(100.0, total)), 1)

    # =====================================================================
    # DIMENSION 2: knowledge_accuracy (LLM judge)
    # =====================================================================
    async def _compute_knowledge_accuracy(
        self,
        bot_response: str,
        creator_id: str,
        context: Optional[Dict] = None,
        creator_db_id=None,
    ) -> float:
        """Evaluate information accuracy using LLM judge."""
        from services.llm_judge import LLMJudge

        if creator_db_id is None:
            from api.database import SessionLocal
            from api.models import Creator as _Creator
            _s = SessionLocal()
            try:
                row = _s.query(_Creator.id).filter_by(name=creator_id).first()
                creator_db_id = row[0] if row else None
            finally:
                _s.close()
        knowledge_context = self._get_knowledge_context(creator_db_id)
        conv_context = ""
        if context and context.get("conversation_context"):
            conv_context = "\n".join(
                f"{m.get('role', '?')}: {m.get('content', '')}"
                for m in context["conversation_context"][-5:]
            )

        prompt = f"""Eres un evaluador de precision de informacion para un bot de DMs de un creador de contenido.

DATOS REALES DEL CREADOR:
{knowledge_context}

RESPUESTA DEL BOT:
{bot_response}

CONTEXTO DE LA CONVERSACION:
{conv_context or '(sin contexto adicional)'}

Evalua la PRECISION de la informacion en la respuesta del bot:
1. Los precios mencionados son correctos?
2. Las descripciones de productos/servicios son fieles?
3. Se inventa informacion que no esta en los datos reales?
4. Omite informacion critica que deberia mencionar?

Responde SOLO con JSON:
{{
  "score": <0-100>,
  "hallucinations": ["lista de datos inventados si los hay"],
  "omissions": ["info critica omitida"],
  "reasoning": "explicacion breve"
}}"""

        judge = LLMJudge()
        result = await judge.judge(
            prompt=prompt,
            dimension="knowledge_accuracy",
        )
        return result.get("score", 50.0)

    # =====================================================================
    # DIMENSION 3: persona_consistency (LLM judge)
    # =====================================================================
    async def _compute_persona_consistency(
        self,
        bot_response: str,
        creator_id: str,
        conversation_history: List[Dict],
    ) -> float:
        """Evaluate persona consistency using LLM judge."""
        from services.llm_judge import LLMJudge

        doc_d_summary = self._get_doc_d_summary(creator_id)
        history_text = ""
        if conversation_history:
            history_text = "\n".join(
                f"{m.get('role', '?')}: {m.get('content', '')}"
                for m in conversation_history[-10:]
            )

        prompt = f"""Eres un evaluador de consistencia de personalidad para un clon de IA de un creador.

PERSONALIDAD DEL CREADOR (Doc D):
{doc_d_summary or '(no disponible)'}

HISTORIAL DE CONVERSACION (ultimos mensajes):
{history_text or '(sin historial)'}

RESPUESTA ACTUAL DEL BOT:
{bot_response}

Evalua la CONSISTENCIA de la personalidad:
1. La respuesta es coherente con la personalidad definida en Doc D?
2. Se contradice con algo dicho anteriormente en la conversacion?
3. Mantiene el mismo nivel de formalidad/informalidad?
4. Respeta los limites de lo que el creador haria o diria?

Responde SOLO con JSON:
{{
  "score": <0-100>,
  "contradictions": ["lista de contradicciones detectadas"],
  "persona_breaks": ["momentos donde el bot sale de personaje"],
  "reasoning": "explicacion breve"
}}"""

        judge = LLMJudge()
        result = await judge.judge(
            prompt=prompt,
            dimension="persona_consistency",
        )
        return result.get("score", 50.0)

    # =====================================================================
    # DIMENSION 4: tone_appropriateness (LLM judge)
    # =====================================================================
    async def _compute_tone_appropriateness(
        self,
        bot_response: str,
        lead_stage: str,
        relationship_type: str,
        intent: str,
        follower_message: str,
    ) -> float:
        """Evaluate tone appropriateness using LLM judge."""
        from services.llm_judge import LLMJudge

        prompt = f"""Eres un evaluador de adecuacion del tono para un bot de DMs de ventas.

CONTEXTO DEL LEAD:
- Etapa: {lead_stage}
- Tipo de relacion: {relationship_type}
- Ultimo intent: {intent}

RESPUESTA DEL BOT:
{bot_response}

MENSAJE DEL FOLLOWER:
{follower_message or '(no disponible)'}

Evalua si el TONO es apropiado:
1. Para un lead "nuevo": es acogedor sin ser agresivo en ventas?
2. Para un lead "caliente": aprovecha el interes sin presionar?
3. Para un "amigo": es cercano y natural, no comercial?
4. Para un "cliente": es servicial y profesional?
5. Si el follower esta frustrado: muestra empatia?
6. Si es primera interaccion: no asume familiaridad?

Responde SOLO con JSON:
{{
  "score": <0-100>,
  "tone_issues": ["problemas de tono detectados"],
  "ideal_tone": "descripcion del tono ideal para este contexto",
  "reasoning": "explicacion breve"
}}"""

        judge = LLMJudge()
        result = await judge.judge(
            prompt=prompt,
            dimension="tone_appropriateness",
        )
        return result.get("score", 50.0)

    # =====================================================================
    # DIMENSION 5: sales_effectiveness (no LLM, data-driven)
    # =====================================================================
    def _compute_sales_effectiveness(
        self,
        session,
        creator_db_id,
        days: int = 30,
    ) -> float:
        """Compute sales effectiveness from lead data and copilot metrics."""
        from sqlalchemy import func

        from api.models import Lead, Message

        since = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            total_leads = (
                session.query(func.count(Lead.id))
                .filter(
                    Lead.creator_id == creator_db_id,
                    Lead.first_contact_at >= since,
                )
                .scalar()
            ) or 1

            progressed_leads = (
                session.query(func.count(Lead.id))
                .filter(
                    Lead.creator_id == creator_db_id,
                    Lead.first_contact_at >= since,
                    Lead.status.in_(["caliente", "cliente"]),
                )
                .scalar()
            ) or 0

            stage_rate = min(100.0, (progressed_leads / total_leads) * 100)

            copilot_total = (
                session.query(func.count(Message.id))
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator_db_id,
                    Message.copilot_action.isnot(None),
                    Message.created_at >= since,
                )
                .scalar()
            ) or 1

            copilot_approved = (
                session.query(func.count(Message.id))
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator_db_id,
                    Message.copilot_action.in_(["approved", "edited"]),
                    Message.created_at >= since,
                )
                .scalar()
            ) or 0

            approval_rate = min(100.0, (copilot_approved / copilot_total) * 100)

            ghost_leads = (
                session.query(func.count(Lead.id))
                .filter(
                    Lead.creator_id == creator_db_id,
                    Lead.first_contact_at >= since,
                    Lead.status.in_(["frio", "frío"]),
                )
                .scalar()
            ) or 0

            ghost_rate = 100.0 - min(100.0, (ghost_leads / total_leads) * 100)

            edited_msgs = (
                session.query(Message.content, Message.suggested_response)
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator_db_id,
                    Message.copilot_action == "edited",
                    Message.suggested_response.isnot(None),
                    Message.content.isnot(None),
                    Message.created_at >= since,
                )
                .limit(200)
                .all()
            )

            if edited_msgs:
                edit_distances = []
                for content, suggested in edited_msgs:
                    if suggested and content:
                        dist = abs(len(content) - len(suggested))
                        max_len = max(len(content), len(suggested), 1)
                        edit_distances.append(1.0 - (dist / max_len))
                avg_edit_similarity = (
                    sum(edit_distances) / len(edit_distances)
                ) if edit_distances else 0.5
            else:
                avg_edit_similarity = 0.7

            edit_score = avg_edit_similarity * 100

            total_score = (
                stage_rate * 0.30
                + approval_rate * 0.25
                + ghost_rate * 0.20
                + edit_score * 0.25
            )

            return round(max(0.0, min(100.0, total_score)), 1)

        except Exception as e:
            logger.error(f"[CLONE_SCORE] sales_effectiveness error: {e}")
            return 50.0

    # =====================================================================
    # DIMENSION 6: safety_score (rules, no LLM)
    # =====================================================================
    def _compute_safety_score_sync(
        self,
        bot_response: str,
        creator_id: str,
    ) -> float:
        """Compute safety score using rule-based checks (sync, no LLM)."""
        score = 100.0
        bot_lower = bot_response.lower()

        for pattern in _PROMISE_PATTERNS:
            if re.search(pattern, bot_lower):
                score -= 15

        for word in _OFFENSIVE_WORDS:
            if word in bot_lower:
                score -= 30

        creator_contacts = self._get_creator_contacts(creator_id)
        emails_in_response = _EMAIL_REGEX.findall(bot_response)
        for email in emails_in_response:
            if email.lower() not in creator_contacts.get("emails", []):
                score -= 20

        phones_in_response = _PHONE_REGEX.findall(bot_response)
        for phone in phones_in_response:
            cleaned = re.sub(r"[\s\-]", "", phone)
            if cleaned not in creator_contacts.get("phones", []):
                score -= 20

        return round(max(0.0, min(100.0, score)), 1)

    # =====================================================================
    # AGGREGATION
    # =====================================================================
    def _aggregate(self, dimension_scores: Dict[str, float]) -> float:
        """Compute weighted aggregate score with safety penalty."""
        weighted_sum = 0.0
        total_weight = 0.0

        for dim, weight in DIMENSION_WEIGHTS.items():
            if dim in dimension_scores:
                weighted_sum += dimension_scores[dim] * weight
                total_weight += weight

        if total_weight > 0:
            weighted_sum = weighted_sum / total_weight * sum(DIMENSION_WEIGHTS.values())

        safety = dimension_scores.get("safety_score", 50.0)
        if safety < 30:
            weighted_sum *= 0.5

        return round(max(0.0, min(100.0, weighted_sum)), 1)

    # =====================================================================
    # HELPERS: data loading
    # =====================================================================
    def _get_style_baseline(self, creator_id: str) -> Dict:
        """Load creator's style baseline from tone_profiles table."""
        import time
        now = time.time()
        if creator_id in self._baseline_cache:
            if now - self._baseline_cache_ts.get(creator_id, 0) < self._BASELINE_CACHE_TTL:
                return self._baseline_cache[creator_id]

        from api.database import SessionLocal
        from api.models import ToneProfile

        session = SessionLocal()
        try:
            tp = (
                session.query(ToneProfile.profile_data)
                .filter(ToneProfile.creator_id == creator_id)
                .first()
            )
            if not tp or not tp.profile_data:
                return {}

            data = tp.profile_data
            baseline = {
                "avg_message_length": data.get("avg_message_length", 80),
                "emoji_rate": data.get("emoji_frequency", 0.1),
                "question_rate": data.get("question_frequency", 0.2),
                "informal_markers": data.get("filler_words", [])
                    + data.get("slang_words", []),
                "top_vocabulary": data.get("vocabulary_sample", []),
            }

            self._baseline_cache[creator_id] = baseline
            self._baseline_cache_ts[creator_id] = now
            return baseline

        except Exception as e:
            logger.error(f"[CLONE_SCORE] _get_style_baseline error: {e}")
            return {}
        finally:
            session.close()

    def _get_knowledge_context(self, creator_db_id) -> str:
        """Load products and knowledge_base entries for accuracy checking."""
        from api.database import SessionLocal
        from api.models import KnowledgeBase, Product

        if not creator_db_id:
            return "(sin datos de productos/conocimiento)"

        session = SessionLocal()
        try:
            products = (
                session.query(Product.name, Product.description, Product.price, Product.currency)
                .filter(Product.creator_id == creator_db_id, Product.is_active.is_(True))
                .all()
            )
            kb_entries = (
                session.query(KnowledgeBase.question, KnowledgeBase.answer)
                .filter(KnowledgeBase.creator_id == creator_db_id)
                .limit(20)
                .all()
            )

            parts = []
            if products:
                parts.append("PRODUCTOS/SERVICIOS:")
                for p in products:
                    price_str = f"{p.price} {p.currency}" if p.price else "sin precio definido"
                    parts.append(f"  - {p.name}: {(p.description or '')[:100]} ({price_str})")

            if kb_entries:
                parts.append("\nBASE DE CONOCIMIENTO:")
                for kb in kb_entries:
                    parts.append(f"  P: {kb.question[:80]}")
                    parts.append(f"  R: {kb.answer[:120]}")

            return "\n".join(parts) if parts else "(sin datos de productos/conocimiento)"

        except Exception as e:
            logger.error(f"[CLONE_SCORE] _get_knowledge_context error: {e}")
            return "(error cargando contexto)"
        finally:
            session.close()

    def _get_doc_d_summary(self, creator_id: str) -> str:
        """Load Doc D personality summary for persona consistency check."""
        try:
            from core.personality_loader import load_personality

            personality = load_personality(creator_id)
            if personality and isinstance(personality, dict):
                doc_d = personality.get("doc_d", personality.get("personality", {}))
                if isinstance(doc_d, dict):
                    parts = []
                    if doc_d.get("name"):
                        parts.append(f"Nombre: {doc_d['name']}")
                    if doc_d.get("tone"):
                        parts.append(f"Tono: {doc_d['tone']}")
                    if doc_d.get("communication_style"):
                        parts.append(f"Estilo: {doc_d['communication_style']}")
                    if doc_d.get("values"):
                        parts.append(f"Valores: {', '.join(doc_d['values'][:5])}")
                    if doc_d.get("boundaries"):
                        parts.append(f"Limites: {', '.join(doc_d['boundaries'][:5])}")
                    return "\n".join(parts)
                elif isinstance(doc_d, str):
                    return doc_d[:500]
            return ""
        except Exception as e:
            logger.debug(f"[CLONE_SCORE] _get_doc_d_summary error: {e}")
            return ""

    def _get_creator_contacts(self, creator_id: str) -> Dict:
        """Load creator's real contact info for safety checking."""
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = (
                session.query(Creator.email, Creator.paypal_email)
                .filter(Creator.name == creator_id)
                .first()
            )
            if not creator:
                return {"emails": [], "phones": []}

            emails = []
            if creator.email:
                emails.append(creator.email.lower())
            if creator.paypal_email:
                emails.append(creator.paypal_email.lower())

            return {"emails": emails, "phones": []}

        except Exception as e:
            logger.error(f"[CLONE_SCORE] _get_creator_contacts error: {e}")
            return {"emails": [], "phones": []}
        finally:
            session.close()

    def _get_lead_context(self, session, lead_id) -> Dict:
        """Get lead context for tone evaluation."""
        from api.models import Lead

        try:
            lead = session.query(Lead).filter_by(id=lead_id).first()
            if not lead:
                return {}
            return {
                "status": lead.status or "nuevo",
                "relationship_type": lead.relationship_type or "nuevo",
            }
        except Exception:
            return {}

    def _get_conversation_snippet(
        self, session, lead_id, before=None, limit: int = 10,
    ) -> List[Dict]:
        """Get last N messages before a timestamp for context."""
        from api.models import Message

        try:
            query = (
                session.query(Message.role, Message.content, Message.created_at)
                .filter(
                    Message.lead_id == lead_id,
                    Message.content.isnot(None),
                )
            )
            if before:
                query = query.filter(Message.created_at < before)

            messages = (
                query.order_by(Message.created_at.desc())
                .limit(limit)
                .all()
            )

            return [
                {"role": m.role, "content": (m.content or "")[:200]}
                for m in reversed(messages)
            ]
        except Exception:
            return []

    def _store_evaluation(
        self,
        session,
        creator_db_id,
        eval_type: str,
        overall_score: float,
        dimension_scores: Dict,
        sample_size: int,
        metadata: Dict,
    ):
        """Store CloneScore evaluation in DB."""
        from api.models import CloneScoreEvaluation

        try:
            evaluation = CloneScoreEvaluation(
                creator_id=creator_db_id,
                eval_type=eval_type,
                overall_score=overall_score,
                dimension_scores=dimension_scores,
                sample_size=sample_size,
                eval_metadata=metadata,
            )
            session.add(evaluation)
            session.commit()
        except Exception as e:
            logger.error(f"[CLONE_SCORE] _store_evaluation error: {e}")
            session.rollback()


# Module-level singleton
_engine_instance: Optional[CloneScoreEngine] = None


def get_clone_score_engine() -> CloneScoreEngine:
    """Get or create the CloneScore engine singleton."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = CloneScoreEngine()
    return _engine_instance
