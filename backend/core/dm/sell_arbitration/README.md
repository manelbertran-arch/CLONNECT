# Sales Intent Arbitration

Semantic arbiter for sell / don't-sell decisions in the Clonnect DM pipeline.
Consolidates four previously-independent signal systems (DNA Engine,
Conversation State, Frustration Detector, Relationship Scorer) into a single
`SellDirective` emitted by a stateless two-layer resolver.

## Why

Before this module the four systems emitted contradictory instructions into
`_build_recalling_block()` (context.py) — "NUNCA vender" + "Menciona el
producto" + "No vendas ahora" + products physically stripped — with no
arbitration. The LLM resolved conflicts ad-hoc, producing three documented
Type-1 contradictions in audit S6 (commit `d5616c68`):

| ID  | Collision                                            |
| --- | ---------------------------------------------------- |
| R.4 | DNA=FAMILIA ("NUNCA vender") vs ConvState=PROPUESTA ("Menciona el producto") |
| R.5 | Frustration≥2 ("No vendas ahora") vs Scorer=PROPUESTA ("Da el link")         |
| C.8 | Multiple sell triggers firing in the same turn                               |

## Two-layer pattern

Recommended by `docs/research/multi_signal_arbitration_review.md` (main
commit `2f71badc`, SafeCRS-inspired). The research synthesis of 5 papers
(arxiv 2604.09075, 2504.08754, 2603.03536, 2503.18666, EMNLP 2025) concludes
that the safest structure splits hard binary vetos from learned ordinal
reasoning.

```
SellArbiterInputs  ──▶  Layer 1: evaluate_vetos
                            │
                 NO_SELL ◀──┤ P1 sensitive
                            │ P2 frustration ≥ 2
                            │
                            └── None ──▶  Layer 2: evaluate_arbitration
                                              │
                                 NO_SELL   ◀──┤ P3 DNA ∈ {FAMILIA, INTIMA}
                                 REDIRECT  ◀──┤ P4 suppress_products
                                 SOFT_MENTION ◀┤ P5 soft_suppress ∨ DNA=AMISTAD_CERCANA
                                 SELL_ACTIVELY ◀┤ P6 phase ∈ {PROPUESTA, CIERRE}
                                 SOFT_MENTION ◀┘ P7 default
```

## Priority table

| Prio | Trigger                                                       | Directive       | Layer        |
| ---- | ------------------------------------------------------------- | --------------- | ------------ |
| P1   | `sensitive_action_required` ∈ `{no_pressure_sale, empathetic_response}` | `NO_SELL`       | veto         |
| P2   | `frustration_level ≥ 2`                                       | `NO_SELL`       | veto         |
| P3   | `dna_relationship_type ∈ {FAMILIA, INTIMA, COLABORADOR}`      | `NO_SELL`       | arbitration  |
| P4   | `suppress_products == True`                                   | `REDIRECT`      | arbitration  |
| P5   | `soft_suppress == True` ∨ `dna == AMISTAD_CERCANA`            | `SOFT_MENTION`  | arbitration  |
| P6   | `conv_phase ∈ {PROPUESTA, CIERRE}`                            | `SELL_ACTIVELY` | arbitration  |
| P7   | default                                                       | `SOFT_MENTION`  | arbitration  |

`COLABORADOR` = business partner / cross-promo creator. Treated as NO_SELL
because partners are not a sales target; selling to them damages the
professional relationship. The mapping lives in `DNA_NO_SELL_SET`
(`arbitration_layer.py`) and is enforced as a valid DNA type in
`VALID_DNA_TYPES` (`inputs.py`).

## Usage

```python
from core.dm.sell_arbitration import SalesIntentResolver, SellArbiterInputs

resolver = SalesIntentResolver()  # stateless, safe to share at module scope

directive = resolver.resolve(SellArbiterInputs(
    creator_id="iris_bertran",
    dna_relationship_type="FAMILIA",
    conv_phase="PROPUESTA",
    frustration_level=0,
    relationship_score=0.3,
    suppress_products=False,
    soft_suppress=False,
    sensitive_action_required=None,
    has_pending_sales_commitment=False,
))
# directive is SellDirective.NO_SELL  (P3 beats P6)
```

## Scope v1

`resolve()` returns `SellDirective` only. The design doc §13 originally proposed
a richer `SellArbiterResult` with `aux_text`, `blocking_signal`, and
`counterfactual` fields. **v1 defers those to a later iteration.** This keeps
the resolver a pure decision function with a minimal return surface.

## Integration (P4 adapter)

`adapter.py` bridges the DM pipeline context (raw_dna dict, state_meta dict,
cognitive_metadata dict, DetectionResult, RelationshipScore, commitment text)
to `SellArbiterInputs`, and renders the directive / aux_text strings that
replace the four previous injections in `_build_recalling_block`.

Public entry points:

