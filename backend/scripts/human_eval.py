#!/usr/bin/env python3
"""
CCEE Human Evaluation Script (v3 — complete rewrite)

Generates bot responses via the production pipeline, then runs blind A/B
interactive evaluation where Manel rates each response independently.

Features:
  - Generates ALL bot responses first (cached so reruns skip regeneration)
  - Blind A/B with seeded random assignment (seed=42 per case index)
  - Media filter: skips cases where test_input or ground_truth is media-only
  - Full conversation history with media placeholders
  - Per-response rating (1-5) + optional notes per response
  - Incremental save after every case (resume on restart)
  - Back/quit support
  - Summary + optional calibrator run at end

Usage:
    railway run python3.11 scripts/human_eval.py --creator iris_bertran
    railway run python3.11 scripts/human_eval.py --creator iris_bertran --resume
    python3.11 scripts/human_eval.py --creator iris_bertran --dry-run
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Media helpers
# ---------------------------------------------------------------------------

_MEDIA_RE = re.compile(
    r"^\s*\[(audio|sticker|image|video|reel|🏷️\s*Sticker|🎤\s*Audio)\]\s*$",
    re.IGNORECASE,
)

_MEDIA_INLINE_RE = re.compile(
    r"\[(audio|sticker|image|video|reel|🏷️\s*Sticker|🎤\s*Audio)\]",
    re.IGNORECASE,
)


def _is_media_only(text: str) -> bool:
    """Return True if text is exclusively a media placeholder."""
    return bool(_MEDIA_RE.match(text.strip())) if text else False


def _is_media_case(conv: dict) -> bool:
    """Return True if test_input or ground_truth is media-only."""
    return _is_media_only(conv.get("test_input", "")) or _is_media_only(
        conv.get("ground_truth", "")
    )


def _humanize_media(text: str, role: str) -> str:
    """Replace raw media tags with readable descriptions."""
    if not text:
        return text
    # Full media-only messages
    m = re.match(
        r"^\s*\[(audio|sticker|image|video|reel|🏷️\s*Sticker|🎤\s*Audio)\]\s*$",
        text,
        re.IGNORECASE,
    )
    if m:
        kind = m.group(1).lower().replace("🏷️ ", "").replace("🎤 ", "")
        label = "Iris" if role in ("assistant", "iris") else "Lead"
        return f"[{label} envió un {kind}]"
    # Inline replacements
    def _replace(match: re.Match) -> str:
        kind = match.group(1).lower().replace("🏷️ ", "").replace("🎤 ", "")
        return f"[{kind}]"
    return _MEDIA_INLINE_RE.sub(_replace, text)


# ---------------------------------------------------------------------------
# History formatter
# ---------------------------------------------------------------------------

MAX_HISTORY_TURNS = 10


def _format_history(turns: List[dict]) -> str:
    """Format conversation turns for display, replacing media with placeholders."""
    if not turns:
        return "  (sin historial previo)"

    display = turns[-MAX_HISTORY_TURNS:]
    omitted = len(turns) - len(display)
    lines = []
    if omitted:
        lines.append(f"  ... ({omitted} turnos anteriores omitidos)")

    for t in display:
        role = t.get("role", "")
        content = t.get("content", "").strip()
        if not content:
            continue
        label = "[Iris]" if role in ("assistant", "iris") else "[Lead]"
        content = _humanize_media(content, role)
        lines.append(f"  {label} {content}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Load test cases
# ---------------------------------------------------------------------------

def load_test_cases(creator_id: str, test_set_path: Optional[str] = None) -> List[Dict]:
    """Load test cases from stratified test set."""
    if test_set_path:
        ts_path = Path(test_set_path)
    else:
        ts_path = REPO_ROOT / "tests" / "cpe_data" / creator_id / "test_set_v2_stratified.json"

    if not ts_path.exists():
        print(f"ERROR: Test set not found: {ts_path}", file=sys.stderr)
        sys.exit(1)

    with open(ts_path, encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, list):
        cases = raw
    else:
        cases = raw.get("conversations", raw.get("test_cases", []))

    return cases


def filter_cases(conversations: List[Dict]) -> Tuple[List[Dict], int]:
    """Filter media-only cases. Returns (valid_cases, n_excluded)."""
    valid = [c for c in conversations if not _is_media_case(c)]
    return valid, len(conversations) - len(valid)


# ---------------------------------------------------------------------------
# Bot response generation
# ---------------------------------------------------------------------------

CACHE_FILENAME = "human_eval_responses_cache.json"


def _get_cache_path(creator_id: str) -> Path:
    p = REPO_ROOT / "tests" / "ccee_results" / creator_id
    p.mkdir(parents=True, exist_ok=True)
    return p / CACHE_FILENAME


def _load_cache(creator_id: str) -> Dict[str, str]:
    """Load cached bot responses keyed by case id."""
    cp = _get_cache_path(creator_id)
    if cp.exists():
        with open(cp, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(creator_id: str, cache: Dict[str, str]) -> None:
    cp = _get_cache_path(creator_id)
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _generate_bot_responses(
    creator_id: str,
    cases: List[Dict],
    dry_run: bool = False,
) -> Dict[str, str]:
    """Generate bot responses for all cases. Loads cache, skips already-generated ones."""
    cache = _load_cache(creator_id)
    missing = [c for c in cases if c["id"] not in cache]

    if not missing:
        print(f"  Respuestas cacheadas para {len(cases)} casos — no se regeneran.")
        return cache

    print(f"  Generando {len(missing)} respuestas bot (ya cacheadas: {len(cases) - len(missing)})...")

    if dry_run:
        for c in missing:
            cache[c["id"]] = "FAKE BOT RESPONSE"
        _save_cache(creator_id, cache)
        print(f"  [dry-run] Generadas {len(missing)} respuestas fake.")
        return cache

    # Load production pipeline
    try:
        from core.dm.agent import get_dm_agent
    except ImportError as e:
        print(f"ERROR: No se pudo importar el pipeline: {e}", file=sys.stderr)
        print("Usa railway run o asegúrate de que DATABASE_URL está disponible.", file=sys.stderr)
        sys.exit(1)

    agent = get_dm_agent(creator_id)

    for idx, tc in enumerate(missing):
        case_id = tc["id"]
        message = tc.get("test_input", "")
        sender_id = tc.get("lead_username", "test_user")

        try:
            dm_response = asyncio.run(
                agent.process_dm(
                    message=message,
                    sender_id=sender_id,
                    metadata={"platform": "instagram"},
                )
            )
            bot_text = (
                dm_response.content
                if hasattr(dm_response, "content")
                else str(dm_response)
            )
        except Exception as e:
            bot_text = f"[ERROR: {e}]"

        cache[case_id] = bot_text

        # Save cache after every response so progress is not lost
        _save_cache(creator_id, cache)

        done = len(cases) - len(missing) + idx + 1
        bar_width = 30
        filled = int(bar_width * done / len(cases))
        bar = "█" * filled + "░" * (bar_width - filled)
        print(
            f"\r  [{bar}] {done}/{len(cases)}  {case_id[:20]:<20}",
            end="",
            flush=True,
        )

    print()  # newline after progress bar
    return cache


# ---------------------------------------------------------------------------
# A/B assignment
# ---------------------------------------------------------------------------

def _ab_assign(case_idx: int, seed: int = 42) -> bool:
    """Return True if bot is assigned to slot A, False if bot is slot B."""
    rng = random.Random(seed + case_idx)
    return rng.random() < 0.5


# ---------------------------------------------------------------------------
# Progress persistence
# ---------------------------------------------------------------------------

PROGRESS_FILENAME = "human_eval_progress.json"


def _get_progress_path(creator_id: str) -> Path:
    p = REPO_ROOT / "tests" / "ccee_results" / creator_id
    p.mkdir(parents=True, exist_ok=True)
    return p / PROGRESS_FILENAME


def _load_progress(creator_id: str) -> Dict:
    pp = _get_progress_path(creator_id)
    if pp.exists():
        with open(pp, encoding="utf-8") as f:
            return json.load(f)
    return {"ratings": [], "metadata": {}}


def _save_progress(creator_id: str, data: Dict) -> None:
    pp = _get_progress_path(creator_id)
    with open(pp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Single-case presentation
# ---------------------------------------------------------------------------

def _trust_label(conv: Dict) -> str:
    """Return human-readable trust label."""
    trust = conv.get("trust_score", conv.get("trust_segment", None))
    if trust is None:
        return "UNKNOWN"
    if isinstance(trust, str):
        return trust.upper()
    if trust < 0.3:
        return "UNKNOWN"
    if trust < 0.7:
        return "KNOWN"
    if trust < 0.9:
        return "CLOSE"
    return "INTIMATE"


def _present_case(
    conv: Dict,
    case_idx: int,   # 0-based index into filtered cases list
    case_num: int,   # 1-based display number
    total: int,
    bot_response: str,
    dry_run: bool = False,
    auto_answer: bool = False,
) -> Optional[Dict]:
    """
    Present a single case and collect ratings.

    Returns:
        dict with rating data  — normal evaluation
        "back"                 — user wants to go back
        None                   — user wants to quit
    """
    separator = "═" * 55

    category = conv.get("category", "?")
    language = conv.get("language", "?")
    trust = _trust_label(conv)

    print(f"\n{separator}")
    print(f"  Caso {case_num}/{total}  |  {category}  |  {language}  |  Trust: {trust}")
    print(separator)

    # History
    turns = conv.get("turns", [])
    if turns:
        print()
        print("  HISTORIAL:")
        print(_format_history(turns))

    # Lead message
    test_input = conv.get("test_input", "")
    print()
    print(f"  ─── LEAD DICE ───")
    print(f'  "{test_input}"')
    print()

    # Blind A/B assignment
    bot_is_A = _ab_assign(case_idx, seed=42)
    real_response = conv.get("ground_truth", "")

    if bot_is_A:
        response_A = bot_response
        response_B = real_response
    else:
        response_A = real_response
        response_B = bot_response

    print(f"  ─── RESPUESTA A ───")
    print(f'  "{response_A}"')
    print()
    print(f"  ─── RESPUESTA B ───")
    print(f'  "{response_B}"')
    print()
    print(separator)
    print()

    def _ask(prompt: str, auto_val: str = "") -> str:
        if auto_answer:
            print(f"  {prompt}{auto_val}  [auto]")
            return auto_val
        return input(f"  {prompt}").strip()

    # --- Q1: Who is Iris? ---
    while True:
        ans = _ask("1. ¿Quién es Iris, A o B? > ", "A" if auto_answer else "")
        al = ans.lower()
        if al in ("a", "b"):
            break
        if al in ("back", "quit", "q"):
            return None if al in ("quit", "q") else "back"
        if auto_answer:
            ans = "A"
            break
        print("     → Escribe A o B (o back/quit)")

    iris_choice = ans.upper()
    iris_correct = (iris_choice == ("B" if bot_is_A else "A"))

    # --- Q2: Response A rating ---
    print()
    while True:
        ans_a = _ask("2. Respuesta A — ¿La enviarías como Iris? (1-5) > ", "3" if auto_answer else "")
        if ans_a.lower() in ("back", "quit", "q"):
            return None if ans_a.lower() in ("quit", "q") else "back"
        try:
            score_a = int(ans_a)
            if 1 <= score_a <= 5:
                break
        except ValueError:
            pass
        if auto_answer:
            score_a = 3
            break
        print("     → Escribe un número del 1 al 5")

    notes_a = _ask("   Notas sobre A (opcional, Enter para saltar) > ", "" if auto_answer else "")
    if notes_a.lower() in ("quit", "q"):
        return None
    if notes_a.lower() == "back":
        return "back"

    # --- Q3: Response B rating ---
    print()
    while True:
        ans_b = _ask("3. Respuesta B — ¿La enviarías como Iris? (1-5) > ", "4" if auto_answer else "")
        if ans_b.lower() in ("back", "quit", "q"):
            return None if ans_b.lower() in ("quit", "q") else "back"
        try:
            score_b = int(ans_b)
            if 1 <= score_b <= 5:
                break
        except ValueError:
            pass
        if auto_answer:
            score_b = 4
            break
        print("     → Escribe un número del 1 al 5")

    notes_b = _ask("   Notas sobre B (opcional, Enter para saltar) > ", "" if auto_answer else "")
    if notes_b.lower() in ("quit", "q"):
        return None
    if notes_b.lower() == "back":
        return "back"

    # --- Confirmation ---
    if not auto_answer:
        confirm = input("  Guardado | Enter=siguiente | back=anterior | quit=guardar y salir > ").strip().lower()
        if confirm == "quit":
            return None
        if confirm == "back":
            return "back"

    # Build result record
    if bot_is_A:
        bot_score = score_a
        iris_score = score_b
        bot_notes = notes_a if notes_a else None
        iris_notes = notes_b if notes_b else None
    else:
        bot_score = score_b
        iris_score = score_a
        bot_notes = notes_b if notes_b else None
        iris_notes = notes_a if notes_a else None

    return {
        "case_id": conv.get("id", f"case_{case_num}"),
        "case_num": case_num,
        "test_input": test_input,
        "bot_response": bot_response,
        "ground_truth": real_response,
        "category": category,
        "language": language,
        "trust_segment": trust,
        "bot_is_A": bot_is_A,
        "iris_choice": iris_choice,
        "iris_identified_correctly": iris_correct,
        "score_A": score_a,
        "score_B": score_b,
        "bot_would_send_score": bot_score,
        "iris_would_send_score": iris_score,
        "notes_bot": bot_notes,
        "notes_iris": iris_notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _print_summary(ratings: List[Dict]) -> Dict:
    """Print end-of-session summary and return aggregate scores."""
    sep = "═" * 55
    print(f"\n{sep}")
    print("  RESUMEN DE EVALUACIÓN HUMANA")
    print(sep)
    print(f"  Casos evaluados: {len(ratings)}")
    print()

    # Turing identification accuracy
    turing_results = [r for r in ratings if "iris_identified_correctly" in r]
    if turing_results:
        correct = sum(1 for r in turing_results if r["iris_identified_correctly"])
        acc = correct / len(turing_results) * 100
        fooled = len(turing_results) - correct
        print(f"  H1 Turing Test:")
        print(f"    Identificó correctamente a Iris: {correct}/{len(turing_results)} ({acc:.1f}%)")
        print(f"    Engañado (pensó que el bot era Iris): {fooled}/{len(turing_results)} ({100 - acc:.1f}%)")

    # Would-send scores
    bot_scores = [r["bot_would_send_score"] for r in ratings if r.get("bot_would_send_score") is not None]
    iris_scores = [r["iris_would_send_score"] for r in ratings if r.get("iris_would_send_score") is not None]

    if bot_scores:
        avg_bot = sum(bot_scores) / len(bot_scores)
        print(f"\n  Would-send Bot:  {avg_bot:.2f}/5  (n={len(bot_scores)})")
    if iris_scores:
        avg_iris = sum(iris_scores) / len(iris_scores)
        print(f"  Would-send Iris: {avg_iris:.2f}/5  (n={len(iris_scores)})")

    # Notes count
    notes_bot = [r for r in ratings if r.get("notes_bot")]
    notes_iris = [r for r in ratings if r.get("notes_iris")]
    total_notes = len(notes_bot) + len(notes_iris)
    if total_notes:
        print(f"\n  Notas recogidas: {total_notes} (bot: {len(notes_bot)}, iris: {len(notes_iris)})")
        for r in notes_bot[:3]:
            print(f"    [BOT][{r['case_id']}] {r['notes_bot'][:80]}")
        for r in notes_iris[:3]:
            print(f"    [IRIS][{r['case_id']}] {r['notes_iris'][:80]}")

    print(f"{sep}")

    scores = {}
    if turing_results:
        scores["H1_turing"] = {
            "accuracy_pct": round(acc, 1),
            "correct": correct,
            "total": len(turing_results),
        }
    if bot_scores:
        scores["bot_would_send"] = {
            "mean_1_5": round(avg_bot, 2),
            "score_0_100": round((avg_bot - 1) * 25, 1),
            "n": len(bot_scores),
        }
    if iris_scores:
        scores["iris_would_send"] = {
            "mean_1_5": round(avg_iris, 2),
            "score_0_100": round((avg_iris - 1) * 25, 1),
            "n": len(iris_scores),
        }

    return scores


# ---------------------------------------------------------------------------
# Calibrator runner
# ---------------------------------------------------------------------------

def _run_calibrator(creator_id: str):
    """Run scripts/calibrate_ccee.py if it exists."""
    cal_path = REPO_ROOT / "scripts" / "calibrate_ccee.py"
    if not cal_path.exists():
        print("  Calibrador no encontrado (scripts/calibrate_ccee.py) — saltando.")
        return

    print(f"\n  Ejecutando calibrador: {cal_path}")
    import subprocess
    result = subprocess.run(
        [sys.executable, str(cal_path), "--creator", creator_id],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"  Calibrador terminó con código {result.returncode}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CCEE Human Evaluation v3")
    parser.add_argument("--creator", required=True, help="Creator slug (e.g. iris_bertran)")
    parser.add_argument("--test-set", default=None, help="Custom test set path")
    parser.add_argument("--resume", action="store_true", help="Resume previous session")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Use fake bot responses, auto-answer first 2 cases, no real pipeline"
    )
    args = parser.parse_args()

    creator = args.creator
    dry_run = args.dry_run

    # ── Load test cases ──────────────────────────────────────────────────────
    print(f"\n  Cargando casos de prueba para {creator}...")
    all_cases = load_test_cases(creator, args.test_set)
    valid_cases, n_excluded = filter_cases(all_cases)

    print(f"  Cargados: {len(all_cases)} | Filtrados (media): {n_excluded} | Válidos: {len(valid_cases)}")

    if dry_run:
        # Show A/B assignments for first 3 cases
        print("\n  [dry-run] Asignaciones A/B (primeros 3 casos):")
        for i, c in enumerate(valid_cases[:3]):
            bot_is_A = _ab_assign(i, seed=42)
            print(f"    Caso {i+1} ({c['id']}): Bot→{'A' if bot_is_A else 'B'}, Iris→{'B' if bot_is_A else 'A'}")

    # ── Generate / load bot responses ────────────────────────────────────────
    print()
    bot_cache = _generate_bot_responses(creator, valid_cases, dry_run=dry_run)

    # ── Resume logic ─────────────────────────────────────────────────────────
    progress = _load_progress(creator)
    completed_ids = {r["case_id"] for r in progress.get("ratings", [])}

    if args.resume and completed_ids:
        print(f"\n  Progreso anterior detectado: {len(completed_ids)} casos completados.")
        ans = input(f"  ¿Continuar desde caso {len(completed_ids) + 1}? (s/n) > ").strip().lower()
        if ans not in ("s", "si", "sí", "y", "yes", ""):
            print("  Empezando desde el principio.")
            progress = {"ratings": [], "metadata": {}}
            completed_ids = set()
    elif not args.resume and completed_ids and not dry_run:
        print(f"\n  Hay {len(completed_ids)} casos evaluados previamente.")
        print(f"  Usa --resume para continuar o se sobrescribirán.")
        ans = input("  ¿Continuar sesión anterior? (s/n) > ").strip().lower()
        if ans in ("s", "si", "sí", "y", "yes"):
            args.resume = True
        else:
            progress = {"ratings": [], "metadata": {}}
            completed_ids = set()

    ratings: List[Dict] = list(progress.get("ratings", []))

    # Build list of remaining cases
    remaining = [
        (i, c) for i, c in enumerate(valid_cases)
        if c.get("id", f"case_{i+1}") not in completed_ids
    ]
    total_display = len(valid_cases)

    if not remaining:
        print("\n  Todos los casos ya evaluados.")
        _print_summary(ratings)
        return

    print(f"\n{'═' * 55}")
    print(f"  Evaluación Humana CCEE — @{creator}")
    print(f"{'═' * 55}")
    print(f"  Casos a evaluar: {len(remaining)} (total válidos: {total_display})")
    print()
    print("  Instrucciones:")
    print("  - Se muestran dos respuestas (A y B) por mensaje")
    print("  - Una es el bot, la otra es Iris real — adivina cuál")
    print("  - Puntúa cada respuesta del 1 al 5 (¿la enviarías como Iris?)")
    print("  - Escribe 'back' para ir al caso anterior")
    print("  - Escribe 'quit' para guardar y salir")
    if dry_run:
        print("\n  [dry-run] Solo se procesan 2 casos con respuestas auto.")
    print()

    cursor = 0  # index into remaining list

    while cursor < len(remaining):
        case_idx, conv = remaining[cursor]
        case_num = len(completed_ids) + cursor + 1  # display number (1-based)

        bot_resp = bot_cache.get(conv.get("id", ""), "")
        if not bot_resp:
            print(f"  [saltar] Sin respuesta bot para {conv.get('id')} — saltando")
            cursor += 1
            continue

        auto_answer = dry_run and cursor < 2

        result = _present_case(
            conv=conv,
            case_idx=case_idx,
            case_num=case_num,
            total=total_display,
            bot_response=bot_resp,
            dry_run=dry_run,
            auto_answer=auto_answer,
        )

        if result is None:
            # Quit
            print("\n  Guardando progreso y saliendo...")
            break

        if result == "back":
            if cursor > 0:
                cursor -= 1
                # Remove last rating if it matches the previous case
                prev_idx, prev_conv = remaining[cursor]
                prev_id = prev_conv.get("id", f"case_{prev_idx+1}")
                if ratings and ratings[-1].get("case_id") == prev_id:
                    ratings.pop()
                print(f"\n  ← Volviendo al caso {case_num - 1}")
            else:
                print("  Ya estás en el primer caso — no se puede ir atrás.")
            continue

        # Upsert rating
        existing_idx = next(
            (j for j, r in enumerate(ratings) if r.get("case_id") == result.get("case_id")),
            None,
        )
        if existing_idx is not None:
            ratings[existing_idx] = result
        else:
            ratings.append(result)

        cursor += 1

        # Incremental save after every case
        save_data = {
            "ratings": ratings,
            "metadata": {
                "creator": creator,
                "last_saved": datetime.now(timezone.utc).isoformat(),
                "total_rated": len(ratings),
                "dry_run": dry_run,
            },
        }
        _save_progress(creator, save_data)

        progress_path = _get_progress_path(creator)
        print(f"\n  Guardado ({len(ratings)}/{total_display}) → {progress_path.name}")

        # In dry-run, stop after 2 cases
        if dry_run and cursor >= 2:
            print("\n  [dry-run] 2 casos completados — saliendo.")
            break

    # ── Final summary ────────────────────────────────────────────────────────
    scores = _print_summary(ratings)

    final_data = {
        "ratings": ratings,
        "scores": scores,
        "metadata": {
            "creator": creator,
            "completed": datetime.now(timezone.utc).isoformat(),
            "total_rated": len(ratings),
            "total_valid_cases": len(valid_cases),
            "dry_run": dry_run,
            "cache_path": str(_get_cache_path(creator)),
        },
    }
    _save_progress(creator, final_data)
    progress_path = _get_progress_path(creator)
    print(f"\n  Resultados guardados en: {progress_path}")

    # ── Calibrator ───────────────────────────────────────────────────────────
    if not dry_run and len(ratings) >= 5:
        _run_calibrator(creator)


if __name__ == "__main__":
    main()
