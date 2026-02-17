"""
Phase 2 — Lead Analyzer (Doc B)

Uses LLM to analyze each lead's conversation individually,
extracting relationship type, creator patterns, lead behavior,
and bot classification.
"""

import asyncio
import logging
from typing import Optional

from core.personality_extraction.conversation_formatter import format_conversation
from core.personality_extraction.llm_client import extract_with_llm
from core.personality_extraction.models import (
    CleanedConversation,
    FormattedConversation,
    LeadAnalysis,
    SuperficialLead,
)

logger = logging.getLogger(__name__)

# Minimum creator real messages to do full analysis
MIN_MESSAGES_FULL_ANALYSIS = 3

# Maximum conversations to send in a single LLM batch
BATCH_SIZE = 10

LEAD_ANALYSIS_SYSTEM_PROMPT = """Eres un analista experto en comportamiento conversacional humano, psicología de ventas y diseño de sistemas conversacionales autónomos.

Tu tarea es analizar conversaciones reales entre un creador de contenido y sus leads/seguidores, y extraer patrones de comunicación con la máxima precisión.

REGLAS:
1. NO INVENTES NADA. Todo debe derivar exclusivamente de los datos reales.
2. Si algo no se puede inferir, escribe "⚠️ Datos insuficientes".
3. CUANTIFICA TODO. "Usa emojis a veces" → MAL. "Emojis en 3/5 mensajes (60%)" → BIEN.
4. Usa frases TEXTUALES del creador como evidencia.
5. Los mensajes marcados [COPILOTO IA — EXCLUIDO] NO son del creador real. Ignóralos en el análisis de patrones.

Para CADA lead, genera el análisis con este formato exacto:

============================================================
LEAD: [Nombre] (@[username])
Mensajes totales: [N] | Creador real: [N] | Lead: [N]
Período: [fecha] → [fecha]
============================================================

1. PERFIL DE LA RELACIÓN
   ├── Tipo: [fría | warm | confianza | amistad | transaccional | B2B | vendor | conflicto]
   ├── Cercanía emocional: [mínima | baja | media | media-alta | alta]
   ├── Dirección de valor: [creador→lead | lead→creador | bidireccional]
   ├── Rol del creador: [amigo | mentor | vendedor | coach | colega | fan | conversacional]
   └── ¿Relación monetizable?: [sí-directo | sí-indirecto | no | potencial]

2. NATURALEZA DE LA CONVERSACIÓN
   ├── Temas principales: [lista]
   ├── Objetivo real: [venta | networking | soporte | amistad | colaboración | nurturing]
   ├── Etapa del funnel: [descubrimiento | interés | consideración | cierre | postventa | nurturing | referral]
   ├── ¿Hubo migración de canal?: [sí-WhatsApp | sí-email | sí-presencial | no]
   └── ¿Hubo transacción?: [sí-confirmada | probable | no]

3. PATRONES DEL CREADOR EN ESTA CONVERSACIÓN
   ├── Tono dominante: [informal/humor | agradecido | directo/breve | inspirador | vendedor | empático | técnico]
   ├── Longitud media de mensajes: [N chars]
   ├── Uso de emojis: [N/N mensajes (N%)]
   ├── Emojis usados: [lista]
   ├── Fragmentación (multi-burbuja): [sí/no — promedio N burbujas por turno]
   │
   ├── TOP 5 FRASES REALES MÁS REPRESENTATIVAS:
   │   → "[frase exacta 1]"
   │   → "[frase exacta 2]"
   │   → "[frase exacta 3]"
   │   → "[frase exacta 4]"
   │   → "[frase exacta 5]"
   │
   └── PATRONES ESPECÍFICOS DE ESTA RELACIÓN:
       [Qué hace el creador de forma DIFERENTE en esta conversación]

4. COMPORTAMIENTO DEL LEAD
   ├── Nivel de engagement: [alto | medio | bajo | unidireccional]
   ├── Tipo de interacción: [conversacional | transaccional | reactivo | proactivo]
   ├── Señales de compra: [lista si existen]
   ├── Señales de fricción: [lista si existen]

5. CLASIFICACIÓN PARA EL BOT
   ├── Status recomendado: [nuevo | interesado | caliente | cliente | colaborador | amigo]
   ├── Score estimado: [0-100]
   ├── Modo de respuesta recomendado: [AUTO | DRAFT | MANUAL]
   └── Riesgo si el bot responde mal: [bajo | medio | alto — por qué]"""


async def analyze_lead_batch(
    conversations: list[FormattedConversation],
    creator_name: str = "",
) -> list[str]:
    """
    Analyze a batch of leads by sending their formatted conversations to the LLM.

    Returns raw analysis text for each lead in the batch.
    """
    # Build the user message with all conversations in the batch
    conv_texts = []
    for conv in conversations:
        conv_texts.append(conv.header)
        conv_texts.append(conv.body)
        conv_texts.append("")

    user_message = (
        f"Analiza las siguientes conversaciones del creador {creator_name}.\n"
        f"Genera el análisis completo para CADA lead.\n\n"
        + "\n".join(conv_texts)
    )

    result = await extract_with_llm(
        system_prompt=LEAD_ANALYSIS_SYSTEM_PROMPT,
        user_message=user_message,
        max_tokens=8192,
        temperature=0.3,
    )
    return [result] if result else []