```python
from core.dm.sell_arbitration import (
    extract_sell_arbiter_inputs,
    render_directive_text,
    synthesize_aux_text,
)

inputs = extract_sell_arbiter_inputs(
    creator_id=agent.creator_id,
    raw_dna=raw_dna,
    state_meta=state_meta,
    cognitive_metadata=cognitive_metadata,
    detection=detection,
    rel_score=_rel_score,
    commitment_text=commitment_text,
)
directive = resolver.resolve(inputs)
directive_text = render_directive_text(directive)   # e.g. "Directiva: NO vendas…"
aux_text      = synthesize_aux_text(directive, inputs)  # "" unless R.9
```

The adapter:

1. **Normalizes uppercase**. `ConversationPhase` enum uses lowercase
   (`"propuesta"`); `.upper()` is applied defensively. `RelationshipType`
   already stores uppercase but is also normalized.
2. **Fallbacks with telemetry.** Every upstream source can be None / missing;
   the adapter applies documented defaults and emits `sell_adapter_fallback`
   (`creator_id`, `field`) so prolonged fallback rates surface as a signal
   rather than silent degradation.
3. **Synthesizes R.9 aux_text** when `directive == NO_SELL AND
   has_pending_sales_commitment == True` — the resolver itself stays pure.

Activation in `context.py` is gated by `ENABLE_SELL_ARBITER_LIVE`
(default `false`). When the flag is on:

- `state_context` is suppressed (phase verbs replaced by the directive).
- `frustration_note` is replaced by `aux_text` (empty unless R.9 fires).
- `dna_context` and `memory` remain read-only.
- `is_friend` is derived from the directive: `NO_SELL` / `REDIRECT` →
  products stripped from the system prompt (consistent with the resolver's
  hard-no-sell outcomes); `SOFT_MENTION` / `SELL_ACTIVELY` → products
  visible.

## Known limitations (v1)

- **DNA `rel_hints` trade-off.** The DNA context block
  (`dm_agent_context_integration.py`) still emits a one-liner hint per
  relationship type — including `"Familiar directo — trato cariñoso,
  personal, NUNCA vender"` for `FAMILIA`. With the arbiter LIVE this
  coincides with `NO_SELL` for `{FAMILIA, INTIMA, COLABORADOR}`, so no
  contradiction surfaces. If future rel_hints disagree with the directive
  for other DNA types, the collision has to be resolved in a follow-up PR
  that suppresses rel_hints when the flag is on.
- **`has_pending_sales_commitment` proxy.** The v1 adapter treats any
  pending commitment in `commitment_tracker` as sales-relevant (`bool(commitment_text)`).
  This admits soft false positives (aux_text for non-sales commitments).
  Filtering by `commitment_type` is a backlog item — see the tracker's
  pattern set in `services/commitment_tracker.py`.
- **Conv State stall on FAMILIA.** When the resolver emits `NO_SELL` for a
  FAMILIA lead in phase=PROPUESTA, the Conversation State machine still
  advances nominally. This is intentional per design doc §1 option C — the
  divergence is exposed via metrics (`sell_resolver_total{directive="NO_SELL"}`
  + `conv_state_phase` tag) so a future iteration can decide whether to
  block the transition (option B, out of scope for this PR).
- **R.9 aux_text inside adapter.** Generation of the pending-commitment
  auxiliary text lives in the adapter, not the resolver. The
  `has_pending_sales_commitment` field is still declared on
  `SellArbiterInputs` so the resolver could read it in a future v2 if a
  richer `SellArbiterResult` is introduced.

## Observability

Four Prometheus counters are registered in `core/observability/metrics.py`:

| Metric                        | Labels                                             | Emitted by           |
| ----------------------------- | -------------------------------------------------- | -------------------- |
| `sell_veto_triggered`         | `creator_id`, `priority` (P1/P2), `reason`         | `veto_layer.py`      |
| `sell_arbitration_resolved`   | `creator_id`, `priority` (P3…P7), `directive`, `reason` | `arbitration_layer.py` |
| `sell_resolver_total`         | `creator_id`, `layer` (veto/arbitration), `directive`   | `resolver.py`        |
| `sell_adapter_fallback`       | `creator_id`, `field` (dna/phase/frustration/rel_score/sensitive) | `adapter.py` |

Logs: resolver uses a 4-byte `blake2b` hash for `creator_id` in log lines
(`creator_hash=<8 hex chars>`) to cap log volume; full `creator_id` remains
in Prometheus labels for dashboards.

## References

- Research: `docs/research/multi_signal_arbitration_review.md` (main `2f71badc`)
- Design: `docs/audit_sprint5/s6_rematrix/sales_arbitration_design.md`
- Forensic analysis: `docs/audit_sprint5/s6_rematrix/sales_arbitration_analysis.md`
- Audit prioritization: commit `d5616c68` (s6 re-matrix decisions)
