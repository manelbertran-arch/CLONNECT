"""
Phase 4 — Bot Configurator (Doc D)

Generates the system prompt, blacklist, and template pool
from the Personality Profile (Doc C).
"""

import json
import logging
from datetime import datetime
from typing import Optional

from core.personality_extraction.llm_client import extract_json_with_llm, extract_with_llm
from core.personality_extraction.models import (
    BotConfiguration,
    MultiBubbleTemplate,
    PersonalityProfile,
    TemplateCategory,
    TemplateEntry,
    WritingStyle,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_GENERATOR = """Eres un experto en diseño de system prompts para LLMs que replican personalidades conversacionales.

Tu tarea: dado un Personality Profile detallado de un creador de contenido, generar un system prompt completo que permita a Gemini Flash-Lite / GPT-4o-mini replicar al creador en DMs con fidelidad del 80-90%.

El system prompt debe incluir estas secciones en este orden:
1. IDENTIDAD — datos duros del creador
2. REGLAS DE ESTILO — instrucciones cuantificadas con ejemplos CORRECTO/INCORRECTO
3. TONO — reglas de adaptación por tipo de interlocutor
4. VOCABULARIO — diccionario resumido (saludos, despedidas, muletillas, etc.)
5. MÉTODO DE VENTA — cómo vende el creador
6. PROHIBICIONES — blacklist completa de frases que el creador nunca usa

REGLAS:
- Sé ESPECÍFICO y CUANTIFICADO. "Sé informal" → MAL. "Usa tuteo, máximo 40 chars por mensaje, 1 emoji cada 3 mensajes" → BIEN.
- Incluye ejemplos reales CORRECTO vs INCORRECTO para cada regla.
- El prompt debe ser autocontenido (no referenciar documentos externos).
- Máximo 3000 tokens para el system prompt final.
- Escribe en español.

Devuelve SOLO el system prompt, sin explicaciones adicionales."""


TEMPLATE_POOL_GENERATOR = """Eres un experto en diseño de template pools para bots conversacionales.

Tu tarea: dado un Personality Profile, extraer TODAS las plantillas de respuesta reutilizables del creador.

Devuelve un JSON con este formato exacto:
{
  "categories": [
    {
      "category": "greeting",
      "frequency_pct": 15.0,
      "risk_level": "low",
      "mode": "AUTO",
      "templates": [
        {"text": "Hola! 😊", "context": "saludo genérico", "observed_count": 12},
        {"text": "Ey! Qué onda?", "context": "saludo informal", "observed_count": 5}
      ]
    }
  ],
  "multi_bubble": [
    {
      "template_id": "greeting_warm",
      "intent": "saludo a conocido",
      "messages": ["Hola hermano!", "Cómo andás?"],
      "risk": "low",
      "mode": "AUTO"
    }
  ],
  "blacklist_phrases": ["puedo ayudarte", "no dudes en", "estaré encantado de"],
  "max_message_length_chars": 120,
  "max_emojis_per_message": 2,
  "max_emojis_per_block": 4,
  "enforce_fragmentation": true,
  "min_bubbles": 1,
  "max_bubbles": 3
}

CATEGORÍAS OBLIGATORIAS:
reaction, confirmation, greeting, gratitude, laugh, celebration, farewell,
encouragement, emoji_only, question, reconnect, sales_soft, scheduling, emotional, content_validation

REGLAS:
- Solo incluye frases REALES del creador (extraídas del perfil).
- Si no hay suficientes datos para una categoría, déjala con templates vacíos.
- risk_level: low (respuestas simples), medium (requieren contexto), high (venta/emocional).
- mode: AUTO (se envía solo), DRAFT (requiere aprobación), MANUAL (siempre humano).
- Los valores numéricos (max_length, max_emojis) deben basarse en las estadísticas del perfil.

Devuelve SOLO el JSON válido, sin texto adicional."""


async def generate_system_prompt(
    profile: PersonalityProfile,
) -> str:
    """Generate the calibrated system prompt from the personality profile."""
    ws = profile.writing_style

    user_message = (
        f"PERSONALITY PROFILE DE: {profile.creator_name}\n"
        f"Confianza: {profile.confidence}\n"
        f"Basado en: {profile.messages_analyzed} mensajes / {profile.leads_analyzed} leads / {profile.months_covered} meses\n\n"
        f"ESTADÍSTICAS DE ESCRITURA:\n"
        f"- Longitud media: {ws.avg_message_length} chars (mediana: {ws.median_message_length})\n"
        f"- P90: {ws.p90_message_length} chars\n"
        f"- % cortos (<30 chars): {ws.short_msgs_pct}%\n"
        f"- Emojis en {ws.emoji_pct}% de mensajes, media {ws.avg_emojis_per_msg}/msg\n"
        f"- Top emojis: {', '.join(e['emoji'] for e in ws.top_emojis[:5])}\n"
        f"- Fragmentación: {ws.avg_bubbles_per_turn} burbujas/turno ({ws.fragmentation_multi_pct}% multi-burbuja)\n"
        f"- Idioma: {ws.primary_language} ({ws.dialect})\n"
        f"- Risas: {', '.join(v['variant'] for v in ws.laugh_variants[:3])}\n\n"
        f"PERFIL COMPLETO (análisis LLM):\n{profile.raw_profile_text}"
    )

    result = await extract_with_llm(
        system_prompt=SYSTEM_PROMPT_GENERATOR,
        user_message=user_message,
        max_tokens=4096,
        temperature=0.3,
    )
    return result or ""


async def generate_template_pool(
    profile: PersonalityProfile,
) -> Optional[dict]:
    """Generate the template pool and blacklist from the personality profile."""
    ws = profile.writing_style

    user_message = (
        f"PERSONALITY PROFILE DE: {profile.creator_name}\n\n"
        f"ESTADÍSTICAS:\n"
        f"- Longitud media: {ws.avg_message_length} chars, P90: {ws.p90_message_length}\n"
        f"- Emojis: {ws.emoji_pct}% mensajes, media {ws.avg_emojis_per_msg}/msg, max {ws.max_emojis_observed}\n"
        f"- Fragmentación: {ws.avg_bubbles_per_turn} burbujas/turno\n\n"
        f"PERFIL COMPLETO:\n{profile.raw_profile_text}"
    )

    return await extract_json_with_llm(
        system_prompt=TEMPLATE_POOL_GENERATOR,
        user_message=user_message,
        max_tokens=8192,
        temperature=0.2,
    )


async def generate_bot_configuration(
    profile: PersonalityProfile,
) -> BotConfiguration:
    """Generate the complete bot configuration (Doc D)."""
    config = BotConfiguration()

    # Generate system prompt
    logger.info("Generating system prompt...")
    config.system_prompt = await generate_system_prompt(profile)

    # Generate template pool
    logger.info("Generating template pool...")
    pool_data = await generate_template_pool(profile)

    if pool_data:
        # Parse blacklist
        config.blacklist_phrases = pool_data.get("blacklist_phrases", [])
        config.max_message_length_chars = pool_data.get("max_message_length_chars", int(profile.writing_style.p90_message_length) or 200)
        config.max_emojis_per_message = pool_data.get("max_emojis_per_message", profile.writing_style.max_emojis_observed or 3)
        config.max_emojis_per_block = pool_data.get("max_emojis_per_block", 5)
        config.enforce_fragmentation = pool_data.get("enforce_fragmentation", profile.writing_style.fragmentation_multi_pct > 30)
        config.min_bubbles = pool_data.get("min_bubbles", 1)
        config.max_bubbles = pool_data.get("max_bubbles", 3)

        # Parse template categories
        for cat_data in pool_data.get("categories", []):
            templates = []
            for t in cat_data.get("templates", []):
                templates.append(TemplateEntry(
                    text=t.get("text", ""),
                    context=t.get("context", ""),
                    observed_count=t.get("observed_count", 0),
                    variables=t.get("variables", []),
                ))
            config.template_categories.append(TemplateCategory(
                category=cat_data.get("category", ""),
                frequency_pct=cat_data.get("frequency_pct", 0),
                risk_level=cat_data.get("risk_level", "low"),
                mode=cat_data.get("mode", "AUTO"),
                templates=templates,
            ))

        # Parse multi-bubble templates
        for mb_data in pool_data.get("multi_bubble", []):
            config.multi_bubble_templates.append(MultiBubbleTemplate(
                template_id=mb_data.get("template_id", ""),
                intent=mb_data.get("intent", ""),
                messages=mb_data.get("messages", []),
                risk=mb_data.get("risk", "low"),
                mode=mb_data.get("mode", "AUTO"),
                requires_context=mb_data.get("requires_context", False),
                source_leads=mb_data.get("source_leads", []),
            ))
    else:
        # Fallback: use writing style stats for basic config
        ws = profile.writing_style
        config.max_message_length_chars = int(ws.p90_message_length) if ws.p90_message_length else 200
        config.max_emojis_per_message = ws.max_emojis_observed or 3
        config.enforce_fragmentation = ws.fragmentation_multi_pct > 30

    return config


def generate_doc_d(config: BotConfiguration) -> str:
    """Generate the complete Doc D text."""
    sections = [
        "# DOCUMENTO D: CONFIGURACIÓN TÉCNICA DEL BOT",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 4.1 SYSTEM PROMPT DEL CLON",
        "```",
        config.system_prompt,
        "```",
        "",
        "## 4.2 BLACKLIST DE FRASES",
        f"Total frases prohibidas: {len(config.blacklist_phrases)}",
    ]
    for phrase in config.blacklist_phrases:
        sections.append(f'  - "{phrase}"')

    sections.extend([
        "",
        "## 4.3 PARÁMETROS DE CALIBRACIÓN",
        f"- max_message_length_chars: {config.max_message_length_chars}",
        f"- max_emojis_per_message: {config.max_emojis_per_message}",
        f"- max_emojis_per_block: {config.max_emojis_per_block}",
        f"- enforce_fragmentation: {config.enforce_fragmentation}",
        f"- min_bubbles: {config.min_bubbles}",
        f"- max_bubbles: {config.max_bubbles}",
        "",
        "## 4.4 TEMPLATE POOL",
        f"Total categorías: {len(config.template_categories)}",
    ])

    for cat in config.template_categories:
        sections.append(f"\n### {cat.category} (freq={cat.frequency_pct}%, risk={cat.risk_level}, mode={cat.mode})")
        for t in cat.templates:
            sections.append(f'  → "{t.text}" — {t.context} ({t.observed_count}x)')

    if config.multi_bubble_templates:
        sections.extend([
            "",
            "## 4.5 PLANTILLAS MULTI-BURBUJA",
            f"Total: {len(config.multi_bubble_templates)}",
        ])
        for mb in config.multi_bubble_templates:
            sections.append(f"\n### {mb.template_id} ({mb.intent}, risk={mb.risk}, mode={mb.mode})")
            for j, m in enumerate(mb.messages):
                sections.append(f'  Burbuja {j+1}: "{m}"')

    return "\n".join(sections)
