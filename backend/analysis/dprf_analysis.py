"""
Dynamic Persona Refinement Framework (DPRF) — Iteration 1
Based on Yao et al., Oct 2025

Analyzes divergence between bot responses and Iris ground truth,
identifies systematic gaps, generates Doc D rules, and updates the DB.

Usage: export DATABASE_URL=... && python3 analysis/dprf_analysis.py
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

# ── Load baseline ──────────────────────────────────────────────────

BASELINE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "tests", "baseline_v3_final.json"
)

with open(BASELINE_PATH) as f:
    baseline = json.load(f)

conversations = baseline["conversations"]
print(f"Loaded {len(conversations)} conversations from baseline_v3_final.json")
print(f"Overall clone_score: {baseline['results']['overall_clone_score']}")


# ── Gap detection per conversation ─────────────────────────────────

def detect_gaps(bot: str, gt: str, conv: dict) -> list[str]:
    """Detect all divergence gaps between bot response and ground truth."""
    gaps = []
    bot_len = len(bot)
    gt_len = len(gt)

    # 1. LENGTH gap — bot significantly longer than ground truth
    if gt_len > 0 and bot_len > gt_len * 1.8 and bot_len - gt_len > 20:
        gaps.append("longitud")
    # Bot too short when GT is substantial
    elif gt_len > 30 and bot_len < gt_len * 0.3:
        gaps.append("longitud_corta")

    # 2. EMOJI gap — GT has emoji but bot doesn't (or vice versa)
    gt_emoji = bool(re.search(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]', gt))
    bot_emoji = bool(re.search(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]', bot))
    if gt_emoji and not bot_emoji:
        gaps.append("emoji_falta")
    # GT has emoji clusters (😂😂😂) but bot has single emoji
    if gt_emoji:
        gt_cluster = bool(re.search(r'([\U0001F300-\U0001FAFF])\1{1,}', gt))
        bot_cluster = bool(re.search(r'([\U0001F300-\U0001FAFF])\1{1,}', bot))
        if gt_cluster and not bot_cluster and bot_emoji:
            gaps.append("emoji_cluster")

    # 3. LANGUAGE gap — response in wrong language
    ca_markers = [r'\bperò\b', r'\bamb\b', r'\bdoncs\b', r'\btambé\b', r'\bquè\b',
                  r'\bés\b', r'\bfem\b', r'\bpuc\b', r'\bpots\b']
    es_markers = [r'\bpero\b', r'\bgracias\b', r'\bpuedes\b', r'\bbueno\b',
                  r'\bvale\b', r'\bclaro\b', r'\bque\s+tal\b']
    expected_lang = conv.get("language", "ca")
    bot_lower = bot.lower()

    bot_ca = sum(1 for p in ca_markers if re.search(p, bot_lower))
    bot_es = sum(1 for p in es_markers if re.search(p, bot_lower))

    if expected_lang == "ca" and bot_es > bot_ca and bot_es > 0:
        gaps.append("idioma")
    elif expected_lang == "es" and bot_ca > bot_es and bot_ca > 0:
        gaps.append("idioma")

    # 4. QUESTION gap — bot asks questions when GT doesn't
    bot_questions = bot.count("?")
    gt_questions = gt.count("?")
    if bot_questions > gt_questions + 1:
        gaps.append("pregunta")
    elif bot_questions > 0 and gt_questions == 0 and gt_len < 30:
        # GT is a brief reaction, bot asks unnecessary question
        gaps.append("pregunta")

    # 5. VOCABULARY gap — bot uses formal/generic vocabulary
    formal_markers = [
        r"cuéntame más", r"qué te trae", r"en qué puedo",
        r"cómo puedo ayudarte", r"no dudes", r"estoy aquí para",
        r"espero que", r"què et porta",
    ]
    if any(re.search(p, bot_lower) for p in formal_markers):
        gaps.append("vocabulario")

    # 6. CONTENT gap — bot invents information not in context
    # Detect if bot mentions something completely absent from GT
    if conv.get("type") == "lead_caliente":
        # Check for content hallucination (e.g., conv_015 "perrito muerto")
        gt_lower = gt.lower()
        # Bot mentions emotional topics not in GT
        emotional_hallucination = [
            r"perrit[oa]", r"mascota", r"falleci", r"pena", r"perdid[oa]",
            r"lo siento mucho", r"duelo",
        ]
        if any(re.search(p, bot_lower) for p in emotional_hallucination):
            if not any(re.search(p, gt_lower) for p in emotional_hallucination):
                gaps.append("contenido")

    # 7. OVERENGINEERED — bot elaborate response when GT is ultra-brief
    if gt_len <= 15 and bot_len > 50:
        gaps.append("sobreelaborado")

    return gaps


# ── Analyze all conversations ──────────────────────────────────────

all_gaps = []
conv_analysis = []

for conv in conversations:
    bot = conv["bot_response"]
    gt = conv["ground_truth"]
    gaps = detect_gaps(bot, gt, conv)
    all_gaps.extend(gaps)

    conv_analysis.append({
        "id": conv["id"],
        "type": conv["type"],
        "language": conv["language"],
        "clone_score": conv["clone_score"],
        "bot_response": bot,
        "ground_truth": gt,
        "bot_len": len(bot),
        "gt_len": len(gt),
        "gaps": gaps,
    })

# ── Gap frequency ──────────────────────────────────────────────────

gap_counts = Counter(all_gaps)
total_convs = len(conversations)

print("\n=== GAP FREQUENCY ===")
for gap, count in gap_counts.most_common():
    pct = count / total_convs * 100
    print(f"  {gap:25s}: {count:2d}/{total_convs} ({pct:.0f}%)")

# ── Show worst conversations per gap ───────────────────────────────

print("\n=== WORST CONVERSATIONS BY GAP ===")
for gap, _ in gap_counts.most_common(5):
    affected = [c for c in conv_analysis if gap in c["gaps"]]
    affected.sort(key=lambda x: x["clone_score"])
    print(f"\n--- {gap} ({len(affected)} convs) ---")
    for c in affected[:3]:
        print(f"  {c['id']} [{c['type']}] score={c['clone_score']}")
        print(f"    BOT ({c['bot_len']:3d}): {c['bot_response'][:80]}")
        print(f"    GT  ({c['gt_len']:3d}): {c['ground_truth'][:80]}")

# ── Generate rules for top 3 gaps ──────────────────────────────────

top_gaps = [g for g, _ in gap_counts.most_common(3)]
print(f"\n=== TOP 3 GAPS: {top_gaps} ===")

RULE_TEMPLATES = {
    "sobreelaborado": (
        "REGLA DPRF: Cuando el lead dice algo breve (1-2 palabras, confirmación, "
        "reacción), responde IGUAL DE BREVE. Si la respuesta de Iris real sería "
        "'Tranqui' o 'Oka!' — NO escribas una frase de 80 chars. "
        "Ejemplos: 'Vamos'→'Tranqui', 'Oki'→'Dale!', '[sticker]'→'Si claro'"
    ),
    "pregunta": (
        "REGLA DPRF: NO añadas preguntas innecesarias. Si el lead comparte algo "
        "o confirma algo, REACCIONA, no interrogues. 'Que te trae por aquí?' y "
        "'Cuéntame más' están PROHIBIDAS. Reacciones válidas: 'Brutaaal 😂', "
        "'Ostiaaa 🫠', 'Daleee 💪'. Si necesitas preguntar, máximo 1 pregunta."
    ),
    "emoji_falta": (
        "REGLA DPRF: Iris usa emojis en ~30% de sus mensajes. Si la respuesta "
        "NO tiene emoji y es un mensaje casual/reacción/saludo, AÑADE al menos "
        "un emoji. Preferir clusters: 😂😂😂 > 😂, 🩷🩷 > 🩷. "
        "Emojis favoritos: 😂 🩷 🫠 😘 💪 🥰 ❤️ ✌🏽"
    ),
    "emoji_cluster": (
        "REGLA DPRF: Cuando uses emoji, usa CLUSTERS como Iris: "
        "😂😂😂, 🩷🩷🩷, ❤️❤️❤️. Un emoji suelto suena a bot. "
        "Tres emojis seguidos = marca Iris."
    ),
    "longitud": (
        "REGLA DPRF: Respuestas demasiado largas. Target: 10-60 chars. "
        "Si puedes decirlo en 20 chars, hazlo. 'Ya estas flor' > "
        "'Hola Angelina! Siii, claro que si! Te apunto! Cuantos dias quieres venir?'. "
        "Máximo absoluto: 80 chars para texto, 120 para audio responses."
    ),
    "longitud_corta": (
        "REGLA DPRF: Algunas respuestas son demasiado cortas y pierden "
        "el contexto necesario. Si el lead hace una pregunta específica, "
        "responde con contenido relevante, no solo 'Moltbe' o 'De res cuca'."
    ),
    "vocabulario": (
        "REGLA DPRF: Vocabulario de bot detectado. PROHIBIDO: "
        "'Cuéntame más', 'Qué te trae por aquí?', 'En qué puedo ayudarte?', "
        "'Què et porta per aquí?'. Usar en su lugar vocabulario de Iris: "
        "'Que tal?', 'Com va?', 'Que fuerteee!', 'Daleee!'"
    ),
    "idioma": (
        "REGLA DPRF: Responder en el MISMO idioma que el lead. "
        "Si lead escribe en español → español. Si catalán → catalán. "
        "Code-switching está OK si es natural, pero no forzar catalán "
        "cuando el lead escribe en español."
    ),
    "contenido": (
        "REGLA DPRF: NO inventes información que no está en el contexto. "
        "Si no sabes de qué habla el lead, haz una reacción genérica breve "
        "('Que tal? 🩷', 'Daleee! 💪') en vez de inventar historias."
    ),
}

new_rules = []
for gap in top_gaps:
    rule = RULE_TEMPLATES.get(gap, f"REGLA DPRF: Corregir gap '{gap}'")
    new_rules.append({"gap": gap, "count": gap_counts[gap], "rule": rule})
    print(f"\n{gap} ({gap_counts[gap]}/{total_convs}):")
    print(f"  {rule[:200]}")


# ── Save analysis ──────────────────────────────────────────────────

output = {
    "metadata": {
        "framework": "DPRF (Dynamic Persona Refinement)",
        "paper": "Yao et al., Oct 2025",
        "iteration": 1,
        "date": datetime.now(timezone.utc).isoformat(),
        "baseline_version": "v3_final",
        "baseline_score": baseline["results"]["overall_clone_score"],
        "n_conversations": total_convs,
    },
    "gap_frequency": {g: {"count": c, "pct": round(c / total_convs * 100, 1)}
                      for g, c in gap_counts.most_common()},
    "rules_generated": new_rules,
    "conversation_analysis": conv_analysis,
}

output_path = os.path.join(os.path.dirname(__file__), "dprf_iteration_1.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nAnalysis saved to: {output_path}")


# ── Update Doc D in DB ─────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("\nNo DATABASE_URL — skipping Doc D update. Set it to update DB.")
    sys.exit(0)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if "sslmode" not in DATABASE_URL:
    DATABASE_URL += ("&" if "?" in DATABASE_URL else "?") + "sslmode=require"

from sqlalchemy import create_engine, text
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 30})

# Read current Doc D
with engine.connect() as conn:
    row = conn.execute(text("""
        SELECT pd.content, pd.creator_id
        FROM personality_docs pd
        JOIN creators c ON c.id::text = pd.creator_id
        WHERE c.name = 'iris_bertran' AND pd.doc_type = 'doc_d'
        LIMIT 1
    """)).fetchone()

if not row:
    print("ERROR: No Doc D found for iris_bertran")
    sys.exit(1)

current_doc_d = row.content
creator_id_db = row.creator_id
print(f"\nCurrent Doc D: {len(current_doc_d)} chars")

# Build DPRF rules block
rules_block = "\n## REGLAS DPRF (Auto-generadas — Iteración 1)\n"
rules_block += f"# Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | "
rules_block += f"Baseline: {baseline['results']['overall_clone_score']:.1f}\n"
for r in new_rules:
    rules_block += f"\n{r['rule']}\n"

# Check if DPRF rules already exist
if "REGLAS DPRF" in current_doc_d:
    # Replace existing DPRF block
    updated = re.sub(
        r'## REGLAS DPRF.*?(?=\n## |\Z)',
        rules_block.strip() + "\n\n",
        current_doc_d,
        flags=re.DOTALL,
    )
    print("Replaced existing DPRF rules block")
else:
    # Insert after REGLAS CRITICAS section
    insert_point = current_doc_d.find("\n---\n")
    if insert_point > 0:
        # Insert after first --- separator (after REGLAS CRITICAS)
        updated = current_doc_d[:insert_point] + "\n" + rules_block + current_doc_d[insert_point:]
    else:
        # Append at end
        updated = current_doc_d + "\n" + rules_block
    print("Inserted DPRF rules after REGLAS CRITICAS")

print(f"Updated Doc D: {len(updated)} chars (+{len(updated) - len(current_doc_d)} chars)")

# Write to DB
with engine.connect() as conn:
    conn.execute(text("""
        UPDATE personality_docs
        SET content = :content, updated_at = now()
        WHERE creator_id = :creator_id AND doc_type = 'doc_d'
    """), {"content": updated, "creator_id": creator_id_db})
    conn.commit()

print("Doc D updated in DB ✓")

# Invalidate personality cache
try:
    from core.personality_loader import invalidate_cache
    invalidate_cache("iris_bertran")
    print("Personality cache invalidated ✓")
except Exception:
    print("Cache invalidation skipped (not in app context)")

print("\n=== DPRF ITERATION 1 COMPLETE ===")
print(f"Gaps found: {dict(gap_counts.most_common())}")
print(f"Rules added: {len(new_rules)}")
print(f"Next: Re-measure with LLM-judge to verify improvement")
