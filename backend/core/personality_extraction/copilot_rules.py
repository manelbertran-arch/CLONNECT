"""
Phase 5 — Copilot Rules Generator (Doc E)

Generates the decision tree for AUTO / DRAFT / MANUAL routing,
intent detection keywords, and quality rules.
"""

import logging
from datetime import datetime
from typing import Optional

from core.personality_extraction.llm_client import extract_with_llm
from core.personality_extraction.models import (
    CopilotRules,
    PersonalityProfile,
)

logger = logging.getLogger(__name__)

COPILOT_RULES_SYSTEM_PROMPT = """Eres un experto en diseño de sistemas de copiloto conversacional para bots de IA.

Tu tarea: dado el Personality Profile de un creador, generar las reglas del copiloto que determinan cuándo el bot puede responder solo (AUTO), cuándo necesita aprobación (DRAFT), y cuándo debe escalar al humano (MANUAL).

Genera el documento con estas secciones exactas:

## 5.1 EVALUACIÓN GLOBAL

```
¿El creador es altamente predecible? → [SÍ/NO] — Evidencia: [...]
¿Su estilo es sistematizable? → [SÍ/NO] — Evidencia: [...]
¿Un bot puede replicarlo? → [0-100%] — Desglose por tipo de interacción

DECISIÓN: [AUTOPILOT | COPILOT | HYBRID]
JUSTIFICACIÓN: [basada en datos]
```

## 5.2 ÁRBOL DE DECISIÓN

```
MENSAJE ENTRANTE
       │
  [0. ¿Loop bot-to-bot?] → SÍ → BLOQUEAR
       │ NO
  [1. ¿Voice message?] → SÍ → MANUAL
       │ NO
  [2. ¿Bot sospechoso?] → SÍ → PAUSAR
       │ NO
  [3. Clasificar intent]
       │
  STORY REACT → AUTO
  SALUDO SIMPLE → [AUTO o DRAFT según datos]
  PREGUNTA SIMPLE → DRAFT
  PROPUESTA B2B → MANUAL
  EMOCIONAL PROFUNDO → MANUAL
  LOGÍSTICA COMPLEJA → MANUAL
  PRECIO/COMPRA → [según datos]
  DEFAULT → DRAFT
```

## 5.3 DISTRIBUCIÓN ESTIMADA

| Modo   | % estimado | Confianza target |
|--------|-----------|-----------------|
| AUTO   | [N%]      | > 90%           |
| DRAFT  | [N%]      | > 80%           |
| MANUAL | [N%]      | N/A             |

## 5.4 INTENT DETECTION KEYWORDS

```python
INTENT_KEYWORDS = {
    "collaboration": [...],
    "coordination": [...],
    "emotional": [...],
    "channel_switch": [...],
    "post_purchase": [...],
    "scheduling": [...],
    "pricing": [...],
    # + intents detectados en los datos
}
```

## 5.5 REGLAS DE CALIDAD (para el 80-90%)

Lista de condiciones que DEBEN cumplirse para que una respuesta AUTO sea enviada:
- [regla 1]
- [regla 2]
- ...

REGLAS:
- Basa tus decisiones en los datos del perfil, no en suposiciones genéricas.
- Si el creador tiene un estilo muy variable, recomienda más DRAFT.
- Si el creador tiene un estilo muy consistente, permite más AUTO.
- Los escenarios de alto riesgo (venta, emocional, B2B) siempre deben ser DRAFT o MANUAL."""


async def generate_copilot_rules(
    profile: PersonalityProfile,
    bot_config_summary: str = "",
) -> CopilotRules:
    """Generate copilot rules from the personality profile."""
    rules = CopilotRules()

    ws = profile.writing_style

    user_message = (
        f"CREADOR: {profile.creator_name}\n"
        f"DATOS: {profile.messages_analyzed} mensajes / {profile.leads_analyzed} leads / {profile.months_covered} meses\n"
        f"CONFIANZA: {profile.confidence}\n\n"
        f"ESTADÍSTICAS CLAVE:\n"
        f"- Longitud media: {ws.avg_message_length} chars\n"
        f"- % mensajes cortos (<30 chars): {ws.short_msgs_pct}%\n"
        f"- Emojis en {ws.emoji_pct}% de mensajes\n"
        f"- Fragmentación: {ws.avg_bubbles_per_turn} burbujas/turno\n"
        f"- Idioma: {ws.primary_language} ({ws.dialect})\n\n"
        f"PERFIL COMPLETO:\n{profile.raw_profile_text[:15000]}\n\n"
    )

    if bot_config_summary:
        user_message += f"CONFIGURACIÓN DEL BOT:\n{bot_config_summary[:5000]}\n"

    result = await extract_with_llm(
        system_prompt=COPILOT_RULES_SYSTEM_PROMPT,
        user_message=user_message,
        max_tokens=8192,
        temperature=0.3,
    )

    if result:
        rules.raw_rules_text = result
        _parse_copilot_rules(rules, result)

    return rules


def _parse_copilot_rules(rules: CopilotRules, text: str) -> None:
    """Parse structured fields from LLM copilot rules text."""
    import re

    text_lower = text.lower()

    # Extract global mode
    for mode in ["AUTOPILOT", "COPILOT", "HYBRID"]:
        if f"decisión: {mode.lower()}" in text_lower or f"decisión: {mode}" in text:
            rules.global_mode = mode
            break

    # Extract distribution percentages
    for mode_label, attr in [("auto", "auto_pct"), ("draft", "draft_pct"), ("manual", "manual_pct")]:
        match = re.search(rf"\|\s*{mode_label}\s*\|\s*(\d+)%?\s*\|", text_lower)
        if match:
            setattr(rules, attr, float(match.group(1)))

    # Extract replicability score
    match = re.search(r"replicarlo\?\s*→?\s*(\d+)[-%]", text_lower)
    if match:
        rules.replicability_pct = float(match.group(1))

    # Extract quality rules
    rules_section = False
    for line in text.split("\n"):
        stripped = line.strip()
        if "reglas de calidad" in stripped.lower():
            rules_section = True
            continue
        if rules_section and stripped.startswith("-"):
            rules.quality_rules.append(stripped.lstrip("- "))
        elif rules_section and stripped.startswith("#"):
            rules_section = False


def generate_doc_e(rules: CopilotRules) -> str:
    """Generate the complete Doc E text."""
    sections = [
        "# DOCUMENTO E: COPILOT RULES (AUTO / DRAFT / MANUAL)",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Modo global: {rules.global_mode}",
        "",
        f"Distribución estimada: AUTO={rules.auto_pct}% / DRAFT={rules.draft_pct}% / MANUAL={rules.manual_pct}%",
        f"Replicabilidad: {rules.replicability_pct}%",
        "",
        "## ANÁLISIS COMPLETO",
        "",
        rules.raw_rules_text or "⚠️ LLM analysis not available",
    ]

    if rules.quality_rules:
        sections.extend([
            "",
            "## REGLAS DE CALIDAD (resumen)",
        ])
        for rule in rules.quality_rules:
            sections.append(f"  - {rule}")

    return "\n".join(sections)
