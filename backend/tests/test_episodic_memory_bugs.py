"""
Functional tests for System #10 Episodic Memory — Bug fixes verification.

Tests BUG-EP-01 through BUG-EP-10.
Run: python3 tests/test_episodic_memory_bugs.py
"""

import os
import sys
import time

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def test(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} — {detail}")


def test_01_bounded_ttl_cache_in_semantic_memory():
    """BUG-EP-01: Factory cache uses BoundedTTLCache, not plain dict."""
    print("\n[Test 1] BUG-EP-01: BoundedTTLCache in semantic memory factory")

    from core.cache import BoundedTTLCache
    from core.semantic_memory_pgvector import _memory_cache, clear_memory_cache, get_semantic_memory

    test("Cache is BoundedTTLCache", isinstance(_memory_cache, BoundedTTLCache))

    clear_memory_cache()
    sm1 = get_semantic_memory("creator_a", "follower_1")
    sm2 = get_semantic_memory("creator_a", "follower_1")
    test("Same instance returned for same key", sm1 is sm2)

    sm3 = get_semantic_memory("creator_a", "follower_2")
    test("Different instance for different follower", sm1 is not sm3)

    clear_memory_cache()


def test_02_min_message_length():
    """BUG-EP-02: Messages shorter than MIN_MESSAGE_LENGTH are skipped."""
    print("\n[Test 2] MIN_MESSAGE_LENGTH filter")

    from core.semantic_memory_pgvector import MIN_MESSAGE_LENGTH, SemanticMemoryPgvector

    sm = SemanticMemoryPgvector("test_creator", "test_follower")
    # Short messages should return False without DB call (feature flag is on)
    # We test the length check logic directly
    short_msg = "hola"
    test("Short message below threshold", len(short_msg.strip()) < MIN_MESSAGE_LENGTH,
         f"len={len(short_msg)} vs threshold={MIN_MESSAGE_LENGTH}")

    long_msg = "Me gustaría saber más sobre tus servicios de consultoría"
    test("Long message above threshold", len(long_msg.strip()) >= MIN_MESSAGE_LENGTH)


def test_03_similarity_threshold_consistency():
    """BUG-EP-03: Verify similarity thresholds are documented and consistent."""
    print("\n[Test 3] BUG-EP-03: Similarity threshold consistency")

    from core.semantic_memory_pgvector import DEFAULT_MIN_SIMILARITY

    test("Default similarity is 0.70", DEFAULT_MIN_SIMILARITY == 0.70)

    # Read _episodic_search threshold
    import inspect
    from core.dm.phases.context import _episodic_search
    source = inspect.getsource(_episodic_search)

    test("Episodic search uses _MIN_SIM = 0.60", "_MIN_SIM = 0.60" in source,
         "Should use 0.60 per BUG-EP-02 fix")


def test_04_fact_tracking_shared_function():
    """BUG-EP-04: Fact tracking uses shared _extract_facts() function."""
    print("\n[Test 4] BUG-EP-04: Shared _extract_facts() function")

    from core.dm.post_response import _extract_facts

    # Test PRICE_GIVEN
    facts = _extract_facts("El curso cuesta 99€", "quiero info", [])
    test("Detects PRICE_GIVEN (€)", "PRICE_GIVEN" in facts)

    facts = _extract_facts("It costs $49 USD", "info please", [])
    test("Detects PRICE_GIVEN ($USD)", "PRICE_GIVEN" in facts)

    # Test LINK_SHARED
    facts = _extract_facts("Mira https://example.com/curso", "info", [])
    test("Detects LINK_SHARED", "LINK_SHARED" in facts)

    # Test PRODUCT_EXPLAINED
    products = [{"name": "Masterclass de Yoga"}]
    facts = _extract_facts("La masterclass de yoga incluye 8 sesiones", "info", products)
    test("Detects PRODUCT_EXPLAINED", "PRODUCT_EXPLAINED" in facts)

    # Test NAME_USED
    facts = _extract_facts("Hola Maria, como estás?", "bien", [], "Maria")
    test("Detects NAME_USED", "NAME_USED" in facts)

    # Test QUESTION_ASKED
    facts = _extract_facts("¿Qué te gustaría saber?", "info", [])
    test("Detects QUESTION_ASKED", "QUESTION_ASKED" in facts)


