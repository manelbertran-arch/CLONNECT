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
| P3   | `dna_relationship_type ∈ {FAMILIA, INTIMA}`                   | `NO_SELL`       | arbitration  |
| P4   | `suppress_products == True`                                   | `REDIRECT`      | arbitration  |
| P5   | `soft_suppress == True` ∨ `dna == AMISTAD_CERCANA`            | `SOFT_MENTION`  | arbitration  |
| P6   | `conv_phase ∈ {PROPUESTA, CIERRE}`                            | `SELL_ACTIVELY` | arbitration  |
| P7   | default                                                       | `SOFT_MENTION`  | arbitration  |

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

## Integration notes for P4 (next PR)

This package lands the arbiter in isolation. Wiring into `context.py` and
replacing the four current injections is deliberately out of scope. The next
PR (P4) must:

1. **Normalize uppercase**. `SellArbiterInputs` requires uppercase enum
   strings for `dna_relationship_type` and `conv_phase`. The in-code
   `ConversationPhase` enum uses lowercase (`"propuesta"`). The adapter layer
   must uppercase the value (or use `enum.name`) before constructing the
   input. `SellArbiterInputs.__post_init__` raises `ValueError` on unknown
   values — failures should surface, not silently default.
2. **Synthesize `aux_text` at the adapter, not inside the resolver.** When
   `directive == NO_SELL` AND `inputs.has_pending_sales_commitment == True`
   (design case R.9), the adapter must generate an auxiliary sentence for
   `frustration_note` ("Tienes un compromiso pendiente. Menciona que lo
   enviarás cuando sea buen momento, sin presionar ahora.") and splice it
   into the prompt separately from the directive. The resolver neither
   reads nor writes aux_text.
3. **Replace the four current injections** in `_build_recalling_block()` with
   directive-conditional rewrites of `state_context` and `frustration_note`
   (DNA, memory, context_notes remain read-only). Insert the arbiter call
   between `context.py:1221` (scorer computed) and `context.py:1504`
   (recalling block assembly) — the single point where all four signals
   converge. See `docs/audit_sprint5/s6_rematrix/sales_arbitration_analysis.md`
   §"Propuesta de Punto de Inserción del Árbitro".

## Known gaps

- **`COLABORADOR` DNA type.** Mentioned in `sales_arbitration_design.md` §2
  but absent from the real `RelationshipType` enum in the code. Treated as
  unknown → `ValueError`. If it appears in production data, surface the bug;
  do not add it to `VALID_DNA_TYPES` without first tracking where it comes
  from.
- **R.9 aux_text.** Generation of the pending-commitment auxiliary text is
  deferred to P4 (see "Integration notes", point 2). The `has_pending_sales_commitment`
  field is carried through `SellArbiterInputs` but not consumed by any
  priority check in v1.
- **Conv State stall on FAMILIA.** When the resolver emits `NO_SELL` for a
  FAMILIA lead in phase=PROPUESTA, the Conversation State machine still
  advances nominally. This is intentional per design doc §1 option C — the
  divergence is exposed via metrics (`sell_resolver_total{directive="NO_SELL"}`
  + `conv_state_phase` tag) so a future iteration can decide whether to block
  the transition (option B, out of scope for this PR).

## Observability

Three Prometheus counters are registered in `core/observability/metrics.py`:

| Metric                        | Labels                                             | Emitted by           |
| ----------------------------- | -------------------------------------------------- | -------------------- |
| `sell_veto_triggered`         | `creator_id`, `priority` (P1/P2), `reason`         | `veto_layer.py`      |
| `sell_arbitration_resolved`   | `creator_id`, `priority` (P3…P7), `directive`, `reason` | `arbitration_layer.py` |
| `sell_resolver_total`         | `creator_id`, `layer` (veto/arbitration), `directive`   | `resolver.py`        |

Logs: resolver uses a 4-byte `blake2b` hash for `creator_id` in log lines
(`creator_hash=<8 hex chars>`) to cap log volume; full `creator_id` remains
in Prometheus labels for dashboards.

## References

- Research: `docs/research/multi_signal_arbitration_review.md` (main `2f71badc`)
- Design: `docs/audit_sprint5/s6_rematrix/sales_arbitration_design.md`
- Forensic analysis: `docs/audit_sprint5/s6_rematrix/sales_arbitration_analysis.md`
- Audit prioritization: commit `d5616c68` (s6 re-matrix decisions)
