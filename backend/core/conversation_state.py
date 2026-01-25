"""
Máquina de Estados Conversacional para Clonnect.
Gestiona el flujo de venta: INICIO -> CUALIFICACION -> DESCUBRIMIENTO -> PROPUESTA -> OBJECIONES -> CIERRE

v1.6.0 - State Machine Implementation
v2.0.0 - PostgreSQL Persistence (Phase 2.1)
"""

import os
from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
PERSIST_CONVERSATION_STATE = os.getenv("PERSIST_CONVERSATION_STATE", "true").lower() == "true"


class ConversationPhase(Enum):
    INICIO = "inicio"
    CUALIFICACION = "cualificacion"
    DESCUBRIMIENTO = "descubrimiento"
    PROPUESTA = "propuesta"
    OBJECIONES = "objeciones"
    CIERRE = "cierre"
    ESCALAR = "escalar"


@dataclass
class UserContext:
    """Contexto acumulado del usuario."""
    name: Optional[str] = None
    situation: Optional[str] = None          # "madre de 3", "trabaja mucho"
    goal: Optional[str] = None               # "bajar peso", "mas energia"
    constraints: List[str] = field(default_factory=list)  # ["poco tiempo", "bajo presupuesto"]
    product_interested: Optional[str] = None
    price_discussed: bool = False
    link_sent: bool = False
    objections_raised: List[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Genera contexto para el prompt del LLM."""
        parts = []
        if self.name:
            parts.append(f"Nombre: {self.name}")
        if self.situation:
            parts.append(f"Situacion: {self.situation}")
        if self.goal:
            parts.append(f"Objetivo: {self.goal}")
        if self.constraints:
            parts.append(f"Limitaciones: {', '.join(self.constraints)}")
        if self.product_interested:
            parts.append(f"Interesado en: {self.product_interested}")
        return "\n".join(parts) if parts else "Sin contexto previo"


@dataclass
class ConversationState:
    """Estado completo de una conversacion."""
    follower_id: str
    creator_id: str
    phase: ConversationPhase = ConversationPhase.INICIO
    context: UserContext = field(default_factory=UserContext)
    message_count: int = 0
    updated_at: datetime = field(default_factory=datetime.utcnow)


class StateManager:
    """
    Gestiona estados y transiciones.

    v2.0.0: Now persists to PostgreSQL when PERSIST_CONVERSATION_STATE=true.
    Falls back to in-memory storage if DB is unavailable.
    """

    PHASE_INSTRUCTIONS = {
        ConversationPhase.INICIO: """
FASE: INICIO - Tu objetivo es saludar y despertar curiosidad.
- Haz UNA pregunta abierta: "Que te llamo la atencion?"
- NO menciones productos ni precios todavia
- Maximo 2 oraciones
""",
        ConversationPhase.CUALIFICACION: """
FASE: CUALIFICACION - Tu objetivo es entender QUE busca.
- Pregunta sobre su objetivo (bajar peso, energia, musculo...)
- UNA sola pregunta
- NO presentes productos todavia
""",
        ConversationPhase.DESCUBRIMIENTO: """
FASE: DESCUBRIMIENTO - Tu objetivo es entender su SITUACION.
- Pregunta sobre tiempo disponible, obstaculos
- Muestra empatia con su situacion
- Usa esta info para personalizar despues
""",
        ConversationPhase.PROPUESTA: """
FASE: PROPUESTA - Tu objetivo es presentar el producto ADAPTADO.
- Menciona el producto que encaja con SU situacion
- Incluye precio claro con euro
- Conecta beneficios con lo que te conto
- Pregunta si tiene alguna duda
""",
        ConversationPhase.OBJECIONES: """
FASE: OBJECIONES - Tu objetivo es resolver dudas con empatia.
- Valida su preocupacion
- Ofrece prueba social si hay
- NO seas pushy
- Si no puedes resolver, ofrece hablar con el creador
""",
        ConversationPhase.CIERRE: """
FASE: CIERRE - Tu objetivo es facilitar la compra.
- Da el link de compra
- Ofrece ayuda post-compra
- NO anadas presion
- Se breve
""",
        ConversationPhase.ESCALAR: """
FASE: ESCALAR - Tu objetivo es pasar a humano.
- Informa que vas a notificar al creador
- Resume brevemente el contexto
""",
    }

    def __init__(self):
        self._states: Dict[str, ConversationState] = {}
        self._db_available = False
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database connection if persistence is enabled."""
        if not PERSIST_CONVERSATION_STATE:
            logger.info("[StateManager] Persistence disabled, using in-memory storage")
            return

        try:
            from api.database import SessionLocal
            from api.models import ConversationStateDB
            self._db_available = True
            logger.info("[StateManager] PostgreSQL persistence enabled")
        except ImportError as e:
            logger.warning(f"[StateManager] DB modules not available: {e}. Using in-memory fallback.")
        except Exception as e:
            logger.warning(f"[StateManager] DB init failed: {e}. Using in-memory fallback.")

    def _load_from_db(self, creator_id: str, follower_id: str) -> Optional[ConversationState]:
        """Load state from database."""
        if not self._db_available:
            return None

        try:
            from api.database import SessionLocal
            from api.models import ConversationStateDB

            db = SessionLocal()
            try:
                db_state = db.query(ConversationStateDB).filter(
                    ConversationStateDB.creator_id == creator_id,
                    ConversationStateDB.follower_id == follower_id
                ).first()

                if db_state:
                    # Reconstruct UserContext from JSON
                    context_data = db_state.context or {}
                    user_context = UserContext(
                        name=context_data.get('name'),
                        situation=context_data.get('situation'),
                        goal=context_data.get('goal'),
                        constraints=context_data.get('constraints', []),
                        product_interested=context_data.get('product_interested'),
                        price_discussed=context_data.get('price_discussed', False),
                        link_sent=context_data.get('link_sent', False),
                        objections_raised=context_data.get('objections_raised', [])
                    )

                    # Convert phase string to enum
                    phase = ConversationPhase(db_state.phase) if db_state.phase else ConversationPhase.INICIO

                    return ConversationState(
                        follower_id=follower_id,
                        creator_id=creator_id,
                        phase=phase,
                        context=user_context,
                        message_count=db_state.message_count or 0,
                        updated_at=db_state.updated_at or datetime.utcnow()
                    )
                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[StateManager] Error loading from DB: {e}")
            return None

    def _save_to_db(self, state: ConversationState) -> bool:
        """Save state to database."""
        if not self._db_available:
            return False

        try:
            from api.database import SessionLocal
            from api.models import ConversationStateDB

            db = SessionLocal()
            try:
                # Check if exists
                db_state = db.query(ConversationStateDB).filter(
                    ConversationStateDB.creator_id == state.creator_id,
                    ConversationStateDB.follower_id == state.follower_id
                ).first()

                # Serialize UserContext to dict
                context_dict = {
                    'name': state.context.name,
                    'situation': state.context.situation,
                    'goal': state.context.goal,
                    'constraints': state.context.constraints,
                    'product_interested': state.context.product_interested,
                    'price_discussed': state.context.price_discussed,
                    'link_sent': state.context.link_sent,
                    'objections_raised': state.context.objections_raised
                }

                if db_state:
                    # Update existing
                    db_state.phase = state.phase.value
                    db_state.message_count = state.message_count
                    db_state.context = context_dict
                    db_state.updated_at = datetime.utcnow()
                else:
                    # Create new
                    db_state = ConversationStateDB(
                        creator_id=state.creator_id,
                        follower_id=state.follower_id,
                        phase=state.phase.value,
                        message_count=state.message_count,
                        context=context_dict
                    )
                    db.add(db_state)

                db.commit()
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[StateManager] Error saving to DB: {e}")
            return False

    def get_state(self, follower_id: str, creator_id: str) -> ConversationState:
        """Obtiene o crea estado de conversacion."""
        key = f"{creator_id}:{follower_id}"

        # Check memory cache first
        if key in self._states:
            return self._states[key]

        # Try loading from DB
        if self._db_available:
            db_state = self._load_from_db(creator_id, follower_id)
            if db_state:
                self._states[key] = db_state
                logger.debug(f"[StateManager] Loaded state from DB for {key}")
                return db_state

        # Create new state
        self._states[key] = ConversationState(
            follower_id=follower_id,
            creator_id=creator_id
        )
        return self._states[key]

    def update_state(self, state: ConversationState, message: str, intent: str, response: str) -> ConversationState:
        """Actualiza estado despues de un intercambio."""
        # DEFENSIVE: Ensure message is a string
        if not isinstance(message, str):
            if isinstance(message, dict):
                message = message.get('text', '') or message.get('content', '') or str(message)
            else:
                message = str(message) if message else ""

        state.message_count += 1
        state.updated_at = datetime.utcnow()

        # Extraer contexto del mensaje
        self._extract_context(state, message)

        # Determinar transicion
        new_phase = self._determine_transition(state, intent, message)
        if new_phase and new_phase != state.phase:
            logger.info(f"[STATE] Transition: {state.phase.value} -> {new_phase.value}")
            state.phase = new_phase

        # Trackear respuesta
        self._track_response(state, response)

        # Persist to database
        if self._db_available:
            self._save_to_db(state)

        return state

    def _extract_context(self, state: ConversationState, message: str) -> None:
        """Extrae informacion del usuario."""
        msg = message.lower()

        # Situacion personal
        if any(w in msg for w in ["hijo", "hija", "nino", "madre", "padre", "familia"]):
            if state.context.situation:
                if "hijos" not in state.context.situation:
                    state.context.situation += ", tiene hijos"
            else:
                state.context.situation = "tiene hijos"

        if any(w in msg for w in ["trabajo", "oficina", "viajo", "ocupado", "ocupada", "enfermera", "enfermero", "medico", "doctor"]):
            if state.context.situation:
                if "trabaja" not in state.context.situation:
                    state.context.situation += ", trabaja mucho"
            else:
                state.context.situation = "trabaja mucho"

        # Edad/salud
        import re
        age_match = re.search(r'(?:tengo|soy de)\s+(\d{2,3})\s*(?:años|anos)', msg)
        if age_match:
            age = age_match.group(1)
            age_info = f"{age} años"
            if state.context.situation:
                if "años" not in state.context.situation:
                    state.context.situation += f", {age_info}"
            else:
                state.context.situation = age_info

        # Objetivos
        if any(w in msg for w in ["bajar", "adelgazar", "peso", "perder peso"]):
            state.context.goal = "bajar de peso"
        elif any(w in msg for w in ["musculo", "fuerza", "tonificar"]):
            state.context.goal = "ganar musculo"
        elif any(w in msg for w in ["energia", "cansad", "agotad"]):
            state.context.goal = "mas energia"
        elif any(w in msg for w in ["salud", "sano", "saludable"]):
            state.context.goal = "mejorar salud"

        # Restricciones
        if any(w in msg for w in ["tiempo", "minutos", "ocupad", "rapido"]):
            if "poco tiempo" not in state.context.constraints:
                state.context.constraints.append("poco tiempo")
        if any(w in msg for w in ["dinero", "caro", "presupuesto", "costoso"]):
            if "presupuesto limitado" not in state.context.constraints:
                state.context.constraints.append("presupuesto limitado")
        if any(w in msg for w in ["lesion", "dolor", "rodilla", "espalda"]):
            if "limitacion fisica" not in state.context.constraints:
                state.context.constraints.append("limitacion fisica")

    def _determine_transition(self, state: ConversationState, intent: str, message: str) -> Optional[ConversationPhase]:
        """Determina si hay transicion de fase."""
        current = state.phase
        msg = message.lower()

        # Escalacion tiene prioridad
        if intent == "escalation" or any(w in msg for w in ["hablar con", "humano", "persona real", "el creador"]):
            return ConversationPhase.ESCALAR

        # Transiciones por fase
        if current == ConversationPhase.INICIO:
            # Despues del primer mensaje, pasar a cualificacion
            if state.message_count >= 1:
                return ConversationPhase.CUALIFICACION

        elif current == ConversationPhase.CUALIFICACION:
            # Si sabemos el objetivo, pasar a descubrimiento
            if state.context.goal:
                return ConversationPhase.DESCUBRIMIENTO
            # O si ya van 2+ mensajes
            if state.message_count >= 3:
                return ConversationPhase.DESCUBRIMIENTO

        elif current == ConversationPhase.DESCUBRIMIENTO:
            # Si tenemos situacion o restricciones, o 4+ mensajes
            if state.context.situation or state.context.constraints or state.message_count >= 4:
                return ConversationPhase.PROPUESTA

        elif current == ConversationPhase.PROPUESTA:
            # Si hay objecion, ir a objeciones
            if "objection" in intent:
                return ConversationPhase.OBJECIONES
            # Si hay interes fuerte, ir a cierre
            elif intent == "interest_strong":
                return ConversationPhase.CIERRE
            # Si pide link o quiere comprar
            elif any(w in msg for w in ["link", "comprar", "pagar", "lo quiero"]):
                return ConversationPhase.CIERRE

        elif current == ConversationPhase.OBJECIONES:
            # Si muestra interes despues de objecion, cierre
            if intent == "interest_strong" or any(w in msg for w in ["vale", "ok", "si", "quiero", "me convence"]):
                return ConversationPhase.CIERRE
            # Si sigue con objeciones, quedarse
            elif "objection" in intent:
                return None  # Stay in OBJECIONES

        return None

    def _track_response(self, state: ConversationState, response: str) -> None:
        """Trackea que se dio en la respuesta."""
        resp = response.lower()
        if "€" in response or "euro" in resp:
            state.context.price_discussed = True
        if "http" in resp or "https" in resp:
            state.context.link_sent = True

    def get_phase_instructions(self, phase: ConversationPhase) -> str:
        """Obtiene instrucciones para una fase."""
        return self.PHASE_INSTRUCTIONS.get(phase, "")

    def get_context_reminder(self, state: ConversationState) -> str:
        """Genera recordatorios para evitar repeticiones."""
        reminders = []
        if state.context.price_discussed:
            reminders.append("Ya mencionaste el precio, no lo repitas a menos que te pregunten")
        if state.context.link_sent:
            reminders.append("Ya enviaste el link de compra")
        if state.context.objections_raised:
            reminders.append(f"Objeciones previas: {', '.join(state.context.objections_raised)}")
        return "\n".join(reminders) if reminders else ""

    def build_enhanced_prompt(self, state: ConversationState) -> str:
        """Construye el contexto mejorado para el prompt."""
        phase_instructions = self.get_phase_instructions(state.phase)
        user_context = state.context.to_prompt_context()
        context_reminder = self.get_context_reminder(state)

        parts = [
            "=== ESTADO CONVERSACION ===",
            f"Fase actual: {state.phase.value.upper()}",
            f"Mensajes intercambiados: {state.message_count}",
            "",
            phase_instructions,
            "",
            "=== CONTEXTO USUARIO ===",
            user_context,
        ]

        if context_reminder:
            parts.extend([
                "",
                "=== RECORDATORIOS ===",
                context_reminder,
            ])

        return "\n".join(parts)


# Singleton
_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Obtiene la instancia singleton del StateManager."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager
