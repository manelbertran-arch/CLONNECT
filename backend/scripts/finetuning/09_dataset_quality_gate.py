#!/usr/bin/env python3
"""
Sprint 7 Dataset Quality Gate
Verifica criterios PASS/FAIL sobre un .jsonl antes de lanzar training.

Uso:
    python3 scripts/finetuning/09_dataset_quality_gate.py \\
        --input data/dpo/trl/sft_sprint7.jsonl \\
        [--eval-set data/eval/ccee_questions.jsonl] \\
        [--report-out docs/finetuning_sprint_iris/presprint7/gate_report.md]

Output:
    - Reporte en stdout
    - Fichero markdown si se pasa --report-out
    - Exit code 0 = PASS / PASS_WITH_WARNINGS
    - Exit code 1 = FAIL (al menos un BLOCKER falla)
"""

import json
import re
import hashlib
import argparse
import sys
import math
import random
from pathlib import Path
from collections import Counter
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# PATRONES Y CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

ERROR_STRINGS = [
    "lo siento, hubo un error",
    "sorry, i",
    "sorry i couldn",
    "error occurred",
    "traceback",
    "exception:",
    "hubuntoo un error",
    "se produjo un error",
]

ARTIFACT_ONLY_PATTERNS = [
    r"^\s*\[sticker\]\s*$",
    r"^\s*\[photo\]\s*$",
    r"^\s*\[audio\]\s*$",
    r"^\s*\[video\]\s*$",
    r"^\s*\[contact\]\s*$",
    r"^\s*\[🎤[^\]]*\]\s*$",
    r"^\s*\[🎬[^\]]*\]\s*$",
    r"^\s*sent an attachment\s*$",
]

ARTIFACT_IN_CONTENT = re.compile(
    r"\[sticker\]|\[photo\]|\[audio\]|\[video\]|\[contact\]|\[🎤|\[🎬|Sent an attachment",
    re.IGNORECASE,
)

PII_PHONE = re.compile(r"\b[67]\d{8}\b|\+34\s*\d{9}|\b\d{10,11}\b")
PII_EMAIL = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w{2,}")
PII_HANDLE = re.compile(r"@[a-zA-Z0-9_.]{3,}")

PERSONA_QA_KEYWORDS = [
    # Catalan
    "qui ets", "quants anys tens", "d'on ets", "on vius", "t'agrada", "que fas",
    "treballes", "estudies", "família", "parella", "tens fills", "que t'agrada",
    "quin és el teu", "com et dius", "el teu nom", "la teva feina",
    "els teus valors", "la teva passió", "el teu somni",
    # Spanish
    "quién eres", "cuántos años", "de dónde eres", "dónde vives", "te gusta",
    "qué haces", "trabajas", "estudias", "familia", "pareja", "tienes hijos",
    "cuál es tu", "cómo te llamas", "tu nombre", "tu trabajo",
    "tus valores", "tu pasión", "tu sueño",
    # English (fallback)
    "who are you", "how old are you", "where are you from", "do you like",
    "what do you do", "do you work", "do you study", "your family",
    "your partner", "your name", "your job", "your values",
]

ADVERSARIAL_KEYWORDS = [
    # Challenging authenticity
    "ets un bot", "ets una ia", "ets un robot", "ets real", "ets una persona",
    "eres un bot", "eres una ia", "eres un robot", "eres real", "eres una persona",
    "are you a bot", "are you ai", "are you real",
    # Price challenge
    "és molt car", "és massa car", "no val tant", "massa diners",
    "es muy caro", "demasiado caro", "no vale tanto",
    "too expensive", "not worth",
    # Provocation
    "no et crec", "no me lo creo", "mentides", "mentiras", "bullshit",
    "fake", "fals", "falso", "estàs mentint", "estás mintiendo",
]

PERSONA_CATEGORIES = {
    "identitat": ["nom", "name", "qui ets", "quién eres", "edat", "edad", "anys", "años"],
    "idioma": ["català", "catalán", "espanyol", "español", "llengua", "idioma", "parles", "hablas"],
    "feina": ["feina", "trabajo", "treballes", "trabajas", "coach", "creadora", "creator", "professió", "profesión"],
    "valors": ["valors", "valores", "passió", "pasión", "creu", "cree", "opina", "importa"],
    "historia": ["d'on", "de dónde", "vius", "vives", "família", "familia", "passat", "pasado"],
    "relacions": ["parella", "pareja", "amics", "amigos", "seguidors", "seguidores", "comunitat", "comunidad"],
}