def _parse_lead_analysis(raw_text: str, conv: FormattedConversation) -> LeadAnalysis:
    """Parse raw LLM analysis text into a LeadAnalysis object."""
    analysis = LeadAnalysis(
        lead_id=conv.lead_id,
        username=conv.username,
        full_name=conv.full_name,
        total_messages=conv.total_messages,
        creator_real_count=conv.creator_real_count,
        lead_count=conv.lead_count,
        period_start=conv.period_start,
        period_end=conv.period_end,
    )

    # Store full raw text for reference
    analysis.relationship_profile = raw_text

    # Extract structured fields using simple pattern matching
    text_lower = raw_text.lower()

    # Extract relation type
    for rt in ["fría", "warm", "confianza", "amistad", "transaccional", "b2b", "vendor", "conflicto"]:
        if rt in text_lower:
            analysis.relation_type = rt
            break

    # Extract recommended mode
    for mode in ["AUTO", "DRAFT", "MANUAL"]:
        if f"modo de respuesta recomendado: {mode.lower()}" in text_lower or f"recomendado: {mode}" in raw_text:
            analysis.recommended_mode = mode
            break

    # Extract risk level
    for risk in ["bajo", "medio", "alto"]:
        if f"riesgo si el bot responde mal: {risk}" in text_lower:
            analysis.risk_level = risk
            break

    # Extract score (look for "Score estimado: NN")
    import re
    score_match = re.search(r"score estimado:\s*(\d+)", text_lower)
    if score_match:
        analysis.estimated_score = int(score_match.group(1))

    return analysis


async def analyze_all_leads(
    conversations: list[CleanedConversation],
    creator_name: str = "",
) -> tuple[list[LeadAnalysis], list[SuperficialLead]]:
    """
    Analyze all leads: full analysis for those with >=3 creator messages,
    superficial classification for the rest.

    Returns (full_analyses, superficial_leads).
    """
    full_convs = []
    superficial = []

    for conv in conversations:
        if conv.creator_real_count >= MIN_MESSAGES_FULL_ANALYSIS:
            full_convs.append(conv)
        else:
            superficial.append(SuperficialLead(
                username=conv.username,
                full_name=conv.full_name,
                message_count=conv.total_messages,
                probable_type="conversacional" if conv.lead_count > 0 else "sin interacción",
                action="monitorear" if conv.lead_count > 2 else "ignorar",
            ))

    logger.info(
        "Lead analysis: %d full + %d superficial",
        len(full_convs), len(superficial),
    )

    # Format conversations for LLM
    formatted_convs = [format_conversation(c) for c in full_convs]

    # Process in batches
    analyses: list[LeadAnalysis] = []
    for i in range(0, len(formatted_convs), BATCH_SIZE):
        batch = formatted_convs[i:i + BATCH_SIZE]
        logger.info("Analyzing lead batch %d-%d of %d", i + 1, i + len(batch), len(formatted_convs))

        raw_results = await analyze_lead_batch(batch, creator_name)

        if raw_results:
            # If single batch result, split by lead headers
            raw_text = raw_results[0]
            # For now, assign the full batch result to each lead
            # TODO: Split result by lead sections for more precise parsing
            for conv in batch:
                analyses.append(_parse_lead_analysis(raw_text, conv))
        else:
            # LLM failed — create empty analyses
            for conv in batch:
                analyses.append(LeadAnalysis(
                    lead_id=conv.lead_id,
                    username=conv.username,
                    full_name=conv.full_name,
                    total_messages=conv.total_messages,
                    creator_real_count=conv.creator_real_count,
                    lead_count=conv.lead_count,
                ))

        # Rate limiting between batches
        if i + BATCH_SIZE < len(formatted_convs):
            await asyncio.sleep(2)

    return analyses, superficial


def generate_doc_b(
    analyses: list[LeadAnalysis],
    superficial: list[SuperficialLead],
) -> str:
    """Generate the complete Doc B text."""
    from datetime import datetime

    sections = [
        "# DOCUMENTO B: ANÁLISIS INDIVIDUAL POR LEAD",
        f"Leads analizados: {len(analyses)} (completos) + {len(superficial)} (superficiales)",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    for analysis in analyses:
        sections.append(f"{'=' * 60}")
        name = analysis.full_name or analysis.username or "Unknown"
        sections.append(f"LEAD: {name} (@{analysis.username})")
        sections.append(
            f"Mensajes totales: {analysis.total_messages} | "
            f"Creador real: {analysis.creator_real_count} | "
            f"Lead: {analysis.lead_count}"
        )
        if analysis.period_start:
            sections.append(f"Período: {analysis.period_start} → {analysis.period_end}")
        sections.append(f"{'=' * 60}")
        sections.append("")
        sections.append(analysis.relationship_profile)
        sections.append("")

    if superficial:
        sections.append(f"\nLEADS SUPERFICIALES (< {MIN_MESSAGES_FULL_ANALYSIS} mensajes del creador real): {len(superficial)}")
        sections.append("─" * 50)
        for lead in superficial:
            name = lead.full_name or lead.username
            sections.append(
                f"  @{lead.username} ({name}) — {lead.message_count} msgs — "
                f"Tipo probable: {lead.probable_type} — Acción: {lead.action}"
            )

    return "\n".join(sections)
