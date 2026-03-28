"""
Response Variator V2 - Calibration-driven pool responses.

Features:
- 6 sub-pool categories (v10.1): humor, greeting, encouragement, gratitude, reaction, conversational
- Question-aware selection (v9.3): targets creator's real question% rate
- Conversation-level dedup (v10.3): never repeats in same conversation
- Calibration-driven: loads pools from calibration JSON when available
- Fallback pools: hardcoded Stefan pools when no calibration exists

Categories:
- greeting: Hola, Hey, Buenas
- confirmation: Dale, Ok, Perfecto
- thanks: Gracias, A ti
- laugh: Jaja, Jajaja
- emoji: single emoji responses
- celebration: Genial, Qué bien
- farewell: Un abrazo, Hablamos
- dry: Ok, Dale, Sí
- empathy: Entiendo, Ánimo
- humor: Jaja responses + funny reactions (v10)
- encouragement: Vamos!, Dale que podés! (v10)
- gratitude: Gracias, Te quiero (v10)
- reaction: Que lindo!, Genial! (v10)
- conversational: catch-all short responses (v10)
"""

import hashlib
import json
import logging
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_sim

logger = logging.getLogger(__name__)


@dataclass
class PoolMatch:
    """Result of pool matching."""

    matched: bool
    response: Optional[str] = None
    category: Optional[str] = None
    confidence: float = 0.0