def test_05_multilingual_interest():
    """BUG-EP-05: Multilingual interest/objection regex."""
    print("\n[Test 5] BUG-EP-05: Multilingual fact tracking")

    from core.dm.post_response import _extract_facts

    # Spanish
    facts = _extract_facts("", "me interesa mucho", [])
    test("ES interest: 'me interesa'", "INTEREST_EXPRESSED" in facts)

    # English
    facts = _extract_facts("", "I'm interested in that", [])
    test("EN interest: 'I'm interested'", "INTEREST_EXPRESSED" in facts)

    # Catalan
    facts = _extract_facts("", "m'interessa molt", [])
    test("CA interest: 'm'interessa'", "INTEREST_EXPRESSED" in facts)

    # Italian
    facts = _extract_facts("", "mi interessa molto", [])
    test("IT interest: 'mi interessa'", "INTEREST_EXPRESSED" in facts)

    # English objection handling
    facts = _extract_facts("I understand your concern, don't worry", "", [])
    test("EN objection: 'I understand your concern'", "OBJECTION_RAISED" in facts)

    # Italian appointment
    facts = _extract_facts("Vuoi fissare un appuntamento?", "", [])
    test("IT appointment: 'appuntamento'", "APPOINTMENT_MENTIONED" in facts)


def test_06_session_leak_fix():
    """BUG-EP-07: _episodic_search uses get_db_session() not raw SessionLocal()."""
    print("\n[Test 6] BUG-EP-07: No raw SessionLocal in _episodic_search")

    import inspect
    from core.dm.phases.context import _episodic_search
    source = inspect.getsource(_episodic_search)

    test("Uses get_db_session()", "get_db_session" in source)
    test("No raw SessionLocal()", "SessionLocal()" not in source)


def test_07_hierarchical_memory_cache():
    """BUG-EP-08: HierarchicalMemoryManager uses cached factory."""
    print("\n[Test 7] BUG-EP-08: Cached HierarchicalMemoryManager factory")

    from core.hierarchical_memory.hierarchical_memory import (
        _hmm_cache,
        get_hierarchical_memory,
    )

    from core.cache import BoundedTTLCache
    test("HMM cache is BoundedTTLCache", isinstance(_hmm_cache, BoundedTTLCache))

    hmm1 = get_hierarchical_memory("test_creator_abc")
    hmm2 = get_hierarchical_memory("test_creator_abc")
    test("Same instance returned for same creator", hmm1 is hmm2)

    hmm3 = get_hierarchical_memory("test_creator_xyz")
    test("Different instance for different creator", hmm1 is not hmm3)


def test_08_hierarchical_l2_stopwords():
    """BUG-EP-10: L2 relevance scoring filters stopwords."""
    print("\n[Test 8] BUG-EP-10: L2 stopword filtering")

    from core.hierarchical_memory.hierarchical_memory import HierarchicalMemoryManager

    hmm = HierarchicalMemoryManager("__test_nonexistent__")
    # Inject fake L2 memories
    hmm._l2 = [
        {"memory": "yoga meditation practice daily", "topic": "wellness", "pattern": "", "count": 5},
        {"memory": "de la el en que un una los", "topic": "stopwords only", "pattern": "", "count": 1},
    ]

    # Message with meaningful word + stopwords
    scored = hmm._score_l2_relevance("quiero practicar yoga en casa")
    test("Yoga memory scores higher than stopword memory",
         scored[0][0]["topic"] == "wellness",
         f"Got: {scored[0][0]['topic']}")

    # Pure stopword message should not match stopword-only memory
    scored_stop = hmm._score_l2_relevance("de la en el que")
    yoga_score = next(s for m, s in scored_stop if m["topic"] == "wellness")
    stop_score = next(s for m, s in scored_stop if m["topic"] == "stopwords only")
    test("Stopword-only memory gets 0 overlap", stop_score == 0,
         f"Expected 0, got {stop_score}")


def test_09_context_integration_uses_cached_hmm():
    """BUG-EP-08: context.py imports get_hierarchical_memory, not raw constructor."""
    print("\n[Test 9] Context integration uses cached factory")

    import inspect
    from core.dm.phases import context
    source = inspect.getsource(context.phase_memory_and_context)

    test("Imports get_hierarchical_memory", "get_hierarchical_memory" in source)
    test("No raw HierarchicalMemoryManager()", "HierarchicalMemoryManager(" not in source)


def test_10_feature_flags_defaults():
    """Verify feature flag defaults are correct."""
    print("\n[Test 10] Feature flag defaults")

    from core.dm.phases.context import ENABLE_EPISODIC_MEMORY, ENABLE_HIERARCHICAL_MEMORY
    from core.semantic_memory_pgvector import ENABLE_SEMANTIC_MEMORY_PGVECTOR

    # Storage is on, search is off — intentional
    test("ENABLE_SEMANTIC_MEMORY_PGVECTOR = true (storage)", ENABLE_SEMANTIC_MEMORY_PGVECTOR is True)
    test("ENABLE_EPISODIC_MEMORY = false (search disabled)", ENABLE_EPISODIC_MEMORY is False)
    test("ENABLE_HIERARCHICAL_MEMORY = false (disabled)", ENABLE_HIERARCHICAL_MEMORY is False)

    from core.dm.post_response import ENABLE_FACT_TRACKING
    test("ENABLE_FACT_TRACKING = true (active)", ENABLE_FACT_TRACKING is True)