VALID_ROLES = {"system", "user", "assistant"}
TOKENS_PER_CHAR = 1 / 3.5  # approx for Catalan/Spanish


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def is_multi_turn(msgs: list) -> bool:
    """True si hay al menos 2 pares user/assistant (excluido system)."""
    turns = [m for m in msgs if m.get("role") in ("user", "assistant")]
    return len(turns) >= 4  # 2 user + 2 assistant


def get_assistant_content(msgs: list) -> str:
    parts = [m.get("content", "") for m in msgs if m.get("role") == "assistant"]
    return " ".join(parts)


def get_user_content(msgs: list) -> str:
    parts = [m.get("content", "") for m in msgs if m.get("role") == "user"]
    return " ".join(parts)


def is_persona_qa(msgs: list) -> bool:
    user = get_user_content(msgs).lower()
    return any(kw in user for kw in PERSONA_QA_KEYWORDS)


def is_adversarial(msgs: list) -> bool:
    user = get_user_content(msgs).lower()
    return any(kw in user for kw in ADVERSARIAL_KEYWORDS)


def has_error_string(content: str) -> bool:
    low = content.lower()
    return any(e in low for e in ERROR_STRINGS)


def is_artifact_only(content: str) -> bool:
    return any(re.match(p, content, re.IGNORECASE) for p in ARTIFACT_ONLY_PATTERNS)


def has_artifact(content: str) -> bool:
    return bool(ARTIFACT_IN_CONTENT.search(content))


def has_pii(content: str, handle_whitelist: set | None = None) -> bool:
    if PII_PHONE.search(content) or PII_EMAIL.search(content):
        return True
    # Instagram handle: flag if @handle not in whitelist
    for m in PII_HANDLE.finditer(content):
        handle = m.group(0).lower()
        if handle_whitelist is None or handle not in handle_whitelist:
            return True
    return False


def detect_language(text: str) -> str:
    """Heuristic: catalán/español/other."""
    ca_markers = ["però", "també", "perquè", "molt", "estar", "gràcies", "ara", "quan", "com", "que"]
    es_markers = ["pero", "también", "porque", "muy", "estar", "gracias", "ahora", "cuando", "cómo", "qué"]
    text_l = text.lower()
    ca = sum(1 for w in ca_markers if w in text_l)
    es = sum(1 for w in es_markers if w in text_l)
    if ca > es and ca >= 2:
        return "ca"
    if es > ca and es >= 2:
        return "es"
    return "other"


def estimate_tokens(msgs: list) -> int:
    total_chars = sum(len(m.get("content", "")) for m in msgs)
    return int(total_chars * TOKENS_PER_CHAR)


def compute_distinct(texts: list, n: int) -> float:
    """Distinct-n: unique n-grams / total n-grams."""
    all_ngrams: list = []
    unique_ngrams: set = set()
    for text in texts:
        words = text.lower().split()
        ngrams = [tuple(words[i:i+n]) for i in range(len(words)-n+1)]
        all_ngrams.extend(ngrams)
        unique_ngrams.update(ngrams)
    if not all_ngrams:
        return 0.0
    return len(unique_ngrams) / len(all_ngrams)


def bleu_n(reference_tokens: list, hypothesis_tokens: list, n: int) -> float:
    """Sentence-level BLEU-n (clipped count)."""
    if len(hypothesis_tokens) < n:
        return 0.0
    hyp_ngrams = Counter(tuple(hypothesis_tokens[i:i+n]) for i in range(len(hypothesis_tokens)-n+1))
    ref_ngrams = Counter(tuple(reference_tokens[i:i+n]) for i in range(len(reference_tokens)-n+1))
    matches = sum(min(hyp_ngrams[ng], ref_ngrams[ng]) for ng in hyp_ngrams)
    total = sum(hyp_ngrams.values())
    return matches / total if total > 0 else 0.0


def self_bleu_4(texts: list, sample_size: int = 500) -> float:
    """Self-BLEU-4 over a sample. Lower = more diverse."""
    if len(texts) < 10:
        return 0.0
    sample = random.sample(texts, min(sample_size, len(texts)))
    tokenized = [t.lower().split() for t in sample]
    scores = []
    for i, hyp in enumerate(tokenized):
        refs = tokenized[:i] + tokenized[i+1:]
        if not refs:
            continue
        # Sample 20 references max for speed
        ref_sample = random.sample(refs, min(20, len(refs)))
        bleu_scores = [bleu_n(ref, hyp, 4) for ref in ref_sample]
        scores.append(sum(bleu_scores) / len(bleu_scores))
    return sum(scores) / len(scores) if scores else 0.0