class ResponseVariatorV2:
    """Response variator with calibration-driven pools."""

    def __init__(
        self,
        pools_path: str = "data/pools/stefan_real_pools.json",
        calibration_path: Optional[str] = None,
    ):
        self.pools: Dict[str, List[str]] = {}
        self._used_responses: Dict[str, Set[str]] = {}  # conv_id -> used responses (v10.3)
        self._extraction_pools: Dict[str, Dict[str, List[str]]] = {}  # creator_id -> pools
        self._extraction_modes: Dict[str, Dict[str, str]] = {}  # creator_id -> cat -> mode
        self._extraction_multi_bubble: Dict[str, list] = {}  # creator_id -> MultiBubbleTemplate list

        # Try loading from calibration first
        if calibration_path:
            self._load_from_calibration(calibration_path)
        else:
            self._try_load_calibration()

        # Load from pools file if available
        if not self.pools:
            self._load_pools(pools_path)

        # Always merge fallback pools
        self._setup_fallback_pools()

        # Build TF-IDF index for context-aware selection (v11)
        self._build_tfidf_index()

    def _try_load_calibration(self) -> None:
        """Try to load pools from default calibration path."""
        cal_dirs = ["calibrations", "data/calibrations"]
        for cal_dir in cal_dirs:
            for filename in os.listdir(cal_dir) if os.path.isdir(cal_dir) else []:
                if filename.endswith(".json"):
                    self._load_from_calibration(os.path.join(cal_dir, filename))
                    if self.pools:
                        return

    def _load_from_calibration(self, path: str) -> None:
        """Load pools from a calibration JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                cal = json.load(f)
            cal_pools = cal.get("response_pools", {})
            if cal_pools:
                self.pools.update(cal_pools)
                self._calibration = cal
                logger.info(f"Loaded {len(cal_pools)} pool categories from calibration")
        except Exception as e:
            logger.debug(f"Could not load calibration pools from {path}: {e}")

    def _load_pools(self, path: str) -> None:
        """Load pools from legacy file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.pools = json.load(f)
        except Exception as e:
            logger.warning("Suppressed error in with open(path, 'r', encoding='utf-8') as f:: %s", e)

    def _setup_fallback_pools(self) -> None:
        """Setup fallback pools if no data exists."""
        fallback = {
            "greeting": [
                "Hola! 😊", "Hey!", "Buenas!", "Ey!", "Qué tal!",
                "Hola hermano!", "Buenas buenas!", "Hey 😊", "Hola! 😀",
            ],
            "confirmation": [
                "Dale!", "Ok!", "Perfecto!", "Genial!", "Vale!",
                "Sí!", "Claro!", "Bien!", "👍", "Dale dale!",
            ],
            "thanks": [
                "Gracias!", "A ti!", "Gracias hermano!", "Nada!",
                "De nada!", "Gracias! 😊", "💙", "Gracias! 💪",
            ],
            "laugh": ["Jaja", "Jajaja", "Jajajaja", "😂", "🤣", "Jeje"],
            "emoji": ["😊", "💙", "👍", "🙌", "❤️", "💪", "🔥", "✨", "😀"],
            "celebration": [
                "Genial!", "Qué bien!", "Buenísimo!", "Increíble!",
                "Excelente!", "Genial! 🙌", "Qué bueno!", "Me alegro!",
            ],
            "farewell": [
                "Un abrazo!", "Abrazo!", "Hablamos!", "Cuídate!",
                "Hasta pronto!", "Un abrazo grande!", "💙", "Abrazo! 💙",
            ],
            "dry": ["Ok", "Dale", "Sí", "Va", "Bien", "Ya", "Eso"],
            "empathy": [
                "Entiendo", "Te entiendo", "Es así", "Normal",
                "Pasa", "A veces es así", "Ánimo!", "Fuerza!",
            ],
            "affection": [
                "Yo a ti! 💙", "Igualmente! ❤️", "Y yo a ti!",
                "Gracias! Te quiero! 💙", "Yo más! 😊",
            ],
            "praise": [
                "Gracias! 😊", "Muchas gracias! 💙", "Qué lindo! 😊",
                "Me alegro!", "Qué bueno!", "Gracias hermano!", "💙",
            ],
            "meeting_request": [
                "Imposible bro, me explota la agenda jaja",
                "Uf imposible, tengo la agenda llena 😅",
                "Me es imposible ahora mismo, hermano",
                "Ahora no puedo, bro. Quizás más adelante! 😊",
            ],
            # v10.1 sub-pools (fallback)
            "humor": [
                "Jajaja 😂", "Me hiciste reir jaja", "Jajajaja genial",
                "Espectacular 😂", "Jaja morí", "Jajaja que bueno",
            ],
            "encouragement": [
                "Vamos con toda! 💪", "Dale que podés!", "Sos grande!",
                "Vamos! 🔥", "Fuerza! 💪", "Crack!",
            ],
            "gratitude": [
                "Gracias! 😊", "A ti! 💙", "Gracias hermano!",
                "De nada!", "Nada! 😊", "Gracias! 💪",
            ],
            "reaction": [
                "Que lindo! 😊", "Hermoso!", "Genial! 🙌",
                "Espectacular!", "Que bueno!", "Me encanta!",
            ],
            "conversational": [
                "Dale!", "Sí!", "Claro!", "Totalmente!", "Exacto!",
                "Eso! 😊", "Tal cual!", "Posta!",
            ],
        }

        for cat, items in fallback.items():
            if cat not in self.pools or not self.pools[cat]:
                # No calibration pool for this category — use fallback
                self.pools[cat] = items
            # NOTE: if calibration pool exists for this category, do NOT merge
            # Stefan's fallback entries. Calibration pools are creator-specific
            # and mixing in generic "hermano/bro" responses breaks persona.

    def _build_tfidf_index(self) -> None:
        """Build TF-IDF index over all pool responses for context-aware selection."""
        all_responses: List[str] = []
        self._response_index: List[Tuple[str, int, str]] = []  # (category, idx, text)

        for cat, responses in self.pools.items():
            for i, resp in enumerate(responses):
                all_responses.append(resp)
                self._response_index.append((cat, i, resp))

        if all_responses and len(all_responses) >= 2:
            try:
                self._vectorizer = TfidfVectorizer()
                self._tfidf_matrix = self._vectorizer.fit_transform(all_responses)
                logger.info(f"Built TF-IDF index over {len(all_responses)} pool responses")
            except Exception as e:
                logger.debug(f"TF-IDF index build failed: {e}")
                self._vectorizer = None
                self._tfidf_matrix = None
        else:
            self._vectorizer = None
            self._tfidf_matrix = None

    def _load_extraction_pools(self, creator_id: str) -> None:
        """Load pool data from personality extraction (Doc D §4.4-4.5) for a creator."""
        if creator_id in self._extraction_pools:
            return  # Already loaded

        try:
            from core.personality_loader import load_extraction

            extraction = load_extraction(creator_id)
            if not extraction:
                self._extraction_pools[creator_id] = {}
                return

            # Convert TemplateEntry list → flat string list
            pools: Dict[str, List[str]] = {}
            modes: Dict[str, str] = {}
            for cat, entries in extraction.template_pools.items():
                mode = extraction.template_modes.get(cat, "AUTO")
                modes[cat] = mode
                # Only use AUTO pools in the variator (DRAFT/MANUAL need human approval)
                if mode == "AUTO":
                    pools[cat] = [e.text for e in entries]

            self._extraction_pools[creator_id] = pools
            self._extraction_modes[creator_id] = modes
            self._extraction_multi_bubble[creator_id] = extraction.multi_bubble

            total = sum(len(v) for v in pools.values())
            mb_count = len(extraction.multi_bubble)
            logger.info(
                "Loaded extraction pools for %s: %d cats, %d templates, %d multi-bubble",
                creator_id, len(pools), total, mb_count,
            )
        except Exception as e:
            logger.warning("Could not load extraction pools for %s: %s", creator_id, e)
            self._extraction_pools[creator_id] = {}

    def get_pools_for_creator(self, category: str, creator_id: str = "") -> List[str]:
        """Get pool for a category, preferring extraction pools over defaults."""
        if creator_id:
            self._load_extraction_pools(creator_id)
            ext_pools = self._extraction_pools.get(creator_id, {})
            if category in ext_pools and ext_pools[category]:
                return ext_pools[category]
        return self.pools.get(category, [])

    def try_multi_bubble(
        self,
        lead_message: str,
        creator_id: str = "",
        conv_id: str = "",
    ) -> Optional[List[str]]:
        """Try to match a multi-bubble template from Doc D §4.5.

        Returns a list of bubble strings if matched, None otherwise.
        Only returns AUTO-mode templates.
        """
        if not creator_id:
            return None

        self._load_extraction_pools(creator_id)
        templates = self._extraction_multi_bubble.get(creator_id, [])
        if not templates:
            return None

        # Only use AUTO-mode multi-bubble templates
        auto_templates = [t for t in templates if t.mode == "AUTO"]
        if not auto_templates:
            return None

        # Filter out already-used templates for this conversation
        if conv_id and conv_id in self._used_responses:
            used = self._used_responses[conv_id]
            available = [t for t in auto_templates if t.id not in used]
            if not available:
                available = auto_templates
        else:
            available = auto_templates

        # Random selection (multi-bubble is rare, no need for TF-IDF)
        template = random.choice(available)

        # Mark as used
        if conv_id:
            self._mark_used(template.id, conv_id)

        return template.bubbles

    @staticmethod
    def _engagement_score(response: str) -> float:
        """Score 0-1 measuring how much a response invites conversation continuation.

        Note: '?' is handled by the question-aware pipeline (v9.3), not here.
        """
        score = 0.0

        hooks = [
            "cuéntame", "dime", "cómo", "qué tal", "y tú", "verdad",
            "no crees", "sabes", "mira", "fíjate",
        ]
        if any(h in response.lower() for h in hooks):
            score += 0.4

        continuation_emojis = ["🤔", "👀", "💬", "😏", "🧐", "👉"]
        if any(e in response for e in continuation_emojis):
            score += 0.3

        if len(response.strip()) > 15:
            score += 0.2

        if len(response.strip()) < 10:
            score -= 0.3

        return max(0.0, min(1.0, score))

    def _select_context_aware(
        self,
        lead_message: str,
        candidates: List[str],
        category: str,
        turn_index: int = 0,
        top_k: int = 3,
        boost_engagement: bool = False,
    ) -> str:
        """Select the most contextually relevant response using TF-IDF similarity.

        Falls back to random.choice if TF-IDF is unavailable.
        """
        if not self._vectorizer or not candidates or len(candidates) <= top_k:
            return random.choice(candidates) if candidates else ""

        try:
            # Get indices of candidates in the global response index
            candidate_set = set(candidates)
            candidate_indices = [
                i for i, (cat, _, text) in enumerate(self._response_index)
                if text in candidate_set
            ]

            if not candidate_indices:
                return random.choice(candidates)

            # Compute similarity between lead message and candidates
            lead_vec = self._vectorizer.transform([lead_message])
            sims = sklearn_cosine_sim(
                lead_vec, self._tfidf_matrix[candidate_indices]
            ).flatten()

            # Build final scores: context similarity + optional engagement boost
            if boost_engagement:
                eng_scores = np.array([
                    self._engagement_score(self._response_index[idx][2])
                    for idx in candidate_indices
                ])
                final_scores = 0.6 * sims + 0.4 * eng_scores
            else:
                final_scores = sims

            # Select from top-k (not always #1, for variety)
            k = min(top_k, len(final_scores))
            top_indices = np.argsort(final_scores)[-k:]
            selected_local = random.choice(top_indices)
            actual_idx = candidate_indices[selected_local]
            return self._response_index[actual_idx][2]

        except Exception as e:
            logger.debug(f"Context-aware selection failed, falling back to random: {e}")
            return random.choice(candidates)

    def _detect_category(
        self,
        message: str,
        context: Optional[str] = None,
    ) -> Tuple[Optional[str], float]:
        """
        Detect message category for pool matching.

        Enhanced with v10 sub-categories.
        """
        msg = message.lower().strip()
        msg_clean = msg.rstrip("!").rstrip(".").rstrip("?")

        # MEETING REQUESTS - HIGHEST PRIORITY
        meeting_triggers = [
            "quedar", "quedamos", "vernos", "encontrarnos", "veámonos",
            "tomarnos algo", "tomar algo", "un café", "un cafe",
            "unas birras", "unas cervezas", "nos juntamos", "te invito",
        ]
        if any(m in msg for m in meeting_triggers):
            return "meeting_request", 0.98

        # Greetings
        greetings = ["hola", "hey", "buenas", "ey", "hi", "hello"]
        if msg_clean in greetings or any(msg.startswith(g) for g in greetings):
            if len(msg) < 15:
                return "greeting", 0.90

        # Humor (v10) - jaja + funny reactions
        if any(w in msg for w in ["jaja", "jeje", "ajaj", "😂", "🤣"]):
            if "humor" in self.pools:
                return "humor", 0.85
            return "laugh", 0.95

        # Confirmations / Continuations
        confirmations = ["ok", "dale", "vale", "perfecto", "genial", "bien",
                         "sí", "si", "claro", "bueno", "exacto", "totalmente"]
        if msg_clean in confirmations:
            if "conversational" in self.pools and len(msg) < 20:
                return "conversational", 0.85
            return "confirmation", 0.95

        # Emoji only
        if all(ord(c) > 127000 or c.isspace() for c in msg):
            return "emoji", 0.90

        # Thanks / Gratitude (v10)
        if "gracias" in msg or "thanks" in msg:
            if len(msg) < 30:
                if "gratitude" in self.pools:
                    return "gratitude", 0.88
                return "thanks", 0.85

        # Re-engagement → always LLM (needs personalized response)
        re_engagement = ["hace mucho", "hace tiempo", "cuánto tiempo", "cuanto tiempo",
                         "tanto tiempo", "no hablamos", "desaparecí", "desapareci"]
        if any(r in msg for r in re_engagement):
            return None, 0.0

        # Class cancellation — user notifying they can't attend
        cancel_triggers = [
            "no podré venir", "no puedo venir", "no puc venir",
            "no podré ir", "no puedo ir", "avui no puc", "avui no podré",
            "no vendré", "no vinc avui", "no puc anar",
        ]
        if any(t in msg for t in cancel_triggers):
            if "cancel" in self.pools:
                return "cancel", 0.90

        # Farewell — only short, genuine farewells (not "hace mucho que no hablamos")
        farewells = ["abrazo", "chao", "bye", "cuídate", "hablamos", "hasta"]
        if any(f in msg for f in farewells) and len(msg) < 40:
            return "farewell", 0.80

        # Celebration / Reaction (v10)
        # Guard: long messages or questions with reaction words are NOT simple
        # reactions — they need LLM (e.g. "suena genial, pero ¿cuál elegir?")
        reaction_words = ["que lindo", "hermoso", "genial", "espectacular",
                          "increíble", "me encanta", "que bueno", "wow"]
        if any(w in msg for w in reaction_words):
            if len(msg) <= 40 and "?" not in msg:
                if "reaction" in self.pools:
                    return "reaction", 0.82
                return "celebration", 0.70

        # Encouragement (v10) - user shares struggle/achievement
        if any(w in msg for w in ["logré", "pude", "cuesta", "difícil", "miedo"]):
            if "encouragement" in self.pools:
                return "encouragement", 0.75

        # Empathy
        empathy_triggers = ["difícil", "cuesta", "triste", "mal", "complicado"]
        if any(e in msg for e in empathy_triggers):
            return "empathy", 0.60

        # Affection
        affection_triggers = ["te quiero", "te amo", "eres el mejor", "te adoro"]
        if any(a in msg for a in affection_triggers):
            return "affection", 0.90

        # Praise
        praise_triggers = ["muy lindo", "estuvo genial", "eres hermoso", "que crack"]
        if any(p in msg for p in praise_triggers):
            if len(msg) > 30:
                return "praise", 0.85

        # Sales contexts → NO pool (needs LLM)
        if context in {"pregunta_producto", "pregunta_precio", "objecion"}:
            return None, 0.0

        # v10.2: Use pre-classified context to map to pool category
        if context:
            context_to_pool = {
                "casual": "conversational",
                "humor": "humor",
                "reaccion": "reaction",
                "reaction": "reaction",
                "continuacion": "conversational",
                "continuation": "conversational",
                "apoyo_emocional": "encouragement",
                "agradecimiento": "gratitude",
                "saludo": "greeting",
                "story_mention": "reaction",
                "interes": "conversational",
            }
            pool_cat = context_to_pool.get(context)
            if pool_cat and pool_cat in self.pools:
                return pool_cat, 0.75

        # Short messages that aren't sales → conversational pool
        if len(msg) < 60 and "conversational" in self.pools:
            return "conversational", 0.65

        return None, 0.0

    def _get_unused_candidates(
        self,
        candidates: List[str],
        conv_id: str,
    ) -> List[str]:
        """Filter out responses already used in this conversation (v10.3)."""
        if not conv_id:
            return candidates

        if conv_id not in self._used_responses:
            self._used_responses[conv_id] = set()

        used = self._used_responses[conv_id]
        unused = [c for c in candidates if c not in used]

        if not unused:
            # All used -> reset and allow all
            self._used_responses[conv_id] = set()
            return candidates

        return unused

    def _mark_used(self, response: str, conv_id: str) -> None:
        """Mark a response as used in this conversation (v10.3)."""
        if conv_id:
            if conv_id not in self._used_responses:
                self._used_responses[conv_id] = set()
            self._used_responses[conv_id].add(response)

    def try_pool_response(
        self,
        lead_message: str,
        min_confidence: float = 0.7,
        calibration: Optional[dict] = None,
        turn_index: int = 0,
        conv_id: str = "",
        context: Optional[str] = None,
        creator_id: str = "",
    ) -> PoolMatch:
        """
        Try to generate response from pool.

        Enhanced with:
        - Question-aware selection (v9.3)
        - Conversation dedup (v10.3)
        - Calibration-driven pool loading
        - Pre-classified context support (v10.2)
        - Personality extraction pools (v12) — highest priority
        """
        # BUG-06 fix: empty/whitespace messages must never match a pool
        if not lead_message or not lead_message.strip():
            return PoolMatch(matched=False)

        category, confidence = self._detect_category(lead_message, context)

        if category is None or confidence < min_confidence:
            return PoolMatch(matched=False)

        # v12: Prefer extraction pools over defaults
        pool = self.get_pools_for_creator(category, creator_id)
        if not pool:
            return PoolMatch(matched=False)

        # v9.2: Prefer responses within context soft_max
        cal = calibration or getattr(self, "_calibration", {})
        ctx_soft_max = cal.get("context_soft_max", {})
        soft_max = ctx_soft_max.get(context or "", 60)

        # Filter to shorter responses that fit the context
        short_pool = [r for r in pool if len(r) <= soft_max]
        if short_pool and len(short_pool) >= 3:
            pool = short_pool

        # v10.3: Filter already-used responses
        candidates = self._get_unused_candidates(pool, conv_id)
        if not candidates:
            candidates = pool

        # v9.3: Question-aware selection
        cal = calibration or getattr(self, "_calibration", {})
        q_target = cal.get("baseline", {}).get("question_frequency_pct", 8.4) / 100

        # Deterministic "want question" decision based on turn index
        h = int(hashlib.md5(
            f"q_{turn_index}_{lead_message[:20]}".encode()
        ).hexdigest()[:8], 16)
        want_question = (h % 100) < (q_target * 100)

        with_q = [c for c in candidates if "?" in c]
        without_q = [c for c in candidates if "?" not in c]

        if want_question and with_q:
            candidates = with_q
        elif not want_question and without_q:
            candidates = without_q

        response = random.choice(candidates)

        # v9.3b removed: question injection ("Todo bien?", "Cómo estás?") made the
        # bot sound like customer service. Pool responses should stand alone.

        # v10.3: Mark as used
        self._mark_used(response, conv_id)

        return PoolMatch(
            matched=True,
            response=response,
            category=category,
            confidence=confidence,
        )

    def get_pool_for_context(self, context: str) -> list:
        """Get pool of responses for a specific context."""
        return self.pools.get(context, [])


# Singleton
_variator_v2: Optional[ResponseVariatorV2] = None


def get_response_variator_v2() -> ResponseVariatorV2:
    """Get variator V2 instance."""
    global _variator_v2
    if _variator_v2 is None:
        _variator_v2 = ResponseVariatorV2()
    return _variator_v2