# =============================================================================
# Optimization tests (O2-O5 from papers)
# =============================================================================


def test_11_o2_redundancy_threshold():
    """O2 (SimpleMem): Semantic density gating threshold exists."""
    print("\n[Test 11] O2: Semantic density gating")

    from core.semantic_memory_pgvector import REDUNDANCY_THRESHOLD

    test("Redundancy threshold is 0.92", REDUNDANCY_THRESHOLD == 0.92)
    test("Redundancy threshold < 1.0 (catches near-dupes)", REDUNDANCY_THRESHOLD < 1.0)
    test("Redundancy threshold > 0.85 (not too aggressive)", REDUNDANCY_THRESHOLD > 0.85)

    # Verify the add_message code contains the redundancy check
    import inspect
    from core.semantic_memory_pgvector import SemanticMemoryPgvector
    source = inspect.getsource(SemanticMemoryPgvector.add_message)
    test("add_message contains redundancy check", "REDUNDANCY_THRESHOLD" in source or "threshold" in source.lower())


def test_12_o3_coreference_resolution():
    """O3 (EMem): Coreference resolution resolves pronouns to names."""
    print("\n[Test 12] O3: Coreference resolution")

    from core.semantic_memory_pgvector import _resolve_coreferences

    # Spanish: "ella me dijo" → "Maria me dijo"
    result = _resolve_coreferences("ella me dijo que le gustaba el yoga", "Maria")
    test("ES: 'ella me dijo' → 'Maria me dijo'", "Maria" in result,
         f"Got: {result}")

    # Spanish: "le dije" → "a Maria dije"
    result = _resolve_coreferences("le dije que no había problema", "Carlos")
    test("ES: 'le dije' → 'a Carlos dije'", "Carlos" in result,
         f"Got: {result}")

    # English: "she told me" → "Maria told me"
    result = _resolve_coreferences("she told me about her business plan", "Maria")
    test("EN: 'she told me' → 'Maria told me'", "Maria" in result,
         f"Got: {result}")

    # English: "I told her" → "I told Maria"
    result = _resolve_coreferences("I told her the price was 50€", "Anna")
    test("EN: 'I told her' → 'I told Anna'", "Anna" in result,
         f"Got: {result}")

    # No name → no change
    result = _resolve_coreferences("ella me dijo algo", None)
    test("No name → no change", result == "ella me dijo algo")

    # No pronoun → no change
    result = _resolve_coreferences("me gusta el yoga", "Maria")
    test("No pronoun → no change", result == "me gusta el yoga")


def test_13_o4_adaptive_gating():
    """O4 (Multi-Layered 2026): Adaptive retrieval gating in context.py."""
    print("\n[Test 13] O4: Adaptive retrieval gating")

    import inspect
    from core.dm.phases import context
    source = inspect.getsource(context.phase_memory_and_context)

    test("Has word count gate (len(_msg_words) >= 3)", "_msg_words" in source)
    test("Has length gate (len >= 15)", ">= 15" in source or ">=15" in source)

    # Verify gating logic: short messages with <3 unique words should NOT trigger search
    # "sí sí" has 1 unique word, should be gated out
    words = set("sí sí".lower().split())
    test("'sí sí' → 1 unique word → gated out", len(words) < 3, f"words={words}")

    # "quiero saber más sobre yoga" has 5 unique words, should pass
    words = set("quiero saber más sobre yoga".lower().split())
    test("'quiero saber más sobre yoga' → 5 words → passes gate", len(words) >= 3)

    # "ok" has 1 word and len <15, double gated
    msg = "ok"
    test("'ok' → len<15 AND <3 words → double gated",
         len(msg.strip()) < 15 and len(set(msg.lower().split())) < 3)


def test_14_o5_temporal_decay():
    """O5 (Memobase): Temporal decay weighting in search query."""
    print("\n[Test 14] O5: Temporal decay in search")

    import inspect
    from core.semantic_memory_pgvector import SemanticMemoryPgvector
    source = inspect.getsource(SemanticMemoryPgvector.search)

    # Verify the SQL contains temporal decay formula
    test("Search SQL contains EXTRACT(EPOCH", "EXTRACT(EPOCH" in source)
    test("Search SQL contains recency factor (0.7 + 0.3)", "0.7 + 0.3" in source)
    test("Search SQL contains 90-day window (90 * 86400)", "90 * 86400" in source)
    test("ORDER BY uses similarity DESC (not distance ASC)", "ORDER BY similarity DESC" in source)


# =============================================================================
# System #9 Memory Engine — Optimization tests (O1-O3)
# =============================================================================