def check_role_alternation(msgs: list) -> bool:
    """Check user/assistant alternate (system allowed at start only)."""
    non_sys = [m for m in msgs if m.get("role") != "system"]
    if not non_sys:
        return False
    expected = "user"
    for m in non_sys:
        role = m.get("role")
        if role != expected:
            return False
        expected = "assistant" if expected == "user" else "user"
    return True


def persona_categories_covered(records: list) -> int:
    """Count how many of 6 persona categories appear in Q&A records."""
    qa_records = [r for r in records if is_persona_qa(r.get("messages", []))]
    all_user_text = " ".join(get_user_content(r.get("messages", [])).lower() for r in qa_records)
    covered = 0
    for cat, keywords in PERSONA_CATEGORIES.items():
        if any(kw in all_user_text for kw in keywords):
            covered += 1
    return covered


def coherence_heuristic(msgs: list) -> bool:
    """
    Rough coherence check: if user has >=1 word of >=4 chars,
    at least one such word appears in assistant response OR
    assistant response is >=20 chars (substantive reply).
    """
    user = get_user_content(msgs).lower()
    asst = get_assistant_content(msgs).lower()
    long_words = [w for w in re.split(r"\W+", user) if len(w) >= 4]
    if not long_words:
        return True  # too short to evaluate
    if len(asst) >= 20:
        return True
    return any(w in asst for w in long_words)


# ─────────────────────────────────────────────────────────────────────────────
# GATE RUNNER
# ─────────────────────────────────────────────────────────────────────────────

class GateResult:
    def __init__(self, gate_id: str, label: str, severity: str, value, threshold, passed: bool, note: str = ""):
        self.gate_id = gate_id
        self.label = label
        self.severity = severity  # BLOCKER or WARNING
        self.value = value
        self.threshold = threshold
        self.passed = passed
        self.note = note

    def status_icon(self) -> str:
        return "✅ PASS" if self.passed else ("❌ FAIL" if self.severity == "BLOCKER" else "⚠️  WARN")

    def fmt_value(self) -> str:
        if isinstance(self.value, float):
            if self.value <= 1.0:
                return f"{self.value:.1%}"
            return f"{self.value:.2f}"
        return str(self.value)

    def fmt_threshold(self) -> str:
        if isinstance(self.threshold, float):
            if self.threshold <= 1.0:
                return f"{self.threshold:.0%}"
            return f"{self.threshold:.2f}"
        return str(self.threshold)


