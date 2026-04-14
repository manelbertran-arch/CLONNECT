#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  Sprint 3.1 — Automated CCEE Pipeline
#  Watches for consolidation to finish, then runs 31B + 26B
#  in parallel with ultra-detailed comparison reports
# ══════════════════════════════════════════════════════════════
#
#  Usage:
#    cd ~/Clonnect/backend
#    nohup bash scripts/run_sprint31_auto.sh > /tmp/sprint31_auto.log 2>&1 &
#    tail -f /tmp/sprint31_auto.log
#
# ══════════════════════════════════════════════════════════════

cd ~/Clonnect/backend

echo "══════════════════════════════════════════════════════════"
echo "  Sprint 3.1 — Automated CCEE Pipeline"
echo "  Started: $(date)"
echo "══════════════════════════════════════════════════════════"

# ── PHASE 1: Wait for consolidation to finish ─────────────────
echo ""
echo "=== PHASE 1: Waiting for consolidation to finish ==="

while true; do
    if pgrep -f "run_consolidation.py" > /dev/null 2>&1; then
        echo "  $(date +%H:%M:%S) — Consolidation still running..."
        sleep 30
    else
        echo "  $(date +%H:%M:%S) — Consolidation finished"
        break
    fi
done

sleep 5

# ── Verify facts state ────────────────────────────────────────
echo ""
echo "=== Verifying facts state after consolidation ==="
set -a && source .env && set +a

python3.11 -c "
from sqlalchemy import create_engine, text
import os, sys
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    active = conn.execute(text('''
        SELECT COUNT(*) FROM lead_memories lf
        JOIN leads l ON lf.lead_id = l.id
        JOIN creators c ON l.creator_id = c.id
        WHERE c.instagram_username = 'iris_bertran' AND lf.is_active = true
    ''')).scalar()
    inactive = conn.execute(text('''
        SELECT COUNT(*) FROM lead_memories lf
        JOIN leads l ON lf.lead_id = l.id
        JOIN creators c ON l.creator_id = c.id
        WHERE c.instagram_username = 'iris_bertran' AND lf.is_active = false
    ''')).scalar()
    total = active + inactive
    pct = inactive/total*100 if total > 0 else 0
    print(f'Facts state:')
    print(f'  Active:   {active}')
    print(f'  Inactive: {inactive}')
    print(f'  Total:    {total}')
    print(f'  Deactivation rate: {pct:.1f}%')
    print()
    # Breakdown by type
    rows = conn.execute(text('''
        SELECT lf.fact_type, 
               SUM(CASE WHEN lf.is_active THEN 1 ELSE 0 END) as active,
               SUM(CASE WHEN NOT lf.is_active THEN 1 ELSE 0 END) as inactive
        FROM lead_memories lf
        JOIN leads l ON lf.lead_id = l.id
        JOIN creators c ON l.creator_id = c.id
        WHERE c.instagram_username = 'iris_bertran'
        GROUP BY lf.fact_type ORDER BY inactive DESC
    ''')).fetchall()
    print(f'  {\"Type\":<20} {\"Active\":>8} {\"Inactive\":>10} {\"Sprint3 Inact\":>14}')
    print(f'  {\"-\"*20} {\"-\"*8} {\"-\"*10} {\"-\"*14}')
    sprint3_old = {'preference':351,'compressed_memo':267,'personal_info':187,'commitment':178,'topic':159,'objection':97,'purchase_history':21}
    for r in rows:
        old = sprint3_old.get(r[0], '?')
        print(f'  {r[0]:<20} {r[1]:>8} {r[2]:>10} {str(old):>14}')
    if active < 5000:
        print('ERROR: Too few active facts — aborting')
        sys.exit(1)
    print()
    print('✅ Facts OK — proceeding to CCEE measurements')
" || { echo "❌ Facts verification failed — aborting"; exit 1; }

