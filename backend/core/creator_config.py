"""
Configuración y personalidad del creador para el clon
"""

import os
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class CreatorConfig:
    """Configuración completa de un creador"""
    id: str
    name: str
    instagram_handle: str

    # Credenciales Instagram
    instagram_access_token: str = ""
    instagram_page_id: str = ""
    instagram_user_id: str = ""

    # Clone personality (frontend fields)
    clone_name: str = ""  # Bot name shown in UI
    clone_tone: str = "friendly"  # friendly, professional, casual
    clone_vocabulary: str = ""  # Custom vocabulary/rules
    clone_active: bool = False  # Whether bot is active (starts paused)

    # Personalidad
    personality: Dict[str, Any] = field(default_factory=lambda: {
        "tone": "cercano",  # cercano, profesional, divertido, inspirador
        "formality": "informal",  # formal, informal, mixto
        "energy": "alta",  # baja, media, alta
        "humor": True,
        "empathy": True
    })

    # Vocabulario y estilo
    vocabulary: List[str] = field(default_factory=list)
    emoji_style: str = "moderate"  # none, minimal, moderate, heavy
    greeting_examples: List[str] = field(default_factory=lambda: [
        "¡Hola! 👋",
        "¡Hey! ¿Qué tal?",
        "¡Buenas! 😊"
    ])
    closing_examples: List[str] = field(default_factory=lambda: [
        "¡Un abrazo!",
        "¡Cualquier cosa me dices!",
        "¡Aquí estoy para lo que necesites!"
    ])

    # Ejemplos de respuestas del creador real
    example_responses: List[Dict[str, str]] = field(default_factory=list)

    # Restricciones
    topics_to_avoid: List[str] = field(default_factory=lambda: [
        "política", "religión", "competidores directos"
    ])
    never_say: List[str] = field(default_factory=lambda: [
        "no sé", "imposible", "nunca"
    ])
    always_mention: List[str] = field(default_factory=list)

    # Configuración de ventas
    sales_style: str = "soft"  # soft, moderate, direct
    mention_price_after_messages: int = 3
    max_messages_before_human: int = 15
    auto_send_payment_link: bool = True

    # Escalación
    escalation_keywords: List[str] = field(default_factory=lambda: [
        "hablar contigo", "persona real", "urgente", "problema grave",
        "reembolso", "devolver dinero", "queja formal"
    ])
    escalation_email: str = ""
    escalation_phone: str = ""

    # Horarios
    active_hours: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": False,
        "start": "09:00",
        "end": "21:00",
        "timezone": "Europe/Madrid",
        "weekend_enabled": True
    })

    # Métricas objetivo
    goals: Dict[str, Any] = field(default_factory=lambda: {
        "response_time_seconds": 60,
        "daily_conversations": 50,
        "conversion_rate": 0.05
    })

    # Estado
    is_active: bool = False  # Start paused by default
    pause_reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'CreatorConfig':
        valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid_fields)