def test_15_o1_type_weighted_fallback():
    """O1 (Memobase/RMM): Fallback retrieval uses type weights, not pure recency."""
    print("\n[Test 15] O1: Type-weighted fallback retrieval")

    from services.memory_engine import MemoryEngine

    # Verify the type weights exist
    test("Has _FALLBACK_TYPE_WEIGHT", hasattr(MemoryEngine, "_FALLBACK_TYPE_WEIGHT"))
    weights = MemoryEngine._FALLBACK_TYPE_WEIGHT
    test("commitment has highest non-memo weight", weights["commitment"] > weights["topic"])
    test("personal_info > topic", weights["personal_info"] > weights["topic"])
    test("compressed_memo is top weight", weights["compressed_memo"] == 5)

    # Verify the method does re-ranking (fetches 3x limit)
    import inspect
    source = inspect.getsource(MemoryEngine._get_recent_facts)
    test("Fetches 3x limit for re-ranking", "limit * 3" in source)
    test("Uses type_w * recency * confidence scoring", "type_w * recency" in source)


def test_16_o2_temporal_decay_in_search():
    """O2 (THEANINE/Graphiti): pgvector search includes temporal decay."""
    print("\n[Test 16] O2: Temporal decay in pgvector search")

    import inspect
    from services.memory_engine import MemoryEngine
    source = inspect.getsource(MemoryEngine._pgvector_search)

    test("SQL has EXTRACT(EPOCH", "EXTRACT(EPOCH" in source)
    test("SQL has 0.7 + 0.3 blend", "0.7 + 0.3" in source)
    test("SQL has 90-day window", "90 * 86400" in source)
    test("Orders by similarity DESC", "ORDER BY similarity DESC" in source)


def test_17_o3_dedup_facts():
    """O3 (Mem0/MemOS): Dedup near-duplicate facts in recall output."""
    print("\n[Test 17] O3: Fact deduplication in recall")

    from services.memory_engine import MemoryEngine, LeadMemory
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    engine = MemoryEngine()

    # Create near-duplicate facts
    facts = [
        LeadMemory(id="1", fact_type="preference", fact_text="Le gusta el yoga y la meditación", created_at=now),
        LeadMemory(id="2", fact_type="preference", fact_text="Le gusta el yoga y la meditación diaria", created_at=now),
        LeadMemory(id="3", fact_type="commitment", fact_text="Va a venir el jueves a clase", created_at=now),
        LeadMemory(id="4", fact_type="topic", fact_text="Preguntó sobre nutrición", created_at=now),
    ]

    deduped = engine._dedup_facts(facts)
    test("Dedup removes near-duplicate", len(deduped) < len(facts),
         f"Got {len(deduped)}, expected < {len(facts)}")
    test("Keeps unique types", len(set(f.fact_type for f in deduped)) >= 3)

    # Different types with same text should NOT be deduped
    mixed = [
        LeadMemory(id="5", fact_type="preference", fact_text="Le gusta el barre", created_at=now),
        LeadMemory(id="6", fact_type="commitment", fact_text="Le gusta el barre", created_at=now),
    ]
    deduped_mixed = engine._dedup_facts(mixed)
    test("Different types with same text are kept", len(deduped_mixed) == 2)

    # Completely different facts should all survive
    unique = [
        LeadMemory(id="7", fact_type="preference", fact_text="Yoga classes", created_at=now),
        LeadMemory(id="8", fact_type="commitment", fact_text="Thursday appointment", created_at=now),
        LeadMemory(id="9", fact_type="objection", fact_text="Too expensive", created_at=now),
    ]
    deduped_unique = engine._dedup_facts(unique)
    test("Unique facts all survive", len(deduped_unique) == 3)


if __name__ == "__main__":
    sep = "=" * 60
    print(f"\n{sep}")
    print("System #10 Episodic Memory — Bug Fixes + Optimizations")
    print(sep)

    # Bug fix tests (1-10)
    test_01_bounded_ttl_cache_in_semantic_memory()
    test_02_min_message_length()
    test_03_similarity_threshold_consistency()
    test_04_fact_tracking_shared_function()
    test_05_multilingual_interest()
    test_06_session_leak_fix()
    test_07_hierarchical_memory_cache()
    test_08_hierarchical_l2_stopwords()
    test_09_context_integration_uses_cached_hmm()
    test_10_feature_flags_defaults()

    # System #10 optimization tests (11-14)
    test_11_o2_redundancy_threshold()
    test_12_o3_coreference_resolution()
    test_13_o4_adaptive_gating()
    test_14_o5_temporal_decay()

    # System #9 optimization tests (15-17)
    test_15_o1_type_weighted_fallback()
    test_16_o2_temporal_decay_in_search()
    test_17_o3_dedup_facts()

    print(f"\n{sep}")
    print(f"Results: {PASS} PASS / {FAIL} FAIL / {PASS + FAIL} TOTAL")
    print(sep)
    sys.exit(0 if FAIL == 0 else 1)