# ── PHASE 2: Launch CCEE measurements in parallel ─────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  PHASE 2: CCEE Measurements (31B + 26B in parallel)"
echo "  $(date)"
echo "══════════════════════════════════════════════════════════"

# ── 31B measurement (background) ──
(
    cd ~/Clonnect/backend
    echo "[31B] === STARTED: $(date) ==="

    source config/env_ccee_gemma4_31b_full.sh
    set -a && source .env && set +a
    export CCEE_NO_FALLBACK=1
    export ENABLE_HISTORY_COMPACTION=true

    # Smoke test
    echo "[31B] --- Smoke test ---"
    python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
        --creator iris_bertran --runs 1 --cases 3 \
        --multi-turn --mt-conversations 8 --mt-turns 10 \
        --v4-composite --v41-metrics --v5 --v52-fixes \
        --generate-only \
        --save-as ccee_v53_31b_sprint31_smoke 2>&1 | tail -5

    SMOKE_OK=$(python3.11 -c "
import json
d = json.load(open('tests/ccee_results/iris_bertran/ccee_v53_31b_sprint31_smoke.json'))
r = d.get('runs', [d])[0]
cases = r.get('cases', r.get('results', r.get('per_case_records', [])))
empty = sum(1 for c in cases if not c.get('bot_response', '').strip())
meta = d.get('metadata', {})
model = meta.get('model', 'MISSING')
print(f'Cases={len(cases)} Empty={empty} Model={model}')
if empty > 0 or '26b' in str(model).lower():
    print('FAIL')
else:
    print('OK')
" 2>&1 | tail -1)

    if [ "$SMOKE_OK" != "OK" ]; then
        echo "[31B] ❌ SMOKE FAILED — aborting 31B"
        exit 1
    fi
    echo "[31B] ✅ Smoke passed"

    # Full run with retry
    echo "[31B] --- Full run: 3 runs × 50 cases × mt-conversations=8 ---"
    MAX_RETRIES=3
    RETRY=0
    while [ $RETRY -lt $MAX_RETRIES ]; do
        source config/env_ccee_gemma4_31b_full.sh
        set -a && source .env && set +a
        export CCEE_NO_FALLBACK=1 ENABLE_HISTORY_COMPACTION=true

        python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
            --creator iris_bertran --runs 3 --cases 50 \
            --multi-turn --mt-conversations 8 --mt-turns 10 \
            --v4-composite --v41-metrics --v5 --v52-fixes \
            --save-as ccee_v53_31b_sprint31 2>&1 | tee /tmp/v53_31b_sprint31.log | tail -20

        if [ $? -eq 0 ]; then
            echo "[31B] ✅ Full run completed"
            break
        fi
        RETRY=$((RETRY + 1))
        echo "[31B] ⚠️ Run failed, retry $RETRY/$MAX_RETRIES in 5 min..."
        sleep 300
    done

    echo "[31B] === FINISHED: $(date) ==="
) > /tmp/sprint31_31b.log 2>&1 &
PID_31B=$!
echo "  31B launched (PID: $PID_31B) → /tmp/sprint31_31b.log"

# Wait 2 minutes before launching 26B to stagger DeepInfra load
sleep 120

# ── 26B measurement (background) ──
(
    cd ~/Clonnect/backend
    echo "[26B] === STARTED: $(date) ==="

    source config/env_ccee_gemma4_26b_full.sh
    set -a && source .env && set +a
    export CCEE_NO_FALLBACK=1
    export ENABLE_HISTORY_COMPACTION=true

    # Smoke test
    echo "[26B] --- Smoke test ---"
    python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
        --creator iris_bertran --runs 1 --cases 3 \
        --multi-turn --mt-conversations 8 --mt-turns 10 \
        --v4-composite --v41-metrics --v5 --v52-fixes \
        --generate-only \
        --save-as ccee_v53_26b_sprint31_smoke 2>&1 | tail -5

    SMOKE_OK=$(python3.11 -c "
import json
d = json.load(open('tests/ccee_results/iris_bertran/ccee_v53_26b_sprint31_smoke.json'))
r = d.get('runs', [d])[0]
cases = r.get('cases', r.get('results', r.get('per_case_records', [])))
empty = sum(1 for c in cases if not c.get('bot_response', '').strip())
meta = d.get('metadata', {})
model = meta.get('model', 'MISSING')
print(f'Cases={len(cases)} Empty={empty} Model={model}')
if empty > 0 or '31b' in str(model).lower():
    print('FAIL')
else:
    print('OK')
" 2>&1 | tail -1)

    if [ "$SMOKE_OK" != "OK" ]; then
        echo "[26B] ❌ SMOKE FAILED — aborting 26B"
        exit 1
    fi
    echo "[26B] ✅ Smoke passed"

    # Full run with retry
    echo "[26B] --- Full run: 3 runs × 50 cases × mt-conversations=8 ---"
    MAX_RETRIES=3
    RETRY=0
    while [ $RETRY -lt $MAX_RETRIES ]; do
        source config/env_ccee_gemma4_26b_full.sh
        set -a && source .env && set +a
        export CCEE_NO_FALLBACK=1 ENABLE_HISTORY_COMPACTION=true

        python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
            --creator iris_bertran --runs 3 --cases 50 \
            --multi-turn --mt-conversations 8 --mt-turns 10 \
            --v4-composite --v41-metrics --v5 --v52-fixes \
            --save-as ccee_v53_26b_sprint31 2>&1 | tee /tmp/v53_26b_sprint31.log | tail -20

        if [ $? -eq 0 ]; then
            echo "[26B] ✅ Full run completed"
            break
        fi
        RETRY=$((RETRY + 1))
        echo "[26B] ⚠️ Run failed, retry $RETRY/$MAX_RETRIES in 5 min..."
        sleep 300
    done

    echo "[26B] === FINISHED: $(date) ==="
) > /tmp/sprint31_26b.log 2>&1 &
PID_26B=$!
echo "  26B launched (PID: $PID_26B) → /tmp/sprint31_26b.log"

# ── PHASE 3: Wait for both to finish ──────────────────────────
echo ""
echo "=== PHASE 3: Waiting for both measurements ==="
echo "  Monitor: tail -f /tmp/sprint31_31b.log"
echo "  Monitor: tail -f /tmp/sprint31_26b.log"

wait $PID_31B
EXIT_31B=$?
echo "  31B exited with code: $EXIT_31B"

wait $PID_26B
EXIT_26B=$?
echo "  26B exited with code: $EXIT_26B"

# ── PHASE 4: Ultra-detailed comparison report ─────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  PHASE 4: Comparison Report"
echo "  $(date)"
echo "══════════════════════════════════════════════════════════"

python3.11 -c "
import json, os, sys

# ═══════════════════════════════════════════════════════════
# Sprint 3 baselines (from handoff document)
# ═══════════════════════════════════════════════════════════

BASELINES = {
    '31B': {
        'v5_composite': 67.3,
        'v41_composite': 67.4,
        'v4_composite': 66.8,
        'st_composite': 63.35,
        'mt_composite': 80.05,
        # Dimensions
        'S1_style_fidelity': 69.8,
        'S2_response_quality': 41.2,
        'S3_strategic_alignment': 63.7,
        'S4_adaptation': 62.7,
        'J_old': 55.4,
        'J_new': 75.7,
        'J6_qa_consistency': 72.5,
        'K_memory': 84.3,
        'G5_robustness': 100.0,
        'L_language': 71.1,
        'H_turing': 78.0,
        'B_persona': 55.5,
        # Sub-metrics
        'J3_prompt_to_line': 89.5,
        'J4_line_to_line': 65.4,
        'J5_belief_drift': 67.5,
        'K1_context_retention': 75.7,
        'K2_style_retention': 97.3,
        'L1_persona_tone': 85.5,
        'L2_logical_reasoning': 73.2,
        'L3_action_justification': 50.0,
        'B2_persona_consistency': 24.0,
        'B4_no_violations': 100.0,
        'B5_emotional_signature': 42.5,
        'H1_turing_mt': 78.0,
        'H1_turing_st': 70.0,
        'C2_naturalness': 50.0,
        'C3_contextual': 17.0,
        'A5_vocabulary': 29.3,
        'A6_language': 34.6,
        'A9_catchphrases': 0.0,
    },
    '26B': {
        'v5_composite': 63.5,
        'v41_composite': 62.3,
        'v4_composite': 60.7,
        'st_composite': 60.90,
        'mt_composite': 72.94,
        # Dimensions
        'S1_style_fidelity': 68.4,
        'S2_response_quality': 40.8,
        'S3_strategic_alignment': 53.2,
        'S4_adaptation': 56.5,
        'J_old': 53.8,
        'J_new': 72.2,
        'J6_qa_consistency': 87.5,
        'K_memory': 72.8,
        'G5_robustness': 80.0,
        'L_language': 67.3,
        'H_turing': 86.0,
        'B_persona': 57.5,
        # Sub-metrics
        'J3_prompt_to_line': 84.0,
        'J4_line_to_line': 58.8,
        'J5_belief_drift': 70.0,
        'K1_context_retention': 64.3,
        'K2_style_retention': 85.5,
        'L1_persona_tone': 82.5,
        'L2_logical_reasoning': 64.3,
        'L3_action_justification': 50.0,
        'B2_persona_consistency': 30.5,
        'B4_no_violations': 100.0,
        'B5_emotional_signature': 42.0,
        'H1_turing_mt': 86.0,
        'H1_turing_st': 74.0,
        'C2_naturalness': 45.0,
        'C3_contextual': 16.0,
    },
}

# Sprint 2 baselines for historical context
SPRINT2 = {
    '31B': {'v5_composite': 65.2},
    '26B': {'v5_composite': 63.2},
}

def extract_metrics(data):
    \"\"\"Extract all metrics from CCEE result JSON into flat dict.\"\"\"
    metrics = {}
    
    # Top-level composites
    for key in ['v5_composite', 'v41_composite', 'v4_composite', 'st_composite', 'mt_composite']:
        val = data.get(key)
        if isinstance(val, dict):
            val = val.get('score', val.get('mean'))
        if val is not None:
            metrics[key] = float(val)
    
    # Try multiple locations for sub-metrics
    sources = [
        data.get('multi_turn_scores', {}),
        data.get('single_turn_scores', {}),
        data.get('dimension_scores', {}),
        data.get('runs', [{}])[0] if data.get('runs') else {},
    ]
    
    # Also flatten any nested dicts
    for src in sources:
        if isinstance(src, dict):
            for k, v in src.items():
                if isinstance(v, dict):
                    v = v.get('score', v.get('mean'))
                if isinstance(v, (int, float)) and k not in metrics:
                    metrics[k] = float(v)
    
    return metrics

def print_comparison(model_name, new_metrics, baseline, sprint2_composite=None):
    \"\"\"Print ultra-detailed comparison.\"\"\"
    
    print()
    print('═' * 80)
    print(f'  {model_name} — Sprint 3.1 vs Sprint 3 Comparison')
    print('═' * 80)
    
    # ── Composites ──
    print()
    print('  ┌─ COMPOSITES ─────────────────────────────────────────────────┐')
    for key, label in [
        ('v5_composite', 'v5 Composite'),
        ('v41_composite', 'v4.1 Composite'),
        ('v4_composite', 'v4 Composite'),
        ('st_composite', 'ST Composite'),
        ('mt_composite', 'MT Composite'),
    ]:
        new_val = new_metrics.get(key, '?')
        old_val = baseline.get(key, '?')
        if isinstance(new_val, (int, float)) and isinstance(old_val, (int, float)):
            delta = new_val - old_val
            signal = '⬆️ ' if delta > 1 else '🔻' if delta < -1 else '➡️ '
            line = f'  │ {label:<18} │ Sprint3: {old_val:>6.1f} │ Sprint3.1: {new_val:>6.1f} │ Δ {delta:>+6.1f} {signal} │'
        else:
            line = f'  │ {label:<18} │ Sprint3: {str(old_val):>6} │ Sprint3.1: {str(new_val):>6} │         │'
        print(line)
    
    if sprint2_composite:
        v5_new = new_metrics.get('v5_composite', '?')
        if isinstance(v5_new, (int, float)):
            total_delta = v5_new - sprint2_composite
            print(f'  │ {\"vs Sprint 2\":<18} │ Sprint2: {sprint2_composite:>6.1f} │ Sprint3.1: {v5_new:>6.1f} │ Δ {total_delta:>+6.1f} 📊  │')
    print('  └──────────────────────────────────────────────────────────────┘')
    
    # ── Dimensions ──
    print()
    print('  ┌─ DIMENSIONS ─────────────────────────────────────────────────┐')
    dimension_keys = [
        ('S1_style_fidelity', 'S1 Style'),
        ('S2_response_quality', 'S2 Quality'),
        ('S3_strategic_alignment', 'S3 Strategy'),
        ('S4_adaptation', 'S4 Adaptation'),
        ('J_old', 'J (old)'),
        ('J_new', 'J (new)'),
        ('J6_qa_consistency', 'J6 QA Consist.'),
        ('K_memory', 'K Memory'),
        ('G5_robustness', 'G5 Robustness'),
        ('L_language', 'L Language'),
        ('H_turing', 'H Turing'),
        ('B_persona', 'B Persona'),
    ]
    for key, label in dimension_keys:
        new_val = new_metrics.get(key, '?')
        old_val = baseline.get(key, '?')
        if isinstance(new_val, (int, float)) and isinstance(old_val, (int, float)):
            delta = new_val - old_val
            signal = '⬆️ ' if delta > 2 else '🔻' if delta < -2 else '➡️ '
            print(f'  │ {label:<18} │ Sprint3: {old_val:>6.1f} │ Sprint3.1: {new_val:>6.1f} │ Δ {delta:>+6.1f} {signal} │')
        else:
            # Try fuzzy match
            matched = None
            for mk in new_metrics:
                if key.lower().replace('_','') in mk.lower().replace('_',''):
                    matched = new_metrics[mk]
                    break
            if matched and isinstance(matched, (int, float)) and isinstance(old_val, (int, float)):
                delta = matched - old_val
                signal = '⬆️ ' if delta > 2 else '🔻' if delta < -2 else '➡️ '
                print(f'  │ {label:<18} │ Sprint3: {old_val:>6.1f} │ Sprint3.1: {matched:>6.1f} │ Δ {delta:>+6.1f} {signal} │')
            else:
                print(f'  │ {label:<18} │ Sprint3: {str(old_val):>6} │ Sprint3.1: {str(new_val):>6} │   N/A   │')
    print('  └──────────────────────────────────────────────────────────────┘')
    
    # ── Sub-metrics ──
    print()
    print('  ┌─ SUB-METRICS ────────────────────────────────────────────────┐')
    submetric_keys = [
        ('J3_prompt_to_line', 'J3 Prompt→Line'),
        ('J4_line_to_line', 'J4 Line→Line'),
        ('J5_belief_drift', 'J5 Belief Drift'),
        ('K1_context_retention', 'K1 Context Ret'),
        ('K2_style_retention', 'K2 Style Ret'),
        ('L1_persona_tone', 'L1 Persona Tone'),
        ('L2_logical_reasoning', 'L2 Logic Reas.'),
        ('L3_action_justification', 'L3 Action Just.'),
        ('B2_persona_consistency', 'B2 Persona Con.'),
        ('B4_no_violations', 'B4 No Violat.'),
        ('B5_emotional_signature', 'B5 Emotional'),
        ('H1_turing_mt', 'H1 Turing (MT)'),
        ('H1_turing_st', 'H1 Turing (ST)'),
        ('C2_naturalness', 'C2 Naturalness'),
        ('C3_contextual', 'C3 Contextual'),
        ('A5_vocabulary', 'A5 Vocabulary'),
        ('A6_language', 'A6 Language'),
        ('A9_catchphrases', 'A9 Catchphrases'),
    ]
    for key, label in submetric_keys:
        new_val = new_metrics.get(key, '?')
        old_val = baseline.get(key, '?')
        if isinstance(new_val, (int, float)) and isinstance(old_val, (int, float)):
            delta = new_val - old_val
            signal = '⬆️ ' if delta > 2 else '🔻' if delta < -2 else '➡️ '
            print(f'  │ {label:<18} │ Sprint3: {old_val:>6.1f} │ Sprint3.1: {new_val:>6.1f} │ Δ {delta:>+6.1f} {signal} │')
        elif isinstance(old_val, (int, float)):
            # Try fuzzy match
            matched = None
            for mk in new_metrics:
                if key.lower().replace('_','') in mk.lower().replace('_',''):
                    matched = new_metrics[mk]
                    break
            if matched and isinstance(matched, (int, float)):
                delta = matched - old_val
                signal = '⬆️ ' if delta > 2 else '🔻' if delta < -2 else '➡️ '
                print(f'  │ {label:<18} │ Sprint3: {old_val:>6.1f} │ Sprint3.1: {matched:>6.1f} │ Δ {delta:>+6.1f} {signal} │')
            else:
                print(f'  │ {label:<18} │ Sprint3: {old_val:>6.1f} │ Sprint3.1:    N/A │         │')
    print('  └──────────────────────────────────────────────────────────────┘')
    
    # ── Key regression recovery check ──
    print()
    print('  ┌─ REGRESSION RECOVERY CHECK ──────────────────────────────────┐')
    if model_name == '31B':
        regressions = [
            ('B2_persona_consistency', 'B2 Persona', 24.0, 32.5, 'Sprint 2 was 32.5'),
            ('H1_turing_mt', 'H1 Turing MT', 78.0, 82.0, 'Sprint 2 was 82.0'),
            ('K1_context_retention', 'K1 Context Ret', 75.7, None, 'Track C found -9.4'),
            ('J5_belief_drift', 'J5 Belief Drift', 67.5, None, 'Track C found -7.5'),
        ]
    else:
        regressions = [
            ('G5_robustness', 'G5 Robustness', 80.0, 100.0, 'Sprint 2 was 100'),
            ('S1_style_fidelity', 'S1 Style', 68.4, 71.2, 'Sprint 2 was 71.2'),
            ('S4_adaptation', 'S4 Adaptation', 56.5, 59.3, 'Sprint 2 was 59.3'),
            ('K1_context_retention', 'K1 Context Ret', 64.3, None, 'Track C found -10.0'),
            ('J5_belief_drift', 'J5 Belief Drift', 70.0, None, 'Track C found -15.0'),
            ('J6_qa_consistency', 'J6 QA Consist.', 87.5, None, 'Track C found -12.5'),
        ]
    for key, label, sprint3_val, sprint2_val, note in regressions:
        new_val = new_metrics.get(key, '?')
        if not isinstance(new_val, (int, float)):
            for mk in new_metrics:
                if key.lower().replace('_','') in mk.lower().replace('_',''):
                    new_val = new_metrics[mk]
                    break
        if isinstance(new_val, (int, float)):
            delta = new_val - sprint3_val
            if delta > 2:
                status = '✅ RECOVERED'
            elif delta > 0:
                status = '🟡 PARTIAL'
            elif delta > -2:
                status = '➡️ UNCHANGED'
            else:
                status = '🔻 WORSE'
            target = f' (target: {sprint2_val})' if sprint2_val else ''
            print(f'  │ {label:<16} │ S3:{sprint3_val:>5.1f} → S3.1:{new_val:>5.1f} │ Δ{delta:>+5.1f} │ {status}{target}')
        else:
            print(f'  │ {label:<16} │ S3:{sprint3_val:>5.1f} → S3.1:  N/A │       │ ❓ NOT FOUND')
    print('  └──────────────────────────────────────────────────────────────┘')
    
    # ── All metrics dump ──
    print()
    print('  ┌─ ALL EXTRACTED METRICS (raw) ────────────────────────────────┐')
    for k in sorted(new_metrics.keys()):
        v = new_metrics[k]
        print(f'  │ {k:<40} │ {v:>8.2f} │')
    print('  └──────────────────────────────────────────────────────────────┘')


# ═══════════════════════════════════════════════════════════
# Process results
# ═══════════════════════════════════════════════════════════

print()
print('══════════════════════════════════════════════════════════════════════════════')
print('  SPRINT 3.1 — FULL MEASUREMENT REPORT')
print('  Generated: $(date)')
print('══════════════════════════════════════════════════════════════════════════════')

# 31B
f31 = 'tests/ccee_results/iris_bertran/ccee_v53_31b_sprint31.json'
if os.path.exists(f31):
    d31 = json.load(open(f31))
    m31 = extract_metrics(d31)
    meta = d31.get('metadata', {})
    print(f'  31B model: {meta.get(\"model\", \"?\")}')
    print(f'  31B runs: {len(d31.get(\"runs\", [1]))}')
    print_comparison('31B', m31, BASELINES['31B'], SPRINT2['31B']['v5_composite'])
else:
    print(f'  ❌ 31B results not found: {f31}')

# 26B
f26 = 'tests/ccee_results/iris_bertran/ccee_v53_26b_sprint31.json'
if os.path.exists(f26):
    d26 = json.load(open(f26))
    m26 = extract_metrics(d26)
    meta = d26.get('metadata', {})
    print(f'  26B model: {meta.get(\"model\", \"?\")}')
    print(f'  26B runs: {len(d26.get(\"runs\", [1]))}')
    print_comparison('26B', m26, BASELINES['26B'], SPRINT2['26B']['v5_composite'])
else:
    print(f'  ❌ 26B results not found: {f26}')

# ── Head-to-head ──
if os.path.exists(f31) and os.path.exists(f26):
    print()
    print('═' * 80)
    print('  31B vs 26B — Head to Head (Sprint 3.1)')
    print('═' * 80)
    all_keys = sorted(set(list(m31.keys()) + list(m26.keys())))
    print(f'  {\"Metric\":<40} {\"31B\":>8} {\"26B\":>8} {\"Gap\":>8} {\"Winner\":>8}')
    print(f'  {\"-\"*40} {\"-\"*8} {\"-\"*8} {\"-\"*8} {\"-\"*8}')
    for k in all_keys:
        v31 = m31.get(k)
        v26 = m26.get(k)
        if isinstance(v31, (int, float)) and isinstance(v26, (int, float)):
            gap = v31 - v26
            winner = '31B' if gap > 2 else '26B' if gap < -2 else 'TIE'
            print(f'  {k:<40} {v31:>8.1f} {v26:>8.1f} {gap:>+8.1f} {winner:>8}')

print()
print('══════════════════════════════════════════════════════════════════════════════')
print('  REPORT COMPLETE')
print('══════════════════════════════════════════════════════════════════════════════')
" 2>&1 | tee /tmp/sprint31_report.txt

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  Pipeline complete: $(date)"
echo "  Full report: /tmp/sprint31_report.txt"
echo "  31B log: /tmp/sprint31_31b.log"
echo "  26B log: /tmp/sprint31_26b.log"
echo "══════════════════════════════════════════════════════════"