class CreatorConfigManager:
    """Gestor de configuración de creadores"""

    def __init__(self, storage_path: str = "data/creators"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    def _get_config_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_config.json")

    def create_config(self, config: CreatorConfig) -> str:
        """Crear configuración de creador"""
        filepath = self._get_config_file(config.id)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Config created for creator {config.id}")
            return config.id
        except Exception as e:
            logger.error(f"Error creating config for {config.id}: {e}")
            raise

    def get_config(self, creator_id: str) -> Optional[CreatorConfig]:
        """Obtener configuración"""
        filepath = self._get_config_file(creator_id)
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return CreatorConfig.from_dict(data)
        except Exception as e:
            logger.error(f"Error loading config for {creator_id}: {e}")
            return None

    def update_config(self, creator_id: str, updates: dict) -> Optional[CreatorConfig]:
        """Actualizar configuración"""
        config = self.get_config(creator_id)
        if not config:
            return None

        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)

        config.updated_at = datetime.now().isoformat()
        self.create_config(config)
        return config

    def delete_config(self, creator_id: str) -> bool:
        """Eliminar configuración"""
        filepath = self._get_config_file(creator_id)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.info(f"Config deleted for creator {creator_id}")
                return True
            except Exception as e:
                logger.error(f"Error deleting config for {creator_id}: {e}")
        return False

    def list_creators(self) -> List[str]:
        """Listar todos los creadores"""
        creators = []
        for filename in os.listdir(self.storage_path):
            if filename.endswith("_config.json"):
                creator_id = filename.replace("_config.json", "")
                creators.append(creator_id)
        return creators

    def set_active(self, creator_id: str, active: bool, reason: str = "") -> bool:
        """Activar/desactivar clon"""
        config = self.get_config(creator_id)
        if not config:
            return False

        config.is_active = active
        config.pause_reason = reason if not active else ""
        config.updated_at = datetime.now().isoformat()
        self.create_config(config)
        return True

    def is_bot_active(self, creator_id: str) -> bool:
        """Verificar si el bot esta activo para un creador"""
        config = self.get_config(creator_id)
        if not config:
            return False
        return config.is_active

    def get_bot_status(self, creator_id: str) -> Dict[str, Any]:
        """Obtener estado completo del bot"""
        config = self.get_config(creator_id)
        if not config:
            return {"exists": False, "active": False}

        return {
            "exists": True,
            "active": config.is_active,
            "pause_reason": config.pause_reason if not config.is_active else None,
            "updated_at": config.updated_at
        }

    def generate_system_prompt(self, creator_id: str) -> str:
        """Generar system prompt para el LLM basado en la configuración"""
        config = self.get_config(creator_id)
        if not config:
            return self._default_system_prompt()

        personality = config.personality

        # Descripción del tono
        tone_desc = {
            "cercano": "cercano y amigable, como hablando con un amigo de confianza",
            "profesional": "profesional pero accesible, experto en mi campo",
            "divertido": "divertido y con buen humor, siempre con alguna broma o comentario gracioso",
            "inspirador": "inspirador y motivador, que impulsa a la acción"
        }.get(personality.get("tone", "cercano"), "cercano y amigable")

        # Descripción de formalidad
        formality_desc = {
            "formal": "Uso 'usted' y lenguaje formal.",
            "informal": "Uso 'tú' y lenguaje informal/coloquial.",
            "mixto": "Adapto la formalidad según el contexto y cómo me escriba la persona."
        }.get(personality.get("formality", "informal"), "")

        # Descripción de emojis
        emoji_desc = {
            "heavy": "Uso emojis frecuentemente para dar energía y cercanía (2-4 por mensaje).",
            "moderate": "Uso emojis de forma moderada, 1-2 por mensaje.",
            "minimal": "Uso emojis ocasionalmente, solo cuando sea muy natural.",
            "none": "No uso emojis en mis respuestas."
        }.get(config.emoji_style, "Uso emojis de forma moderada.")

        # Ejemplos de respuestas
        examples_text = ""
        if config.example_responses:
            examples_text = "\n\nEJEMPLOS DE CÓMO RESPONDO (IMITA ESTE ESTILO):\n"
            for ex in config.example_responses[:5]:
                examples_text += f"\nPregunta: {ex.get('question', '')}\nMi respuesta: {ex.get('response', '')}\n"

        # Vocabulario característico
        vocabulary_text = ""
        if config.vocabulary:
            vocabulary_text = f"\n\nPALABRAS/FRASES QUE USO FRECUENTEMENTE: {', '.join(config.vocabulary)}"

        # Temas a evitar
        avoid_text = ""
        if config.topics_to_avoid:
            avoid_text = f"\n\nTEMAS QUE NUNCA TOCO: {', '.join(config.topics_to_avoid)}"

        # Cosas que nunca digo
        never_say_text = ""
        if config.never_say:
            never_say_text = f"\n\nFRASES QUE NUNCA USO: {', '.join(config.never_say)}"

        # Cosas que siempre menciono
        always_mention_text = ""
        if config.always_mention:
            always_mention_text = f"\n\nCOSAS QUE MENCIONO CUANDO ES RELEVANTE: {', '.join(config.always_mention)}"

        # Estilo de ventas
        sales_style_desc = {
            "soft": "No presiono para vender. Solo menciono mis productos/servicios si la persona muestra interés claro o pregunta directamente. Mi objetivo principal es ayudar y conectar.",
            "moderate": "Menciono mis productos cuando es relevante a la conversación, sin ser agresivo. Doy información útil primero.",
            "direct": "Soy directo sobre mis productos y sus beneficios cuando hay oportunidad, pero siempre de forma natural y sin presionar."
        }.get(config.sales_style, "")

        prompt = f"""Eres el clon de IA de {config.name} (@{config.instagram_handle}).
Respondes mensajes directos de Instagram en nombre de {config.name}.

🎭 MI PERSONALIDAD:
- Mi tono es {tone_desc}.
- {formality_desc}
- {emoji_desc}
{"- Tengo buen sentido del humor y uso bromas cuando es apropiado." if personality.get("humor") else "- Soy más serio y directo, sin hacer bromas."}
{"- Soy muy empático, entiendo y valido las emociones de las personas." if personality.get("empathy") else ""}
- Mi nivel de energía es {personality.get("energy", "media")}.

💼 ESTILO DE VENTAS:
{sales_style_desc}
{vocabulary_text}
{examples_text}
{avoid_text}
{never_say_text}
{always_mention_text}

📋 REGLAS IMPORTANTES:
1. Respondo SIEMPRE como si fuera {config.name}, en primera persona ("yo hago", "mi curso").
2. Soy auténtico y consistente con mi personalidad en cada mensaje.
3. Si no sé algo específico, lo admito de forma natural ("déjame revisar eso y te cuento").
4. Recuerdo y hago referencia a las conversaciones anteriores con cada persona.
5. Mi objetivo es ayudar genuinamente, conectar con la persona y, cuando es natural, guiar hacia mis productos/servicios.
6. Respondo de forma concisa pero completa (máximo 2-3 párrafos cortos).
7. Si alguien está molesto o tiene un problema grave, muestro empatía y ofrezco escalarlo a atención personal.

👋 SALUDOS QUE USO: {', '.join(config.greeting_examples[:3])}
🤝 DESPEDIDAS QUE USO: {', '.join(config.closing_examples[:3])}

Ahora, responde al siguiente mensaje manteniendo mi personalidad y estilo:"""

        return prompt

    def _default_system_prompt(self) -> str:
        """Prompt por defecto si no hay configuración"""
        return """Eres un asistente de IA amigable que responde mensajes de Instagram en nombre de un creador de contenido.

REGLAS:
1. Sé cercano y amigable, como un amigo.
2. Usa un tono informal pero respetuoso.
3. Usa emojis de forma moderada (1-2 por mensaje).
4. Si no sabes algo, admítelo de forma natural.
5. Ayuda a las personas y responde sus preguntas.
6. Si preguntan por productos/servicios, da información útil sin presionar.
7. Responde de forma concisa (máximo 2-3 párrafos).

Responde al siguiente mensaje:"""

    def get_greeting(self, creator_id: str) -> str:
        """Obtener un saludo del creador"""
        config = self.get_config(creator_id)
        if config and config.greeting_examples:
            import random
            return random.choice(config.greeting_examples)
        return "¡Hola! 👋"

    def get_closing(self, creator_id: str) -> str:
        """Obtener una despedida del creador"""
        config = self.get_config(creator_id)
        if config and config.closing_examples:
            import random
            return random.choice(config.closing_examples)
        return "¡Un abrazo!"

    def is_within_active_hours(self, creator_id: str) -> bool:
        """Verificar si estamos dentro del horario activo"""
        config = self.get_config(creator_id)
        if not config:
            return True

        active_hours = config.active_hours
        if not active_hours.get("enabled", False):
            return True

        try:
            from datetime import datetime
            import pytz

            tz = pytz.timezone(active_hours.get("timezone", "UTC"))
            now = datetime.now(tz)

            # Verificar fin de semana
            if now.weekday() >= 5:  # Sábado o domingo
                if not active_hours.get("weekend_enabled", True):
                    return False

            # Verificar horario
            start = datetime.strptime(active_hours.get("start", "00:00"), "%H:%M").time()
            end = datetime.strptime(active_hours.get("end", "23:59"), "%H:%M").time()

            return start <= now.time() <= end

        except Exception as e:
            logger.error(f"Error checking active hours: {e}")
            return True

    def export_config(self, creator_id: str) -> Optional[str]:
        """Exportar configuración como JSON"""
        config = self.get_config(creator_id)
        if not config:
            return None

        # Ocultar tokens sensibles
        export_data = config.to_dict()
        if export_data.get("instagram_access_token"):
            export_data["instagram_access_token"] = "***HIDDEN***"

        return json.dumps(export_data, indent=2, ensure_ascii=False)

    def import_config(self, creator_id: str, json_data: str) -> Optional[CreatorConfig]:
        """Importar configuración desde JSON"""
        try:
            data = json.loads(json_data)
            data["id"] = creator_id  # Asegurar ID correcto

            # Mantener tokens existentes si están ocultos
            existing = self.get_config(creator_id)
            if existing and data.get("instagram_access_token") == "***HIDDEN***":
                data["instagram_access_token"] = existing.instagram_access_token

            config = CreatorConfig.from_dict(data)
            self.create_config(config)
            return config

        except Exception as e:
            logger.error(f"Error importing config: {e}")
            return None
