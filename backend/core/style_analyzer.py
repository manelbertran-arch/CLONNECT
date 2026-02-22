"""
Style Analyzer — Extract quantitative and qualitative style profiles from creator messages.

Part of ECHO Engine (E = Extract).

Usage:
    from core.style_analyzer import StyleAnalyzer

    analyzer = StyleAnalyzer()
    profile = await analyzer.analyze_creator(creator_id, creator_db_id)
    # Returns StyleProfile dict ready for DB persistence

Requires:
    - Messages in DB for the creator (from copilot or direct DMs)
    - Gemini Flash-Lite for qualitative analysis

Feature flag: ENABLE_STYLE_ANALYZER (default: true)
"""
import json
import logging
import os
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Configuration ---
MIN_MESSAGES_FOR_PROFILE = int(os.getenv("STYLE_MIN_MESSAGES", "30"))
IDEAL_MESSAGES_FOR_PROFILE = int(os.getenv("STYLE_IDEAL_MESSAGES", "200"))
MAX_MESSAGES_TO_ANALYZE = int(os.getenv("STYLE_MAX_MESSAGES", "1000"))
STYLE_PROFILE_VERSION = 1

ENABLE_STYLE_ANALYZER = os.getenv(
    "ENABLE_STYLE_ANALYZER", "true"
).lower() == "true"

# --- Spanish informal patterns (from multilingue_e_informal.md) ---
ABBREVIATIONS_ES = {
    "xq": "porque", "pq": "porque", "xk": "porque",
    "tb": "también", "tmb": "también", "tbien": "también",
    "q": "que", "k": "que",
    "x": "por", "xa": "para", "pa": "para",
    "d": "de", "dl": "del",
    "bn": "bien", "bno": "bueno",
    "msj": "mensaje", "msg": "mensaje",
    "grax": "gracias", "thx": "thanks",
    "ntp": "no te preocupes", "ntc": "no te creas",
    "desp": "después", "dsp": "después",
    "pto": "punto", "min": "minuto",
    "tel": "teléfono", "cel": "celular",
    "fav": "favor", "pls": "please", "plz": "please",
    "tqm": "te quiero mucho", "tkm": "te quiero mucho",
}

# Common Spanish filler words / muletillas
MULETILLAS = [
    "bueno", "mira", "dale", "claro", "o sea", "tipo",
    "la verdad", "nada", "pues", "entonces", "digamos",
    "sabes", "ves", "osea", "básicamente", "literal",
]

# Emoji regex
EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
    "\U0001F680-\U0001F6FF"  # Transport & Map
    "\U0001F900-\U0001F9FF"  # Supplemental
    "\U0001FA00-\U0001FA6F"  # Chess, Extended-A
    "\U00002600-\U000027BF"  # Misc Symbols
    "\U0000FE00-\U0000FE0F"  # Variation Selectors
    "\U0001F1E0-\U0001F1FF"  # Flags
    "]+",
    flags=re.UNICODE,
)

# Question pattern (Spanish)
QUESTION_PATTERN = re.compile(r"[¿?]")

# Laugh patterns
LAUGH_PATTERN = re.compile(r"(?:ja|je|ji|jo){2,}|(?:ha|he){2,}", re.IGNORECASE)