def run_gate(input_path: Path, eval_set_path: Optional[Path] = None, verbose: bool = True, pii_whitelist: set | None = None) -> tuple[list[GateResult], dict]:
    results: list[GateResult] = []

    # ── Load records ──────────────────────────────────────────────────────────
    records = []
    parse_errors = 0
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                parse_errors += 1

    N = len(records)
    stats = {
        "n_records": N,
        "parse_errors": parse_errors,
        "input": str(input_path),
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f" SPRINT 7 DATASET QUALITY GATE")
        print(f"{'='*60}")
        print(f" Input:  {input_path}")
        print(f" Records: {N:,}  (parse errors: {parse_errors})")
        print()

    # ── GATE 7: Format compliance (first — needed for all other gates) ────────
    if verbose:
        print("GATE 7 — Format compliance")

    n_valid_messages = sum(1 for r in records if isinstance(r.get("messages"), list) and len(r.get("messages", [])) > 0)
    n_alternation_ok = sum(1 for r in records if check_role_alternation(r.get("messages", [])))
    n_has_user_asst = sum(1 for r in records if
        any(m.get("role") == "user" for m in r.get("messages", [])) and
        any(m.get("role") == "assistant" for m in r.get("messages", [])))
    n_valid_roles = sum(1 for r in records if
        all(m.get("role") in VALID_ROLES for m in r.get("messages", [])))
    n_has_system = sum(1 for r in records if
        any(m.get("role") == "system" for m in r.get("messages", [])))
    n_no_empty = sum(1 for r in records if
        all(m.get("content", "").strip() for m in r.get("messages", [])))

    def pct(n): return n / N if N > 0 else 0.0

    results += [
        GateResult("G7.1", "messages array válido", "BLOCKER", pct(n_valid_messages), 1.0, pct(n_valid_messages) == 1.0),
        GateResult("G7.2", "role alternation correcto", "BLOCKER", pct(n_alternation_ok), 1.0, pct(n_alternation_ok) == 1.0),
        GateResult("G7.3", "tiene user + assistant", "BLOCKER", pct(n_has_user_asst), 1.0, pct(n_has_user_asst) == 1.0),
        GateResult("G7.4", "roles válidos", "BLOCKER", pct(n_valid_roles), 1.0, pct(n_valid_roles) == 1.0),
        GateResult("G7.5", "system prompt presente", "WARNING", pct(n_has_system), 0.95, pct(n_has_system) >= 0.95),
        GateResult("G7.6", "no empty content", "BLOCKER", pct(n_no_empty), 1.0, pct(n_no_empty) == 1.0),
    ]

    if verbose:
        for r in results[-6:]:
            print(f"  {r.gate_id} {r.label:<40} {r.fmt_value():>8}   {r.status_icon()}")

    # Only continue detailed analysis on format-valid records
    valid_records = [r for r in records if
        isinstance(r.get("messages"), list) and
        any(m.get("role") == "user" for m in r.get("messages", [])) and
        any(m.get("role") == "assistant" for m in r.get("messages", []))]
    Nv = len(valid_records)

    def vpct(n): return n / Nv if Nv > 0 else 0.0

    # ── GATE 1: Composición ───────────────────────────────────────────────────
    if verbose:
        print("\nGATE 1 — Composición")

    n_multiturn = sum(1 for r in valid_records if is_multi_turn(r["messages"]))
    n_persona_qa = sum(1 for r in valid_records if is_persona_qa(r["messages"]))
    n_adversarial = sum(1 for r in valid_records if is_adversarial(r["messages"]))
    n_single_turn_social = Nv - n_multiturn - n_persona_qa - n_adversarial

    # G1.2: pass if absolute count >=750 OR ratio >=7.5% (Session 2: absolute is the design param)
    g12_pass = n_persona_qa >= 750 or vpct(n_persona_qa) >= 0.075
    g12_display = f"{n_persona_qa} ({vpct(n_persona_qa):.1%})"
    # G1.3: pass if absolute count >=200 OR ratio >=2% (Session 3: 200 examples sufficient v1)
    g13_pass = n_adversarial >= 200 or vpct(n_adversarial) >= 0.02
    g13_display = f"{n_adversarial} ({vpct(n_adversarial):.1%})"

    results += [
        GateResult("G1.1", "multi-turn ≥15%", "BLOCKER", vpct(n_multiturn), 0.15, vpct(n_multiturn) >= 0.15),
        GateResult("G1.2", "persona Q&A ≥750 OR ≥7.5%", "BLOCKER", g12_display, "≥750 OR ≥7.5%", g12_pass),
        GateResult("G1.3", "adversarial ≥200 OR ≥2% (WARNING v1)", "WARNING", g13_display, "≥200 OR ≥2%", g13_pass),
        GateResult("G1.4", "DM single-turn ≤75%", "WARNING", vpct(n_single_turn_social), 0.75, vpct(n_single_turn_social) <= 0.75),
    ]

    if verbose:
        for r in results[-4:]:
            vfmt = r.value if isinstance(r.value, str) else r.fmt_value()
            print(f"  {r.gate_id} {r.label:<44} {vfmt:>14}   {r.status_icon()}")

    stats.update({
        "n_multiturn": n_multiturn,
        "n_persona_qa": n_persona_qa,
        "n_adversarial": n_adversarial,
    })

    # ── GATE 2: Calidad ───────────────────────────────────────────────────────
    if verbose:
        print("\nGATE 2 — Calidad")

    n_error_strings = 0
    n_artifact_only = 0
    n_has_artifact = 0
    n_short_unjustified = 0
    assistant_hashes: Counter = Counter()

    for r in valid_records:
        msgs = r["messages"]
        asst_content = get_assistant_content(msgs)

        if has_error_string(asst_content):
            n_error_strings += 1
        if is_artifact_only(asst_content):
            n_artifact_only += 1
        if has_artifact(asst_content):
            n_has_artifact += 1
        if len(asst_content.strip()) < 10:
            n_short_unjustified += 1

        h = md5(asst_content)
        assistant_hashes[h] += 1

    n_duplicates = sum(c - 1 for c in assistant_hashes.values() if c > 1)
    dup_rate = n_duplicates / Nv if Nv > 0 else 0.0
    artifact_rate = n_has_artifact / Nv if Nv > 0 else 0.0
    short_rate = n_short_unjustified / Nv if Nv > 0 else 0.0

    results += [
        GateResult("G2.1", "error strings = 0", "BLOCKER", n_error_strings, 0, n_error_strings == 0),
        GateResult("G2.2", "solo-artifact = 0", "BLOCKER", n_artifact_only, 0, n_artifact_only == 0),
        GateResult("G2.3", "artifacts explícitos <2%", "BLOCKER", artifact_rate, 0.02, artifact_rate < 0.02),
        GateResult("G2.4", "duplicados exactos <5%", "WARNING", dup_rate, 0.05, dup_rate < 0.05),
        GateResult("G2.5", "respuestas <10chars <5%", "WARNING", short_rate, 0.05, short_rate < 0.05),
    ]

    if verbose:
        for r in results[-5:]:
            print(f"  {r.gate_id} {r.label:<40} {r.fmt_value():>8}   {r.status_icon()}")

    stats["n_error_strings"] = n_error_strings
    stats["n_artifact_only"] = n_artifact_only
    stats["artifact_rate"] = artifact_rate

    # ── GATE 3: Diversidad ────────────────────────────────────────────────────
    if verbose:
        print("\nGATE 3 — Diversidad léxica")

    assistant_texts = [get_assistant_content(r["messages"]) for r in valid_records]
    d1 = compute_distinct(assistant_texts, 1)
    d2 = compute_distinct(assistant_texts, 2)
    sb4 = self_bleu_4(assistant_texts, sample_size=500)

    results += [
        GateResult("G3.1", "Distinct-1 ≥0.20", "WARNING", d1, 0.20, d1 >= 0.20),
        GateResult("G3.2", "Distinct-2 ≥0.40", "WARNING", d2, 0.40, d2 >= 0.40),
        GateResult("G3.3", "Self-BLEU-4 ≤0.65", "WARNING", sb4, 0.65, sb4 <= 0.65),
    ]

    if verbose:
        for r in results[-3:]:
            print(f"  {r.gate_id} {r.label:<40} {r.fmt_value():>8}   {r.status_icon()}")

    stats.update({"distinct_1": d1, "distinct_2": d2, "self_bleu_4": sb4})

    # ── GATE 4: Cobertura semántica ───────────────────────────────────────────
    if verbose:
        print("\nGATE 4 — Cobertura semántica")

    cats_covered = persona_categories_covered(valid_records)
    lang_counts = Counter(detect_language(get_assistant_content(r["messages"])) for r in valid_records)
    lang_ca_es_pct = (lang_counts.get("ca", 0) + lang_counts.get("es", 0)) / Nv if Nv > 0 else 0.0

    results += [
        GateResult("G4.1", "categorías persona ≥5/6", "WARNING", f"{cats_covered}/6", "≥5/6", cats_covered >= 5),
        GateResult("G4.2", "idioma ca+es ≥35%", "WARNING", lang_ca_es_pct, 0.35, lang_ca_es_pct >= 0.35),
    ]

    if verbose:
        for r in results[-2:]:
            vfmt = r.value if isinstance(r.value, str) else f"{r.value:.1%}"
            print(f"  {r.gate_id} {r.label:<40} {vfmt:>8}   {r.status_icon()}")

    stats.update({
        "persona_categories_covered": cats_covered,
        "lang_ca": lang_counts.get("ca", 0),
        "lang_es": lang_counts.get("es", 0),
        "lang_other": lang_counts.get("other", 0),
    })

    # ── GATE 5: Coherencia ────────────────────────────────────────────────────
    if verbose:
        print("\nGATE 5 — Coherencia user→assistant (heurística)")

    n_coherent = sum(1 for r in valid_records if coherence_heuristic(r["messages"]))
    coherence_rate = vpct(n_coherent)

    results.append(
        GateResult("G5.1", "coherencia ≥85% (heurística)", "WARNING", coherence_rate, 0.85, coherence_rate >= 0.85,
                   note="Heurística rápida. Ejecutar LLM judge para validación completa.")
    )

    if verbose:
        r = results[-1]
        print(f"  {r.gate_id} {r.label:<40} {r.fmt_value():>8}   {r.status_icon()}")
        if r.note:
            print(f"         ↳ {r.note}")

    # ── GATE 6: Contaminación ─────────────────────────────────────────────────
    if verbose:
        print("\nGATE 6 — Sin contaminación")

    # PII
    n_pii = sum(1 for r in valid_records if has_pii(get_assistant_content(r["messages"]), handle_whitelist=pii_whitelist))
    results.append(GateResult("G6.2", "PII en assistant = 0", "BLOCKER", n_pii, 0, n_pii == 0))

    if verbose:
        r = results[-1]
        print(f"  {r.gate_id} {r.label:<40} {r.fmt_value():>8}   {r.status_icon()}")

    # CCEE eval set overlap
    if eval_set_path and eval_set_path.exists():
        eval_hashes: set = set()
        with open(eval_set_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    # Support various eval formats
                    user_text = (
                        obj.get("user") or
                        obj.get("question") or
                        obj.get("prompt") or
                        next((m["content"] for m in obj.get("messages", []) if m.get("role") == "user"), None) or
                        ""
                    )
                    if user_text:
                        eval_hashes.add(md5(user_text))
                except json.JSONDecodeError:
                    pass

        n_overlap = sum(1 for r in valid_records if
            md5(get_user_content(r["messages"])) in eval_hashes)
        results.append(GateResult("G6.1", "overlap CCEE eval = 0", "BLOCKER", n_overlap, 0, n_overlap == 0))

        if verbose:
            r = results[-1]
            print(f"  {r.gate_id} {r.label:<40} {r.fmt_value():>8}   {r.status_icon()}")
        stats["ccee_overlap"] = n_overlap
    else:
        if verbose:
            print(f"  G6.1 overlap CCEE eval = 0            SKIPPED (no --eval-set)")
        stats["ccee_overlap"] = "skipped"

    # ── GATE 8: Tamaño ────────────────────────────────────────────────────────
    if verbose:
        print("\nGATE 8 — Tamaño y tokens")

    token_counts = sorted(estimate_tokens(r["messages"]) for r in valid_records)
    p99_tokens = token_counts[int(0.99 * len(token_counts))] if token_counts else 0
    n_over_1500 = sum(1 for t in token_counts if t > 1500)

    results += [
        GateResult("G8.1", "N mínimo ≥2,000", "BLOCKER", Nv, 2000, Nv >= 2000),
        GateResult("G8.2", "N máximo ≤30,000", "WARNING", Nv, 30000, Nv <= 30000),
        GateResult("G8.3", f"P99 tokens ≤2,048 (est: {p99_tokens})", "WARNING", p99_tokens, 2048, p99_tokens <= 2048),
        GateResult("G8.4", "records >1500 tokens <10%", "WARNING", vpct(n_over_1500), 0.10, vpct(n_over_1500) < 0.10),
    ]

    if verbose:
        for r in results[-4:]:
            vfmt = r.fmt_value() if not isinstance(r.value, str) else r.value
            if isinstance(r.value, int) and r.value > 100:
                vfmt = f"{r.value:,}"
            print(f"  {r.gate_id} {r.label:<40} {vfmt:>8}   {r.status_icon()}")

    stats.update({"p99_tokens": p99_tokens, "n_over_1500_tokens": n_over_1500})

    return results, stats


def decide(results: list[GateResult]) -> str:
    """Returns PASS, PASS_WITH_WARNINGS, PASS_DEGRADED, or FAIL."""
    blockers_failed = [r for r in results if r.severity == "BLOCKER" and not r.passed]
    warnings_failed = [r for r in results if r.severity == "WARNING" and not r.passed]

    if blockers_failed:
        return "FAIL"
    if not warnings_failed:
        return "PASS"
    if len(warnings_failed) <= 3:
        return "PASS_WITH_WARNINGS"
    return "PASS_DEGRADED"


def build_report(results: list[GateResult], stats: dict, verdict: str) -> str:
    """Build a markdown report string."""
    from datetime import datetime

    lines = [
        f"# Dataset Quality Gate Report",
        f"",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Input:** `{stats['input']}`  ",
        f"**Records:** {stats['n_records']:,}  ",
        f"**Verdict:** {'✅ PASS' if verdict == 'PASS' else '⚠️ ' + verdict if 'PASS' in verdict else '❌ ' + verdict}",
        f"",
        f"---",
        f"",
        f"## Gate Results",
        f"",
        f"| Gate | Criterio | Valor | Threshold | Severidad | Estado |",
        f"|---|---|---|---|---|---|",
    ]

    for r in results:
        vfmt = r.fmt_value() if not isinstance(r.value, str) else r.value
        icon = "✅" if r.passed else ("❌" if r.severity == "BLOCKER" else "⚠️")
        lines.append(f"| {r.gate_id} | {r.label} | {vfmt} | {r.fmt_threshold()} | {r.severity} | {icon} |")

    blockers = [r for r in results if r.severity == "BLOCKER" and not r.passed]
    warnings = [r for r in results if r.severity == "WARNING" and not r.passed]

    lines += ["", "---", "", "## Summary"]
    lines.append(f"- **Blockers fallados:** {len(blockers)}")
    lines.append(f"- **Warnings fallados:** {len(warnings)}")

    if blockers:
        lines += ["", "### Blockers que requieren acción"]
        for r in blockers:
            lines.append(f"- **{r.gate_id}** {r.label}: `{r.fmt_value()}` (threshold: {r.fmt_threshold()})")

    if warnings:
        lines += ["", "### Warnings (training permitido pero documentar)"]
        for r in warnings:
            lines.append(f"- **{r.gate_id}** {r.label}: `{r.fmt_value()}` (threshold: {r.fmt_threshold()})")

    lines += ["", "---", "", "## Stats detalladas", ""]
    for k, v in stats.items():
        if k == "input":
            continue
        fv = f"{v:.4f}" if isinstance(v, float) else str(v)
        lines.append(f"- **{k}:** {fv}")

    lines += ["", "---", "", "_Generado por `scripts/finetuning/09_dataset_quality_gate.py`_"]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sprint 7 Dataset Quality Gate — verifica PASS/FAIL antes de lanzar training."
    )
    parser.add_argument("--input", required=True, type=Path, help="Path al dataset .jsonl")
    parser.add_argument("--eval-set", type=Path, default=None, help="Path al CCEE eval set (optional)")
    parser.add_argument("--report-out", type=Path, default=None, help="Guardar reporte markdown en este path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed para Self-BLEU sampling")
    parser.add_argument(
        "--pii-whitelist", type=str, nargs="*", default=None,
        metavar="HANDLE",
        help="Instagram handles to exclude from PII detection (e.g. @iris_bertran). Case-insensitive.",
    )
    args = parser.parse_args()

    random.seed(args.seed)

    if not args.input.exists():
        print(f"❌ ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    pii_whitelist_set = set(h.lower() for h in args.pii_whitelist) if args.pii_whitelist else set()
    results, stats = run_gate(args.input, eval_set_path=args.eval_set, verbose=True, pii_whitelist=pii_whitelist_set)
    verdict = decide(results)

    blockers_failed = [r for r in results if r.severity == "BLOCKER" and not r.passed]
    warnings_failed = [r for r in results if r.severity == "WARNING" and not r.passed]

    print(f"\n{'='*60}")
    if verdict == "PASS":
        print(f" RESULTADO FINAL: ✅ PASS")
    elif verdict == "PASS_WITH_WARNINGS":
        print(f" RESULTADO FINAL: ⚠️  PASS_WITH_WARNINGS ({len(warnings_failed)} warnings)")
    elif verdict == "PASS_DEGRADED":
        print(f" RESULTADO FINAL: ⚠️  PASS_DEGRADED ({len(warnings_failed)} warnings — revisar antes de training)")
    else:
        print(f" RESULTADO FINAL: ❌ FAIL ({len(blockers_failed)} blockers)")
    print(f"{'='*60}\n")

    if blockers_failed:
        print("Blockers que impiden training:")
        for r in blockers_failed:
            print(f"  ❌ {r.gate_id} {r.label}: {r.fmt_value()} (threshold: {r.fmt_threshold()})")
        print()
        print("Consulta docs/finetuning_sprint_iris/presprint7/09_dataset_quality_gate.md Sección D para fixes.")
        print()

    if args.report_out:
        report_md = build_report(results, stats, verdict)
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(report_md, encoding="utf-8")
        print(f"Reporte guardado: {args.report_out}")

    sys.exit(0 if verdict != "FAIL" else 1)


if __name__ == "__main__":
    main()
