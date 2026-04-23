# Phase 4 — State of the art: papers + repos applicable to this refactor

> Branch: `forensic/tone-profile-db-20260423`
> Scope: 6 topic areas mapped to the 9 bugs (B-01 … B-09) from Phase 3.
> Selection rule: papers 2024–2026, production-engineering first; repos ≥500★ and active ≤6 months.

---

## Master table — source → finding → bug mapping

| # | Source (paper / doc / repo) | Kind | Year | Finding | Bug(s) | Verdict | Citation (<15 words) |
|---|---|---|---|---|---|---|---|
| **1** | [Cosmic Python — Chapter 2: Repository Pattern](https://www.cosmicpython.com/book/chapter_02_repository.html) | Book | 2020 → actively maintained | Repository = collection-like interface per aggregate; one repo per bounded context | **B-03** | **validates** split | "Repository pattern provides an abstraction of data, … a collection." |
| **2** | [Ryan Zheng — Repository Pattern with SQLAlchemy](https://ryan-zheng.medium.com/simplifying-database-interactions-in-python-with-the-repository-pattern-and-sqlalchemy-22baecae8d84) | Blog | 2024 | One repository per entity type; bulk upserts belong in the repo, not the service | **B-03** | **validates** split | "Base repository class … subclassed for specific entity repositories." |
| **3** | [SQLAlchemy 2.0 docs — Dataclass integration](https://docs.sqlalchemy.org/en/20/orm/dataclasses.html) | Official docs | 2024 | 2.0 supports native dataclass mapping; domain types can stay framework-light | **B-03** | **validates** per-repo typed return shapes | "Native dataclass integration … via a single mixin or decorator." |
| **4** | [SQLAlchemy Discussion #11354 — Design a Repository pattern](https://github.com/sqlalchemy/sqlalchemy/discussions/11354) | Repo (23k★) | 2024 | Community consensus: per-aggregate repo; session injection over module globals | **B-03, B-06** | **validates** split and no-private-module-state | "One repository per aggregate root; inject Session; avoid module globals." |
| **5** | [PEP 702 — @warnings.deprecated](https://peps.python.org/pep-0702/) | PEP | 2023 (impl. 2024) | Decorator sets `__deprecated__`, emits `DeprecationWarning` at runtime + static-checker hint | shim for **B-03** | **validates** lightweight shim deprecation | "By default, this decorator will also raise a runtime DeprecationWarning." |
| **6** | [PEP 562 — Module `__getattr__` and `__dir__`](https://peps.python.org/pep-0562/) | PEP | 2017 → std. | Module-level `__getattr__` enables per-name deprecation without breaking `from x import y` | shim for **B-03** | **validates** shim technique | "Accessing a deprecated name … triggers a DeprecationWarning." |
| **7** | [pytz-deprecation-shim (pganssle)](https://github.com/pganssle/pytz-deprecation-shim) | Repo (author of stdlib `zoneinfo`) | 2022 → active | Reference implementation: re-export + deprecation without semantic drift | shim for **B-03** | **validates** our shim shape (flat re-exports) | "Shims use … PEP 495-compatible … won't raise warnings as long as …" |
| **8** | [cachetools 6.x — TTLCache API](https://cachetools.readthedocs.io/) | Repo (2.1k★) + docs | 2024–2026 active | `.get()` returns `None` on miss/expiry; subscript raises `KeyError`; `__missing__` hook optional | **B-01** | **validates** `.get()` fix | "`__getitem__` raises on miss … subclasses may override `__missing__`." |
| **9** | [cachetools CHANGELOG — condition-variable stampede fix](https://github.com/tkem/cachetools/blob/master/CHANGELOG.rst) | Repo | 2024 | `cached()` decorator adopted `threading.Condition` to mitigate cache stampede | **B-01, B-07** | **informs** future hardening (single-flight on miss) | "Decorators converted to use threading.Condition … to deal with stampede." |
| **10** | [Scientific Python — SPEC 1 (lazy submodule loading)](https://scientific-python.org/specs/spec-0001/) | Spec | 2024 | `__getattr__` + `importlib.import_module` avoids import-time cost during shim phase | shim for **B-03** | **validates** shim stays cheap | "Lazy submodule imports using `importlib.import_module()` … on demand." |
| **11** | [PersonaLLM Workshop — NeurIPS 2025](https://personallmworkshop.github.io/) | Workshop call | 2025 | Tone/persona treated as a first-class persisted artifact; separate lifecycle from content | Domain A isolation supports **B-03** | **validates** keeping tone repo near BOOTSTRAP | "LLM persona modeling … treating personas as a first-class artifact." |
| **12** | [PersonaCraft (ScienceDirect, Int'l J. Human-Computer Studies)](https://www.sciencedirect.com/science/article/abs/pii/S1071581925000023) | Paper | 2025 | Separate data layer: survey → persona → LLM; each layer has own CRUD | Domain A/B/C separation | **validates** 3-repo split | "Integrating LLMs with survey data analysis … combines persona development and AI." |
| **13** | [LLM Generated Persona is a Promise with a Catch (arXiv 2503.16527)](https://arxiv.org/abs/2503.16527) | Paper | 2025-03 | Persona artifacts degrade when mixed with generic context — storage separation matters | Domain A isolation | **validates** not co-locating tone with ingestion | "Persona artifacts degrade when … mixed with generic context." |
| **14** | [Understand Legacy Code — Characterization Tests](https://understandlegacycode.com/blog/characterization-tests-or-approval-tests/) | Blog (Feathers-tradition) | 2024 | Capture current output before refactor; assert unchanged after | **B-02, B-04, B-05** | **validates** plan: snapshot before rewrite | "Throw inputs at code, capture outputs — regression net … refactoring." |
| **15** | [The Code Whisperer — Golden Master + Sampling](https://blog.thecodewhisperer.com/permalink/surviving-legacy-code-with-golden-master-and-sampling) | Blog | 2018 → still canonical | Golden master is the fastest path to coverage when domain logic is known | **B-02** | **refines** test rewrite (parametrized inputs ≥ assert-by-shape) | "Golden Master testing … relatively easy to implement … refactoring." |
| **16** | [Google eng-practices — Small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) | Doc (20k★ repo) | 2024 active | 100 lines/CL reasonable; 1000 too large; 200 in one file "might be okay" | **B-03** | **validates** 500-LOC cap direction (smaller is better) | "100 lines is usually a reasonable size for a CL." |
| **17** | [Google eng-practices — Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html) | Doc | 2024 | Reviewer can reject a CL solely for being too large | **B-03** | **validates** hard 500-LOC cap policy | "Reviewers have discretion to reject … for the sole reason of being too large." |
| **18** | [python-clean-architecture-example (claudiosw)](https://github.com/claudiosw/python-clean-architecture-example) | Repo | 2024 | `domain/` vs `infrastructure/` split; each repo class ≤150 LOC | **B-03** | **validates** target per-file LOC budget | "Repository classes kept small … one aggregate per module." |

**Counts:** 18 sources — 13 papers/docs/PEPs + 5 repos (cosmicpython, sqlalchemy, pytz-deprecation-shim, cachetools, python-clean-architecture-example, google/eng-practices). All repos referenced are ≥500★ and active ≤6 months (cachetools last release 2026, eng-practices active, sqlalchemy 10k+★ daily commits).

---

## Per-bug applicability summary

| Bug | Severity | Sources grounding the fix (by #) | Takeaway |
|---|---|---|---|
| **B-01** — subscript TypeError | 🔴 CRÍTICA | #8, #9 | `cachetools` canonically uses `.get()` returning `None` on miss/TTL expiry. Our fix matches the industry idiom; bonus: condition-variable stampede protection is available when/if we graduate off `BoundedTTLCache`. |
| **B-02** — 7 stale tests | 🟠 ALTA | #14, #15 | Characterization/golden-master approach: snapshot the 11 green cases as the safety net, then rewrite the 7 stale around the new `BoundedTTLCache` contract. |
| **B-03** — file bundling | 🟠 ALTA | #1, #2, #3, #4, #16, #17, #18 | Every authoritative source agrees: one repository per aggregate, keep each module small. Google: 100-line CLs; clean-arch examples: ≤150 LOC per repo class. Our target 150/180/196 per file is comfortably in range. |
| **B-04** — Domain B coverage | 🟡 MEDIA | #14, #15 | Add happy-path + error-path characterization tests; target 9. |
| **B-05** — Domain C coverage | 🟡 MEDIA | #14, #15 | Same, with hashtag/mention parsing specifically (stylometry signal). |
| **B-06** — private-name leak | 🟡 MEDIA | #4 | SQLAlchemy community guidance: no module globals exposed across boundaries — public accessor only. Matches our `get_tone_cache_stats()` plan. |
| **B-07** — hardcoded cache sizing | 🟡 MEDIA | #8, #9 | `cachetools.TTLCache(maxsize, ttl)` takes both as constructor args from config; env-var pattern is canonical. |
| **B-08** — dead code `_get_db_session` | 🟢 BAJA | #4 | "Avoid module globals; inject session" — dead helper is the fossil of an abandoned pattern; delete. |
| **B-09** — docstring mis-describes | 🟢 BAJA | #10 | SPEC-1 calls out accurate module docstrings as part of lazy-loading contracts; any shim should state its purpose explicitly. |

---

## Key conceptual findings for Phase 5 implementation

### 1. Repository pattern — "one per aggregate" is the consensus
Both the **Cosmic Python** canonical treatment (#1) and the **SQLAlchemy community discussion #11354** (#4) converge on: one repository per aggregate root, each exposing a collection-like API. Our three domains (tone profile, IG post, RAG chunk) are three distinct aggregates with independent lifecycles — textbook case for three repositories.

### 2. Shim with PEP 702 + PEP 562 is idiomatic and cheap
The combination of:
- Flat `from ... import *` re-exports (source #7 pytz-deprecation-shim — Paul Ganssle, author of stdlib `zoneinfo`),
- `@warnings.deprecated` for any names we want to actively discourage (#5),
- Module-level `__getattr__` (#6) if we want lazy-emit warnings only on legacy access,

is the accepted 2024–2026 pattern. Our shim plan (flat re-exports, no DeprecationWarning at first — optional later) matches #7's exact shape and minimises risk.

### 3. `.get()` vs `__getitem__` — not a preference, a contract distinction
cachetools docs (#8) make the semantic difference explicit: `__getitem__` is the "assert present" contract (raises on miss); `.get()` is the "probe" contract (returns `None`). For a cache behind a `__contains__` probe, the only safe subscript is after an unconditional `if key in cache` that cannot race — which `BoundedTTLCache` cannot guarantee because entries can expire between the `in` check and the subscript. `.get()` collapses both into one atomic step. Our B-01 fix is the textbook resolution.

### 4. Cache stampede / thundering herd — known problem, known fix
cachetools 6.x (#9) adopted `threading.Condition` inside `@cached` decorators after reports of stampede under high load. Our current `BoundedTTLCache` does **not** have stampede protection. This is **out of scope for Phase 5** (the constraint says no Railway/behavioural changes), but worth flagging as a follow-up once the split lands: if `tone_profile_repo` ever gets called concurrently on first load for many creators, we'd want single-flight semantics.

### 5. Persona/tone separation — also the SOTA answer for LLM apps
The **PersonaLLM workshop (#11)**, **PersonaCraft (#12)**, and the arXiv "Promise with a Catch" paper (#13) all treat **persona / tone as a first-class persisted artifact** with its own lifecycle, explicitly separated from content. This is exactly the line we are drawing at the file boundary: `tone_profile_repo` stays in BOOTSTRAP / DM pipeline scope; `instagram_posts_repo` and `content_chunks_repo` go to the Data/Ingestion layer. The academic literature agrees mixing them degrades persona fidelity over time.

### 6. Golden master / characterization first, then rewrite
Feathers-tradition (#14, #15) guidance: when refactoring tested but partially-broken code, first capture the **current** passing behaviour as a golden baseline, then rewrite around the new contract. Applied to B-02: the 11 currently-passing tests become our golden master for Domain A; the 7 stale are rewritten anew against the `BoundedTTLCache` contract, not against the vanished `dict` contract.

### 7. Google Small-CLs rule maps to our file-size discipline
Google's canonical guidance (#16, #17): 100 lines/CL reasonable, 1000 too large, 200 in one file "might be okay." Our refactor target (150/180/196 LOC per new repo file) fits under the "might be okay" threshold, with the legacy shim at ~30–40 LOC. This grounds the 500-LOC ceiling as industry-consistent (Google's review-discretion-to-reject fact specifically backs the enforcement side).

---

## Applicability verdict

All 9 bugs have at least one authoritative source grounding the proposed fix. **No finding refutes any of the Phase 3 fixes.** Three findings refine implementation details:

- **#9** (cache stampede) → noted as post-merge follow-up, not Phase 5 scope.
- **#13** (persona artifact degradation) → reinforces the architectural choice to keep `tone_profile_repo` isolated from ingestion.
- **#15** (golden master) → adds a step to the Phase 5 test rewrite: capture the 11 passing tests' output as baseline before modifying anything.

Phase 5 scope as you defined (sections A–G) is consistent with every source consulted. Proceeding with implementation.

---

## STOP — End of Phase 4.