class StyleAnalyzer:
    """Analyze creator's messaging style from historical messages."""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    async def analyze_creator(
        self,
        creator_id: str,
        creator_db_id: str,
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Full analysis pipeline: extract messages → quantitative → qualitative → profile.

        Args:
            creator_id: Creator name/identifier (e.g. "stefano_bonanno")
            creator_db_id: Creator UUID from DB
            force: Re-analyze even if cached profile exists

        Returns:
            StyleProfile dict or None if insufficient data
        """
        if not ENABLE_STYLE_ANALYZER:
            return None

        # Check cache
        if not force and creator_id in self._cache:
            return self._cache[creator_id]

        # 1. Extract creator messages from DB
        messages = self._load_creator_messages(creator_db_id)
        if len(messages) < MIN_MESSAGES_FOR_PROFILE:
            logger.warning(
                f"[STYLE] Insufficient messages for {creator_id}: "
                f"{len(messages)}/{MIN_MESSAGES_FOR_PROFILE}"
            )
            return None

        logger.info(
            f"[STYLE] Analyzing {len(messages)} messages for {creator_id}"
        )

        # 2. Quantitative metrics
        quant = self.extract_quantitative_metrics(messages)

        # 3. Qualitative profile (via LLM)
        qual = await self.extract_qualitative_profile(messages, creator_id)

        # 4. Build composite profile
        profile = self._build_profile(creator_id, quant, qual, len(messages))

        # 5. Cache
        self._cache[creator_id] = profile

        return profile

    # =========================================================================
    # DATA LOADING
    # =========================================================================

    def _load_creator_messages(self, creator_db_id: str) -> List[Dict]:
        """Load creator's outgoing messages from DB.

        Only loads messages where role='assistant' and status in ('sent', 'edited')
        — these are the creator's actual responses (approved or manually written).
        """
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(id=creator_db_id).first()
            if not creator:
                return []

            messages = (
                session.query(
                    Message.content,
                    Message.created_at,
                    Message.intent,
                    Message.copilot_action,
                    Lead.status.label("lead_status"),
                )
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator.id,
                    Message.role == "assistant",
                    Message.status.in_(["sent", "edited"]),
                    Message.content.isnot(None),
                    Message.content != "",
                )
                .order_by(Message.created_at.desc())
                .limit(MAX_MESSAGES_TO_ANALYZE)
                .all()
            )

            return [
                {
                    "content": m.content,
                    "created_at": m.created_at,
                    "intent": m.intent,
                    "copilot_action": m.copilot_action,
                    "lead_status": m.lead_status,
                }
                for m in messages
            ]
        finally:
            session.close()

    # =========================================================================
    # QUANTITATIVE METRICS
    # =========================================================================

    def extract_quantitative_metrics(
        self, messages: List[Dict]
    ) -> Dict[str, Any]:
        """
        Extract numeric/statistical style metrics from messages.

        Inspired by whatsapp-llm generate_style_metrics() + adapted for
        Spanish informal DMs (from multilingue_e_informal.md).
        """
        texts = [m["content"] for m in messages if m.get("content")]
        if not texts:
            return {}

        # --- Message length distribution ---
        lengths = [len(t) for t in texts]
        word_counts = [len(t.split()) for t in texts]

        length_stats = {
            "char_mean": round(statistics.mean(lengths), 1),
            "char_median": round(statistics.median(lengths), 1),
            "char_p10": round(_percentile(lengths, 10), 1),
            "char_p90": round(_percentile(lengths, 90), 1),
            "char_min": min(lengths),
            "char_max": max(lengths),
            "word_mean": round(statistics.mean(word_counts), 1),
            "word_median": round(statistics.median(word_counts), 1),
        }

        # --- Emoji analysis ---
        emoji_counter = Counter()
        msgs_with_emoji = 0
        total_emojis = 0
        for t in texts:
            emojis = EMOJI_PATTERN.findall(t)
            individual = []
            for match in emojis:
                individual.extend(list(match))
            if individual:
                msgs_with_emoji += 1
                total_emojis += len(individual)
                emoji_counter.update(individual)

        emoji_stats = {
            "top_20": emoji_counter.most_common(20),
            "total_count": total_emojis,
            "msgs_with_emoji_pct": round(msgs_with_emoji / len(texts) * 100, 1),
            "avg_per_message": round(total_emojis / len(texts), 2),
        }

        # --- Abbreviations / Muletillas ---
        abbrev_counter = Counter()
        muletilla_counter = Counter()
        for t in texts:
            words = t.lower().split()
            for w in words:
                clean = re.sub(r"[^a-záéíóúüñ]", "", w)
                if clean in ABBREVIATIONS_ES:
                    abbrev_counter[clean] += 1
            for m in MULETILLAS:
                if m in t.lower():
                    muletilla_counter[m] += 1

        # --- Punctuation patterns ---
        exclamation_msgs = sum(1 for t in texts if "!" in t)
        question_msgs = sum(1 for t in texts if QUESTION_PATTERN.search(t))
        ellipsis_msgs = sum(1 for t in texts if "..." in t)
        laugh_msgs = sum(1 for t in texts if LAUGH_PATTERN.search(t))

        punctuation_stats = {
            "exclamation_pct": round(exclamation_msgs / len(texts) * 100, 1),
            "question_pct": round(question_msgs / len(texts) * 100, 1),
            "ellipsis_pct": round(ellipsis_msgs / len(texts) * 100, 1),
            "laugh_pct": round(laugh_msgs / len(texts) * 100, 1),
        }

        # --- Case analysis ---
        all_upper = sum(1 for t in texts if t == t.upper() and len(t) > 3)
        starts_upper = sum(1 for t in texts if t and t[0].isupper())

        case_stats = {
            "all_caps_pct": round(all_upper / len(texts) * 100, 1),
            "starts_uppercase_pct": round(starts_upper / len(texts) * 100, 1),
        }

        # --- Opening / closing patterns ---
        openers = Counter()
        closers = Counter()
        for t in texts:
            first_word = t.split()[0].lower().rstrip("!.,") if t.split() else ""
            if first_word:
                openers[first_word] += 1
            last_word = t.split()[-1].lower().rstrip("!.,?") if t.split() else ""
            if last_word:
                closers[last_word] += 1

        # --- Response time by hour (if timestamps available) ---
        hourly_counts = Counter()
        for m in messages:
            if m.get("created_at"):
                h = m["created_at"].hour if hasattr(m["created_at"], "hour") else 0
                hourly_counts[h] += 1

        # --- Style by lead status ---
        status_lengths = {}
        for m in messages:
            status = m.get("lead_status", "unknown")
            if status not in status_lengths:
                status_lengths[status] = []
            status_lengths[status].append(len(m.get("content", "")))

        style_by_status = {
            status: {
                "avg_length": round(statistics.mean(lens), 1),
                "count": len(lens),
            }
            for status, lens in status_lengths.items()
            if len(lens) >= 3
        }

        return {
            "length": length_stats,
            "emoji": emoji_stats,
            "abbreviations_top_20": abbrev_counter.most_common(20),
            "muletillas_top_20": muletilla_counter.most_common(20),
            "punctuation": punctuation_stats,
            "case": case_stats,
            "openers_top_10": openers.most_common(10),
            "closers_top_10": closers.most_common(10),
            "hourly_distribution": dict(sorted(hourly_counts.items())),
            "style_by_lead_status": style_by_status,
            "total_messages_analyzed": len(texts),
        }

    # =========================================================================
    # QUALITATIVE PROFILE (LLM)
    # =========================================================================

    async def extract_qualitative_profile(
        self,
        messages: List[Dict],
        creator_id: str,
    ) -> Dict[str, Any]:
        """
        Use LLM to extract qualitative style traits.

        Sends a sample of messages to Gemini Flash-Lite and asks for
        structured analysis of tone, humor, sales patterns, etc.
        """
        sample = self._select_representative_sample(messages, n=30)
        sample_text = "\n---\n".join(
            f"[{m.get('intent', '?')}|{m.get('lead_status', '?')}] {m['content']}"
            for m in sample
        )

        prompt = f"""Analiza los siguientes {len(sample)} mensajes reales del creador "{creator_id}" y extrae su perfil de estilo de escritura.

MENSAJES:
{sample_text}

Responde SOLO con un JSON (sin markdown, sin explicaciones):
{{
  "tone": "formal|informal|mixto",
  "energy_level": "alto|medio|bajo",
  "humor_usage": "frecuente|ocasional|raro|ninguno",
  "sales_style": "directo|sutil|consultivo|ninguno",
  "empathy_level": "alto|medio|bajo",
  "formality_markers": ["tuteo|voseo|ustedeo", "usa_emojis", "usa_abreviaciones"],
  "signature_phrases": ["frase1", "frase2", "frase3"],
  "vocabulary_preferences": ["palabra1", "palabra2", "..."],
  "avoids": ["palabra_o_patron_que_evita1", "..."],
  "greeting_style": "descripcion breve de cómo saluda",
  "closing_style": "descripcion breve de cómo cierra conversaciones",
  "sales_patterns": "descripcion de cómo introduce productos/precios",
  "per_lead_type_differences": {{
    "nuevo": "cómo se comunica con leads nuevos",
    "caliente": "cómo se comunica con leads calientes",
    "cliente": "cómo se comunica con clientes existentes"
  }},
  "dialect": "neutro|rioplatense|peninsular|mexicano|colombiano|otro",
  "code_switching": "descripcion de mezcla de idiomas si aplica",
  "overall_summary": "resumen de 2-3 frases del estilo general"
}}"""

        system_prompt = (
            "Eres un lingüista experto en análisis de estilo de comunicación en "
            "español informal de redes sociales. Analiza patrones reales, no inventes."
        )

        try:
            from core.providers.gemini_provider import generate_simple

            result = await generate_simple(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=1024,
                temperature=0.1,
            )

            if not result:
                logger.warning(f"[STYLE] LLM returned empty for {creator_id}")
                return {"error": "llm_empty_response"}

            # Parse JSON
            cleaned = re.sub(r"```(?:json)?\s*", "", result).strip()
            cleaned = re.sub(r"```\s*$", "", cleaned).strip()
            profile = json.loads(cleaned)

            logger.info(f"[STYLE] Qualitative profile generated for {creator_id}")
            return profile

        except json.JSONDecodeError as e:
            logger.warning(f"[STYLE] LLM JSON parse error: {e}")
            return {"error": "json_parse_error", "raw": result[:500] if result else ""}
        except Exception as e:
            logger.error(f"[STYLE] Qualitative analysis failed: {e}")
            return {"error": str(e)}

    def _select_representative_sample(
        self, messages: List[Dict], n: int = 30
    ) -> List[Dict]:
        """Select a diverse sample of messages for LLM analysis.

        Strategy:
        - 50% most recent messages (current style)
        - 25% from different intents (diversity)
        - 25% from different lead statuses (adaptability)
        """
        if len(messages) <= n:
            return messages

        recent = messages[:n // 2]

        # By intent diversity
        by_intent: Dict[str, List] = {}
        for m in messages:
            intent = m.get("intent", "other")
            by_intent.setdefault(intent, []).append(m)

        intent_sample = []
        per_intent = max(1, n // 4 // max(len(by_intent), 1))
        for intent_msgs in by_intent.values():
            intent_sample.extend(intent_msgs[:per_intent])

        # By lead status diversity
        by_status: Dict[str, List] = {}
        for m in messages:
            status = m.get("lead_status", "unknown")
            by_status.setdefault(status, []).append(m)

        status_sample = []
        per_status = max(1, n // 4 // max(len(by_status), 1))
        for status_msgs in by_status.values():
            status_sample.extend(status_msgs[:per_status])

        # Combine and deduplicate
        seen_contents = set()
        combined = []
        for m in recent + intent_sample + status_sample:
            key = m["content"][:100]
            if key not in seen_contents:
                seen_contents.add(key)
                combined.append(m)

        return combined[:n]

    # =========================================================================
    # PROFILE BUILDER
    # =========================================================================

    def _build_profile(
        self,
        creator_id: str,
        quantitative: Dict,
        qualitative: Dict,
        total_messages: int,
    ) -> Dict[str, Any]:
        """Compose the final StyleProfile JSON."""
        if total_messages >= IDEAL_MESSAGES_FOR_PROFILE:
            confidence = 0.9
        elif total_messages >= MIN_MESSAGES_FOR_PROFILE * 2:
            confidence = 0.7
        else:
            confidence = 0.5

        return {
            "version": STYLE_PROFILE_VERSION,
            "creator_id": creator_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "confidence": confidence,
            "total_messages_analyzed": total_messages,
            "quantitative": quantitative,
            "qualitative": qualitative,
            "prompt_injection": self._generate_prompt_section(
                quantitative, qualitative, creator_id
            ),
        }

    def _generate_prompt_section(
        self,
        quant: Dict,
        qual: Dict,
        creator_id: str,
    ) -> str:
        """Generate the style prompt section for injection into dm_agent_v2.py.

        This is the text that gets injected into combined_context as style_prompt.
        It complements Doc D personality profile with data-driven metrics.
        """
        parts = []

        # 1. Overall style summary
        summary = qual.get("overall_summary", "")
        if summary:
            parts.append(f"ESTILO DE {creator_id.upper()}: {summary}")

        # 2. Length targets (from actual data)
        length = quant.get("length", {})
        if length:
            parts.append(
                f"LONGITUD: Promedio {length.get('char_mean', 40)} caracteres "
                f"(rango {length.get('char_p10', 10)}-{length.get('char_p90', 100)}). "
                f"Mediana {length.get('word_mean', 8)} palabras."
            )

        # 3. Emoji usage (from actual data)
        emoji = quant.get("emoji", {})
        if emoji:
            top_emojis = [e[0] for e in emoji.get("top_20", [])[:5]]
            if top_emojis:
                parts.append(
                    f"EMOJIS: Usa {emoji.get('avg_per_message', 0)} emojis/mensaje. "
                    f"Favoritos: {' '.join(top_emojis)}. "
                    f"{emoji.get('msgs_with_emoji_pct', 0)}% de mensajes tienen emoji."
                )

        # 4. Tone and formality
        tone = qual.get("tone", "informal")
        dialect = qual.get("dialect", "neutro")
        parts.append(f"TONO: {tone} ({dialect})")

        formality = qual.get("formality_markers", [])
        if formality:
            parts.append(f"FORMALIDAD: {', '.join(formality)}")

        # 5. Signature phrases
        phrases = qual.get("signature_phrases", [])
        if phrases:
            quoted = ", ".join(f'"{p}"' for p in phrases[:5])
            parts.append(f"FRASES CARACTERÍSTICAS: {quoted}")

        # 6. Vocabulary
        vocab = qual.get("vocabulary_preferences", [])
        if vocab:
            parts.append(f"VOCABULARIO PREFERIDO: {', '.join(vocab[:10])}")

        avoids = qual.get("avoids", [])
        if avoids:
            parts.append(f"EVITAR: {', '.join(avoids[:5])}")

        # 7. Sales style
        sales = qual.get("sales_style", "")
        if sales and sales != "ninguno":
            parts.append(f"ESTILO DE VENTA: {sales}")
            sales_patterns = qual.get("sales_patterns", "")
            if sales_patterns:
                parts.append(f"PATRÓN: {sales_patterns}")

        # 8. Punctuation style
        punct = quant.get("punctuation", {})
        if punct:
            style_hints = []
            if punct.get("exclamation_pct", 0) > 30:
                style_hints.append("usa muchas exclamaciones")
            if punct.get("laugh_pct", 0) > 15:
                style_hints.append("ríe frecuentemente (jaja)")
            if punct.get("ellipsis_pct", 0) > 20:
                style_hints.append("usa puntos suspensivos")
            if style_hints:
                parts.append(f"PUNTUACIÓN: {', '.join(style_hints)}")

        return "\n".join(parts)


# =========================================================================
# UTILITY FUNCTIONS
# =========================================================================

def _percentile(data: List[float], pct: float) -> float:
    """Calculate percentile (simple linear interpolation)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (pct / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


# =========================================================================
# SINGLETON + ENTRY POINTS
# =========================================================================

_analyzer_instance: Optional[StyleAnalyzer] = None


def get_style_analyzer() -> StyleAnalyzer:
    """Get singleton StyleAnalyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = StyleAnalyzer()
    return _analyzer_instance


async def analyze_and_persist(
    creator_id: str,
    creator_db_id: str,
    force: bool = False,
) -> Optional[Dict]:
    """
    Analyze creator style and persist to DB.

    This is the main entry point for the onboarding flow and periodic updates.
    """
    analyzer = get_style_analyzer()
    profile = await analyzer.analyze_creator(creator_id, creator_db_id, force=force)

    if not profile:
        return None

    _save_profile_to_db(creator_db_id, profile)
    return profile


def _save_profile_to_db(creator_db_id: str, profile: Dict) -> None:
    """Save or update StyleProfile in the database."""
    from api.database import SessionLocal
    from api.models import StyleProfileModel

    session = SessionLocal()
    try:
        existing = (
            session.query(StyleProfileModel)
            .filter_by(creator_id=creator_db_id)
            .first()
        )

        profile_json = json.dumps(profile, ensure_ascii=False, default=str)

        if existing:
            existing.profile_data = profile_json
            existing.version = profile.get("version", 1)
            existing.confidence = profile.get("confidence", 0.5)
            existing.messages_analyzed = profile.get("total_messages_analyzed", 0)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_profile = StyleProfileModel(
                creator_id=creator_db_id,
                profile_data=profile_json,
                version=profile.get("version", 1),
                confidence=profile.get("confidence", 0.5),
                messages_analyzed=profile.get("total_messages_analyzed", 0),
            )
            session.add(new_profile)

        session.commit()
        logger.info(
            f"[STYLE] Profile saved for creator {creator_db_id} "
            f"(confidence={profile.get('confidence', 0)}, "
            f"msgs={profile.get('total_messages_analyzed', 0)})"
        )
    except Exception as e:
        session.rollback()
        logger.error(f"[STYLE] Failed to save profile: {e}")
    finally:
        session.close()


def load_profile_from_db(creator_db_id: str) -> Optional[Dict]:
    """Load StyleProfile from DB. Returns parsed JSON or None."""
    from api.database import SessionLocal
    from api.models import StyleProfileModel

    session = SessionLocal()
    try:
        sp = (
            session.query(StyleProfileModel)
            .filter_by(creator_id=creator_db_id)
            .first()
        )
        if sp and sp.profile_data:
            data = json.loads(sp.profile_data) if isinstance(sp.profile_data, str) else sp.profile_data
            return data
        return None
    except Exception as e:
        logger.error(f"[STYLE] Failed to load profile: {e}")
        return None
    finally:
        session.close()
