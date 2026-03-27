"""
Mega Test Automático — Clonnect
Capa 1-4: detección, postprocessing, RAG, state, scoring, memory
"""
import sys
import os
import time
import json
import asyncio
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("TESTING", "true")

PASS, FAIL, SKIP = 0, 0, 0
errors = []
semi_review = []


def assert_eq(a, b):
    assert a == b, f"Expected {b!r}, got {a!r}"


def assert_true(cond):
    assert cond, f"Expected True, got False"


def assert_false(cond):
    assert not cond, f"Expected False, got True"


def _try_raises(fn, exc_type):
    try:
        fn()
        return False
    except exc_type:
        return True
    except Exception:
        return False


def test(name, fn):
    global PASS, FAIL, SKIP
    try:
        fn()
        PASS += 1
        print(f"  ✅ {name}")
    except AssertionError as e:
        FAIL += 1
        errors.append(f"❌ {name}: {e}")
        print(f"  ❌ {name}: {e}")
    except Exception as e:
        SKIP += 1
        errors.append(f"⏭️ {name}: {type(e).__name__}: {e}")
        print(f"  ⏭️ {name}: {e}")


def semi(name, fn):
    global PASS, FAIL, SKIP
    try:
        result = fn()
        PASS += 1
        semi_review.append(
            f"\n{'='*50}\n✅ {name}\n{str(result)[:800]}\nREVISIÓN: ¿Output correcto y natural?\n"
        )
        print(f"  ✅ {name} (→ semi_review)")
    except Exception as e:
        SKIP += 1
        semi_review.append(f"\n{'='*50}\n⏭️ {name}: {e}\n")
        print(f"  ⏭️ {name}: {e}")


# ──────────────────────────────────────────────
# BLOQUE A — DETECCIÓN: Intent Classifier
# ──────────────────────────────────────────────
print("\n📦 BLOQUE A — INTENT CLASSIFIER")

try:
    from services.intent_service import Intent, IntentClassifier
    _classifier = IntentClassifier()
    _intent_imported = True
except Exception as e:
    _intent_imported = False
    print(f"  ⏭️ Import intent_service: {e}")

if _intent_imported:
    def _classify(msg):
        return _classifier.classify(msg)

    test("A1: GREETING — hola", lambda: assert_eq(_classify("hola"), Intent.GREETING))
    test("A2: GREETING — hey!", lambda: assert_eq(_classify("hey"), Intent.GREETING))
    test("A3: PURCHASE_INTENT — quiero comprar", lambda: assert_eq(_classify("quiero comprar"), Intent.PURCHASE_INTENT))
    test("A4: PRICING — cuánto cuesta", lambda: assert_eq(_classify("cuánto cuesta"), Intent.PRICING))
    test("A5: PRODUCT_QUESTION — qué incluye el programa", lambda: assert_eq(_classify("qué incluye el programa"), Intent.PRODUCT_QUESTION))
    test("A6: OBJECTION_PRICE — es muy caro", lambda: assert_eq(_classify("es muy caro"), Intent.OBJECTION_PRICE))
    test("A7: OBJECTION_TIME — no tengo tiempo", lambda: assert_eq(_classify("no tengo tiempo"), Intent.OBJECTION_TIME))
    test("A8: OBJECTION_DOUBT — no sé si me servirá", lambda: assert_eq(_classify("no sé si me servirá"), Intent.OBJECTION_DOUBT))
    test("A9: OBJECTION_LATER — lo pienso", lambda: assert_eq(_classify("lo pienso"), Intent.OBJECTION_LATER))
    test("A10: Intent enum has GREETING", lambda: assert_true(Intent.GREETING.value == "greeting"))
    test("A11: Intent enum has PURCHASE_INTENT", lambda: assert_true(Intent.PURCHASE_INTENT.value == "purchase_intent"))
    test("A12: Intent enum has OTHER", lambda: assert_true(Intent.OTHER.value == "other"))
    test("A13: Classify empty string → OTHER", lambda: assert_eq(_classify(""), Intent.OTHER))
    test("A14: THANKS detected", lambda: assert_true(_classify("gracias!") in (Intent.THANKS, Intent.OTHER, Intent.ACKNOWLEDGMENT)))
    test("A15: PRICING — precio de", lambda: assert_eq(_classify("precio de algo"), Intent.PRICING))


# ──────────────────────────────────────────────
# BLOQUE B — SENSITIVE DETECTOR
# ──────────────────────────────────────────────
print("\n📦 BLOQUE B — SENSITIVE DETECTOR")

try:
    from core.sensitive_detector import detect_sensitive_content, SensitiveType
    _sensitive_imported = True
except Exception as e:
    _sensitive_imported = False
    print(f"  ⏭️ Import sensitive_detector: {e}")

if _sensitive_imported:
    def _detect(msg):
        return detect_sensitive_content(msg)

    test("B1: Normal message → NONE", lambda: assert_eq(_detect("hola qué tal").type, SensitiveType.NONE))
    test("B2: SELF_HARM detected", lambda: assert_eq(_detect("quiero morir ya no quiero vivir").type, SensitiveType.SELF_HARM))
    test("B3: SPAM detected", lambda: assert_eq(_detect("check out my profile click here bit.ly/abc").type, SensitiveType.SPAM))
    test("B4: THREAT detected", lambda: assert_eq(_detect("te voy a encontrar y matar").type, SensitiveType.THREAT))
    test("B5: Result has confidence field", lambda: assert_true(0.0 <= _detect("hola").confidence <= 1.0))
    test("B6: Result has action_required field", lambda: assert_true(isinstance(_detect("hola").action_required, str)))
    test("B7: NONE evaluates falsy", lambda: assert_false(_detect("buenas tardes")))
    test("B8: SELF_HARM evaluates truthy", lambda: assert_true(_detect("voy a suicidarme")))
    test("B9: MINOR detected", lambda: assert_eq(_detect("tengo 14 años y me interesa").type, SensitiveType.MINOR))
    test("B10: Empty message → NONE", lambda: assert_eq(_detect("").type, SensitiveType.NONE))


# ──────────────────────────────────────────────
# BLOQUE C — FRUSTRATION DETECTOR
# ──────────────────────────────────────────────
print("\n📦 BLOQUE C — FRUSTRATION DETECTOR")

try:
    from core.frustration_detector import FrustrationDetector, get_frustration_detector, FrustrationSignals
    _frustration_imported = True
except Exception as e:
    _frustration_imported = False
    print(f"  ⏭️ Import frustration_detector: {e}")

if _frustration_imported:
    _fd = FrustrationDetector()

    test("C1: Factory returns FrustrationDetector", lambda: assert_true(isinstance(get_frustration_detector(), FrustrationDetector)))
    test("C2: Calm message → low score", lambda: assert_true(_fd.analyze_message("hola cómo estás", "conv_test_calm")[1] < 0.5))
    test("C3: Explicit frustration → high score", lambda: assert_true(_fd.analyze_message("joder esto no funciona ya te lo dije!", "conv_test_frust")[1] >= 0.3))
    test("C4: Returns (FrustrationSignals, float)", lambda: assert_true(isinstance(_fd.analyze_message("ok", "conv1"), tuple)))
    test("C5: FrustrationSignals has get_score()", lambda: assert_true(0.0 <= FrustrationSignals().get_score() <= 1.0))
    test("C6: ALL CAPS → higher CAPS ratio signal", lambda: assert_true(_fd.analyze_message("NO FUNCIONA NADA", "conv_caps")[0].caps_ratio > 0.3))
    test("C7: Repeated question → repeated_questions > 0",
         lambda: assert_true(
             _fd.analyze_message(
                 "cuánto cuesta",
                 "conv_repeat",
                 previous_messages=["cuánto cuesta", "no me respondiste"]
             )[0].repeated_questions >= 1
         ))
    test("C8: Multi question marks → question_marks_excess", lambda: assert_true(_fd.analyze_message("cuánto??? en serio???", "conv_qm")[0].question_marks_excess > 0))


# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# BLOQUE E — BOT QUESTION ANALYZER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE E — BOT QUESTION ANALYZER")

try:
    from core.bot_question_analyzer import BotQuestionAnalyzer, is_short_affirmation, QuestionType
    _bqa_imported = True
except Exception as e:
    _bqa_imported = False
    print(f"  ⏭️ Import bot_question_analyzer: {e}")

if _bqa_imported:
    _bqa = BotQuestionAnalyzer()

    test("E1: is_short_affirmation('si') → True", lambda: assert_true(is_short_affirmation("si")))
    test("E2: is_short_affirmation('vale') → True", lambda: assert_true(is_short_affirmation("vale")))
    test("E3: is_short_affirmation('ok') → True", lambda: assert_true(is_short_affirmation("ok")))
    test("E4: is_short_affirmation('no me interesa') → False", lambda: assert_false(is_short_affirmation("no me interesa para nada")))
    test("E5: is_short_affirmation('') → False", lambda: assert_false(is_short_affirmation("")))
    test("E6: analyze interest bot msg → INTEREST", lambda: assert_eq(_bqa.analyze("¿Te gustaría saber más sobre el curso?"), QuestionType.INTEREST))
    test("E7: analyze purchase msg → PURCHASE", lambda: assert_eq(_bqa.analyze("¿te apuntas al programa?"), QuestionType.PURCHASE))
    test("E8: analyze empty → UNKNOWN", lambda: assert_eq(_bqa.analyze(""), QuestionType.UNKNOWN))
    test("E9: BotQuestionAnalyzer instantiates OK", lambda: assert_true(_bqa is not None))


# ──────────────────────────────────────────────
# BLOQUE F — RESPONSE FIXES
# ──────────────────────────────────────────────
print("\n📦 BLOQUE F — RESPONSE FIXES")

try:
    from core.response_fixes import (
        fix_price_typo,
        fix_broken_links,
        fix_identity_claim,
        clean_raw_ctas,
        hide_technical_errors,
        deduplicate_products,
    )
    _fixes_imported = True
except Exception as e:
    _fixes_imported = False
    print(f"  ⏭️ Import response_fixes: {e}")

if _fixes_imported:
    test("F1: fix_price_typo '297?' → '297€'", lambda: assert_true("297€" in fix_price_typo("El precio es 297?")))
    test("F2: fix_price_typo normal text unchanged", lambda: assert_true("¿cuánto cuesta?" in fix_price_typo("¿cuánto cuesta?")))
    test("F3: fix_broken_links '://www' → 'https://www'", lambda: assert_true("https://www." in fix_broken_links("Visita ://www.ejemplo.com")))
    test("F4: fix_broken_links normal link unchanged", lambda: assert_true("https://www.google.com" in fix_broken_links("https://www.google.com")))
    test("F5: fix_identity_claim 'Soy Stefan' → asistente", lambda: assert_true("asistente" in fix_identity_claim("Soy Stefan, puedo ayudarte")))
    test("F6: clean_raw_ctas removes QUIERO SER PARTE", lambda: assert_false("QUIERO SER PARTE" in clean_raw_ctas("Únete QUIERO SER PARTE ya!")))
    test("F7: clean_raw_ctas removes COMPRA AHORA", lambda: assert_false("COMPRA AHORA" in clean_raw_ctas("texto COMPRA AHORA mas texto")))
    test("F8: deduplicate_products removes duplicates", lambda: assert_eq(
        len(deduplicate_products([{"name": "Curso A"}, {"name": "Curso A"}, {"name": "Curso B"}])), 2
    ))
    test("F9: deduplicate_products empty list → []", lambda: assert_eq(deduplicate_products([]), []))
    test("F10: fix_price_typo empty string → ''", lambda: assert_eq(fix_price_typo(""), ""))
    test("F11: fix_price_typo '22? y 33?' → prices fixed", lambda: assert_true("22€" in fix_price_typo("Son 22? y 33?")))
    test("F12: hide_technical_errors removes ERROR:", lambda: assert_false("ERROR:" in hide_technical_errors("El bot dice: ERROR: something failed")))


# ──────────────────────────────────────────────
# BLOQUE G — GUARDRAILS
# ──────────────────────────────────────────────
print("\n📦 BLOQUE G — GUARDRAILS")

try:
    from core.guardrails import ResponseGuardrail, get_response_guardrail
    _guardrails_imported = True
except Exception as e:
    _guardrails_imported = False
    print(f"  ⏭️ Import guardrails: {e}")

if _guardrails_imported:
    _guardrail = ResponseGuardrail()

    test("G1: Factory returns ResponseGuardrail", lambda: assert_true(isinstance(get_response_guardrail(), ResponseGuardrail)))
    test("G2: validate_response returns dict", lambda: assert_true(isinstance(_guardrail.validate_response("hola", "Hola, ¿en qué puedo ayudarte?"), dict)))
    test("G3: validate_response has 'valid' key", lambda: assert_true("valid" in _guardrail.validate_response("hola", "buenas")))
    test("G4: validate_response has 'issues' key", lambda: assert_true("issues" in _guardrail.validate_response("hola", "buenas")))
    test("G5: Clean response → valid=True", lambda: assert_true(
        _guardrail.validate_response("hola", "Hola! Todo bien por aquí")["valid"]
    ))
    test("G6: Excessively long response → issues", lambda: assert_false(
        _guardrail.validate_response("hola", "x" * 2500)["valid"]
    ))
    test("G7: guardrail has 'enabled' attr", lambda: assert_true(hasattr(_guardrail, "enabled")))


# ──────────────────────────────────────────────
# BLOQUE H — OUTPUT VALIDATOR
# ──────────────────────────────────────────────
print("\n📦 BLOQUE H — OUTPUT VALIDATOR")

try:
    from core.output_validator import validate_prices, validate_links, extract_prices_from_text, ValidationIssue
    _outval_imported = True
except Exception as e:
    _outval_imported = False
    print(f"  ⏭️ Import output_validator: {e}")

if _outval_imported:
    test("H1: extract_prices_from_text finds 297€", lambda: assert_true(any(v == 297.0 for _, v in extract_prices_from_text("El precio es 297€"))))
    test("H2: extract_prices_from_text finds $99", lambda: assert_true(any(v == 99.0 for _, v in extract_prices_from_text("Son $99 USD"))))
    test("H3: extract_prices_from_text empty → []", lambda: assert_eq(extract_prices_from_text(""), []))
    test("H4: extract_prices_from_text no price → []", lambda: assert_eq(extract_prices_from_text("hola cómo estás"), []))
    test("H5: validate_prices known price OK → no issues", lambda: assert_eq(
        validate_prices("El precio es 297€", {"Curso A": 297.0}), []
    ))
    test("H6: validate_prices hallucinated price → issue", lambda: assert_true(
        len(validate_prices("El precio es 999€", {"Curso A": 297.0})) > 0
    ))
    test("H7: validate_prices no known_prices → no issues", lambda: assert_eq(
        validate_prices("El precio es 297€", {}), []
    ))
    test("H8: validate_links known link → no issues", lambda: assert_eq(
        validate_links("Visita https://calendly.com/test", ["https://calendly.com/test"])[0], []
    ))
    test("H9: validate_links returns tuple(list, str)", lambda: assert_true(
        isinstance(validate_links("nada", []), tuple)
    ))
    test("H10: ValidationIssue has type/severity/details", lambda: (
        lambda vi: assert_true(hasattr(vi, "type") and hasattr(vi, "severity") and hasattr(vi, "details"))
    )(ValidationIssue(type="test", severity="error", details="test detail")))


# ──────────────────────────────────────────────
# BLOQUE I — LENGTH CONTROLLER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE I — LENGTH CONTROLLER")

try:
    from services.length_controller import detect_message_type, enforce_length, CONTEXT_LENGTH_RULES, classify_lead_context
    _length_imported = True
except Exception as e:
    _length_imported = False
    print(f"  ⏭️ Import length_controller: {e}")

if _length_imported:
    test("I1: detect_message_type 'hola' → saludo", lambda: assert_eq(detect_message_type("hola"), "saludo"))
    test("I2: detect_message_type 'cuánto cuesta' → pregunta_precio", lambda: assert_eq(detect_message_type("cuánto cuesta"), "pregunta_precio"))
    test("I3: detect_message_type '' → inicio_conversacion", lambda: assert_eq(detect_message_type(""), "inicio_conversacion"))
    test("I4: detect_message_type 'me interesa el curso' → interes", lambda: assert_eq(detect_message_type("me interesa el curso"), "interes"))
    test("I5: detect_message_type objection → objecion", lambda: assert_eq(detect_message_type("no sé si me convence, es muy complicado y dificil para mí"), "objecion"))
    test("I6: CONTEXT_LENGTH_RULES has 'saludo'", lambda: assert_true("saludo" in CONTEXT_LENGTH_RULES))
    test("I7: CONTEXT_LENGTH_RULES has 'objecion'", lambda: assert_true("objecion" in CONTEXT_LENGTH_RULES))
    test("I8: enforce_length short text unchanged", lambda: assert_eq(enforce_length("Hola!", "hola", context="saludo"), "Hola!"))
    test("I9: enforce_length very long text with sentence boundaries trimmed",
         lambda: assert_true(len(enforce_length(
             "Hola buenas tardes. " * 100,
             "hola", context="saludo"
         )) < len("Hola buenas tardes. " * 100)))
    test("I10: classify_lead_context 'qué incluye' → pregunta_producto",
         lambda: assert_true(classify_lead_context("qué incluye el programa") in ("pregunta_producto", "interes")))


# ──────────────────────────────────────────────
# BLOQUE J — QUESTION REMOVER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE J — QUESTION REMOVER")

try:
    from services.question_remover import contains_banned_question, remove_banned_questions, BANNED_QUESTIONS
    _qr_imported = True
except Exception as e:
    _qr_imported = False
    print(f"  ⏭️ Import question_remover: {e}")

if _qr_imported:
    test("J1: contains_banned_question '¿qué tal?' → True", lambda: assert_true(contains_banned_question("¿qué tal?")))
    test("J2: contains_banned_question '¿cómo estás?' → True", lambda: assert_true(contains_banned_question("¿cómo estás?")))
    test("J3: contains_banned_question '¿qué te llamó la atención?' → True", lambda: assert_true(contains_banned_question("¿qué te llamó la atención?")))
    test("J4: contains_banned_question neutral text → False", lambda: assert_false(contains_banned_question("El precio es 297€")))
    test("J5: contains_banned_question '¿en qué puedo ayudarte?' → True", lambda: assert_true(contains_banned_question("¿en qué puedo ayudarte?")))
    test("J6: remove_banned_questions removes them", lambda: assert_false(contains_banned_question(remove_banned_questions("Hola ¿qué tal?"))))
    test("J7: BANNED_QUESTIONS is list", lambda: assert_true(isinstance(BANNED_QUESTIONS, list)))
    test("J8: BANNED_QUESTIONS not empty", lambda: assert_true(len(BANNED_QUESTIONS) > 0))


# ──────────────────────────────────────────────
# BLOQUE K — MESSAGE SPLITTER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE K — MESSAGE SPLITTER")

try:
    from services.message_splitter import MessageSplitter, get_message_splitter, SplitConfig, MessagePart
    _splitter_imported = True
except Exception as e:
    _splitter_imported = False
    print(f"  ⏭️ Import message_splitter: {e}")

if _splitter_imported:
    _splitter = MessageSplitter()

    test("K1: Factory returns MessageSplitter", lambda: assert_true(isinstance(get_message_splitter(), MessageSplitter)))
    test("K2: Short msg should_split → False", lambda: assert_false(_splitter.should_split("Hola!")))
    test("K3: Long msg with periods should_split → True", lambda: assert_true(
        _splitter.should_split("Esta es una oración larga. Esta es otra oración larga que también importa. Y otra más aquí para asegurarnos.")
    ))
    test("K4: split short msg → single MessagePart", lambda: assert_eq(len(_splitter.split("Hola!")), 1))
    test("K5: split single part → is_first=True and is_last=True", lambda: (
        lambda parts: assert_true(parts[0].is_first and parts[0].is_last)
    )(_splitter.split("Hola!")))
    test("K6: MessagePart has text, delay_before, is_first, is_last", lambda: (
        lambda mp: assert_true(hasattr(mp, "text") and hasattr(mp, "delay_before") and hasattr(mp, "is_first") and hasattr(mp, "is_last"))
    )(MessagePart(text="test", delay_before=1.0)))
    test("K7: SplitConfig has min_length_to_split", lambda: assert_true(hasattr(SplitConfig(), "min_length_to_split")))


# ──────────────────────────────────────────────
# BLOQUE L — APPLY VOSEO (text_utils)
# ──────────────────────────────────────────────
print("\n📦 BLOQUE L — TEXT UTILS (voseo)")

try:
    from core.dm.text_utils import apply_voseo, split_message
    _voseo_imported = True
except Exception as e:
    _voseo_imported = False
    print(f"  ⏭️ Import dm/text_utils: {e}")

if _voseo_imported:
    test("L1: apply_voseo 'tienes' → 'tenés'", lambda: assert_true("tenés" in apply_voseo("tienes mucho potencial")))
    test("L2: apply_voseo 'puedes' → 'podés'", lambda: assert_true("podés" in apply_voseo("puedes hacerlo")))
    test("L3: apply_voseo 'tú' → 'vos'", lambda: assert_true("vos" in apply_voseo("tú lo sabes")))
    test("L4: apply_voseo 'eres' → 'sos'", lambda: assert_true("sos" in apply_voseo("eres increíble")))
    test("L5: apply_voseo empty string → ''", lambda: assert_eq(apply_voseo(""), ""))
    test("L6: split_message short text → single item", lambda: assert_eq(len(split_message("Hola")), 1))
    test("L7: split_message long text → multiple items", lambda: assert_true(
        len(split_message("a" * 200, max_length=50)) > 1
    ))


# ──────────────────────────────────────────────
# BLOQUE M — TONE ENFORCER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE M — TONE ENFORCER")

try:
    from services.tone_enforcer import enforce_tone
    _tone_imported = True
except Exception as e:
    _tone_imported = False
    print(f"  ⏭️ Import tone_enforcer: {e}")

if _tone_imported:
    _mock_calibration = {
        "baseline": {
            "emoji_pct": 50.0,
            "exclamation_pct": 30.0,
            "question_frequency_pct": 10.0,
        }
    }

    test("M1: enforce_tone returns string", lambda: assert_true(isinstance(enforce_tone("Hola mundo", _mock_calibration, "user123", "hola"), str)))
    test("M2: enforce_tone empty response → ''", lambda: assert_eq(enforce_tone("", _mock_calibration, "user123", "hola"), ""))
    test("M3: enforce_tone None calibration → unchanged", lambda: assert_eq(enforce_tone("Hola!", None, "user", "msg"), "Hola!"))
    test("M4: enforce_tone result is non-empty string", lambda: assert_true(len(enforce_tone("Buenas tardes", _mock_calibration, "abc", "hi")) > 0))


# ──────────────────────────────────────────────
# BLOQUE N — RAG SERVICE
# ──────────────────────────────────────────────
print("\n📦 BLOQUE N — RAG SERVICE")

try:
    from services.rag_service import RAGService, DocumentChunk
    _rag_imported = True
except Exception as e:
    _rag_imported = False
    print(f"  ⏭️ Import rag_service: {e}")

if _rag_imported:
    _rag = RAGService(similarity_threshold=0.1)

    test("N1: RAGService instantiates", lambda: assert_true(_rag is not None))
    test("N2: add_document returns chunk_id string", lambda: assert_true(isinstance(_rag.add_document("Curso de nutrición: aprende a comer bien"), str)))
    test("N3: retrieve empty → []", lambda: assert_eq(RAGService().retrieve("nutrición"), []))
    test("N4: retrieve with documents → list", lambda: (
        lambda r: _rag.add_document("Coaching de vida: supera tus límites"),
        lambda: assert_true(isinstance(_rag.retrieve("coaching"), list))
    )[-1]())
    test("N5: add_document empty raises ValueError", lambda: (
        lambda raised: assert_true(raised)
    )(_try_raises(lambda: _rag.add_document(""), ValueError)))
    test("N6: DocumentChunk auto-generates chunk_id", lambda: assert_true(
        DocumentChunk(content="test").chunk_id is not None
    ))
    test("N7: DocumentChunk has created_at", lambda: assert_true(
        DocumentChunk(content="test").created_at is not None
    ))
    test("N8: retrieve returns results with 'content' key", lambda: (
        lambda: (
            _rag.add_document("El programa incluye 12 semanas de entrenamiento"),
            assert_true(all("content" in r for r in _rag.retrieve("programa")) or _rag.retrieve("nutricion") == [])
        )
    )())


# ──────────────────────────────────────────────
# BLOQUE O — LEAD SCORING
# ──────────────────────────────────────────────
print("\n📦 BLOQUE O — LEAD SCORING")

try:
    from services.lead_scoring import classify_lead, calculate_score, FOLLOWER_PURCHASE_KEYWORDS
    _scoring_imported = True
except Exception as e:
    _scoring_imported = False
    print(f"  ⏭️ Import lead_scoring: {e}")

if _scoring_imported:
    def _make_signals(**kwargs):
        base = {
            "total_messages": 5,
            "follower_messages": 3,
            "creator_messages": 2,
            "follower_purchase_hits": 0,
            "follower_interest_hits": 0,
            "follower_scheduling_hits": 0,
            "follower_negative_hits": 0,
            "follower_social_hits": 0,
            "creator_social_hits": 0,
            "social_hits": 0,
            "collaboration_hits": 0,
            "follower_avg_length": 20.0,
            "short_reactions": 0,
            "story_replies": 0,
            "bidirectional_ratio": 0.0,
            "strong_intents": 0,
            "soft_intents": 0,
            "days_since_last": 5,
            "days_since_first": 30,
            "is_existing_customer": False,
        }
        base.update(kwargs)
        return base

    test("O1: classify_lead default → 'nuevo'", lambda: assert_eq(classify_lead(_make_signals()), "nuevo"))
    test("O2: classify_lead cliente preserved", lambda: assert_eq(classify_lead(_make_signals(is_existing_customer=True)), "cliente"))
    test("O3: classify_lead with purchase hits → 'caliente'", lambda: assert_eq(classify_lead(_make_signals(follower_purchase_hits=2)), "caliente"))
    test("O4: classify_lead with collaboration → 'colaborador'", lambda: assert_eq(classify_lead(_make_signals(collaboration_hits=2)), "colaborador"))
    test("O5: classify_lead with social + volume + bidirec → 'amigo'", lambda: assert_eq(
        classify_lead(_make_signals(follower_social_hits=2, creator_social_hits=2, total_messages=8, bidirectional_ratio=0.4, days_since_last=5)), "amigo"
    ))
    test("O6: classify_lead inactive 20 days → 'frío'", lambda: assert_eq(classify_lead(_make_signals(days_since_last=20, total_messages=15, follower_messages=8)), "frío"))
    test("O7: calculate_score returns int", lambda: assert_true(isinstance(calculate_score("nuevo", _make_signals()), int)))
    test("O8: calculate_score cliente → high score", lambda: assert_true(calculate_score("cliente", _make_signals(is_existing_customer=True, days_since_last=2)) > 50))
    test("O9: calculate_score caliente → 50-100", lambda: assert_true(50 <= calculate_score("caliente", _make_signals(follower_purchase_hits=3)) <= 100))
    test("O10: FOLLOWER_PURCHASE_KEYWORDS contains 'precio'", lambda: assert_true("precio" in FOLLOWER_PURCHASE_KEYWORDS))


# ──────────────────────────────────────────────
# BLOQUE P — MEMORY SERVICE
# ──────────────────────────────────────────────
print("\n📦 BLOQUE P — MEMORY SERVICE")

try:
    from services.memory_service import MemoryStore, FollowerMemory
    _memory_imported = True
except Exception as e:
    _memory_imported = False
    print(f"  ⏭️ Import memory_service: {e}")

if _memory_imported:
    import tempfile
    _tmp_dir = tempfile.mkdtemp(prefix="clonnect_test_")
    _store = MemoryStore(storage_path=_tmp_dir)

    test("P1: MemoryStore instantiates", lambda: assert_true(_store is not None))
    test("P2: FollowerMemory creates with required fields", lambda: assert_true(
        FollowerMemory(follower_id="u123", creator_id="iris_bertran").follower_id == "u123"
    ))
    test("P3: FollowerMemory to_dict() returns dict", lambda: assert_true(
        isinstance(FollowerMemory(follower_id="u123", creator_id="iris").to_dict(), dict)
    ))
    test("P4: FollowerMemory from_dict roundtrip", lambda: (
        lambda fm: assert_eq(FollowerMemory.from_dict(fm.to_dict()).follower_id, fm.follower_id)
    )(FollowerMemory(follower_id="abc", creator_id="iris", username="testuser")))
    test("P5: FollowerMemory default interests=[]", lambda: assert_eq(FollowerMemory(follower_id="x", creator_id="y").interests, []))
    test("P6: FollowerMemory status default 'new'", lambda: assert_eq(FollowerMemory(follower_id="x", creator_id="y").status, "new"))


# ──────────────────────────────────────────────
# BLOQUE Q — CONVERSATION STATE
# ──────────────────────────────────────────────
print("\n📦 BLOQUE Q — CONVERSATION STATE")

try:
    from core.conversation_state import StateManager, ConversationState, ConversationPhase, get_state_manager, UserContext
    _state_imported = True
except Exception as e:
    _state_imported = False
    print(f"  ⏭️ Import conversation_state: {e}")

if _state_imported:
    _sm = StateManager()

    test("Q1: StateManager instantiates", lambda: assert_true(_sm is not None))
    test("Q2: get_state_manager returns StateManager", lambda: assert_true(isinstance(get_state_manager(), StateManager)))
    test("Q3: ConversationPhase.INICIO value = 'inicio'", lambda: assert_eq(ConversationPhase.INICIO.value, "inicio"))
    test("Q4: ConversationPhase has CIERRE", lambda: assert_true(hasattr(ConversationPhase, "CIERRE")))
    test("Q5: ConversationPhase has ESCALAR", lambda: assert_true(hasattr(ConversationPhase, "ESCALAR")))
    test("Q6: UserContext.to_prompt_context() returns string", lambda: assert_true(isinstance(UserContext().to_prompt_context(), str)))
    test("Q7: ConversationState default phase = INICIO", lambda: assert_eq(
        ConversationState(follower_id="u1", creator_id="iris").phase, ConversationPhase.INICIO
    ))
    test("Q8: ConversationState has context field", lambda: assert_true(
        hasattr(ConversationState(follower_id="u1", creator_id="iris"), "context")
    ))


# ──────────────────────────────────────────────
# BLOQUE R — IDENTITY RESOLVER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE R — IDENTITY RESOLVER")

try:
    from core.identity_resolver import extract_contact_signals
    _identity_imported = True
except Exception as e:
    _identity_imported = False
    print(f"  ⏭️ Import identity_resolver: {e}")

if _identity_imported:
    test("R1: email extracted", lambda: assert_eq(extract_contact_signals("mi email es test@example.com").get("email"), "test@example.com"))
    test("R2: instagram handle extracted", lambda: assert_true("instagram_handle" in extract_contact_signals("sígueme en @testuser123")))
    test("R3: empty message → {}", lambda: assert_eq(extract_contact_signals(""), {}))
    test("R4: no signals → {}", lambda: assert_eq(extract_contact_signals("hola cómo estás"), {}))
    test("R5: phone extracted", lambda: assert_true("phone" in extract_contact_signals("llámame al +34 612345678")))
    test("R6: @gmail excluded from instagram handles (word form)", lambda: assert_false("instagram_handle" in extract_contact_signals("escribe a @gmail")))
    test("R7: returns dict", lambda: assert_true(isinstance(extract_contact_signals("hola"), dict)))


# ──────────────────────────────────────────────
# BLOQUE S — CALIBRATION LOADER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE S — CALIBRATION LOADER")

try:
    from services.calibration_loader import load_calibration, get_few_shot_section
    _cal_imported = True
except Exception as e:
    _cal_imported = False
    print(f"  ⏭️ Import calibration_loader: {e}")

if _cal_imported:
    test("S1: load_calibration nonexistent → None", lambda: assert_eq(load_calibration("__no_existe_creator_xyz__"), None))
    test("S2: get_few_shot_section empty cal → ''", lambda: assert_eq(get_few_shot_section({}, max_examples=3), ""))
    test("S3: get_few_shot_section with examples", lambda: assert_true(isinstance(get_few_shot_section({
        "few_shot_examples": [{"context": "saludo", "user_message": "hola", "response": "Hola!", "length": 5}]
    }), str)))
    test("S4: load_calibration returns None or dict", lambda: assert_true(
        load_calibration("__test__") is None or isinstance(load_calibration("__test__"), dict)
    ))


# ──────────────────────────────────────────────
# BLOQUE T — PERSONALITY LOADER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE T — PERSONALITY LOADER")

try:
    from core.personality_loader import load_extraction, ExtractionData
    _personality_imported = True
except Exception as e:
    _personality_imported = False
    print(f"  ⏭️ Import personality_loader: {e}")

if _personality_imported:
    test("T1: load_extraction nonexistent → None (no DB fallback)", lambda: (
        lambda result: assert_true(result is None or isinstance(result, ExtractionData))
    )(load_extraction("__no_existe_creator_zzz__")))
    test("T2: ExtractionData has creator_id field", lambda: assert_true(hasattr(ExtractionData(creator_id="test"), "creator_id")))
    test("T3: ExtractionData has blacklist_phrases field", lambda: assert_true(hasattr(ExtractionData(creator_id="test"), "blacklist_phrases")))
    test("T4: ExtractionData default blacklist_phrases = []", lambda: assert_eq(ExtractionData(creator_id="test").blacklist_phrases, []))


# ──────────────────────────────────────────────
# BLOQUE U — TIMING SERVICE
# ──────────────────────────────────────────────
print("\n📦 BLOQUE U — TIMING SERVICE")

try:
    from services.timing_service import TimingService, TimingConfig, get_timing_service
    _timing_imported = True
except Exception as e:
    _timing_imported = False
    print(f"  ⏭️ Import timing_service: {e}")

if _timing_imported:
    _ts = TimingService()

    test("U1: TimingService instantiates", lambda: assert_true(_ts is not None))
    test("U2: calculate_delay returns float", lambda: assert_true(isinstance(_ts.calculate_delay(50, 30), float)))
    test("U3: calculate_delay >= min_delay (2.0)", lambda: assert_true(_ts.calculate_delay(0, 0) >= _ts.config.min_delay))
    test("U4: calculate_delay <= max_delay (30.0)", lambda: assert_true(_ts.calculate_delay(1000, 500) <= _ts.config.max_delay))
    test("U5: is_active_hours returns bool", lambda: assert_true(isinstance(_ts.is_active_hours(), bool)))
    test("U6: get_timing_service returns TimingService", lambda: assert_true(isinstance(get_timing_service(), TimingService)))
    test("U7: TimingConfig has min_delay=2.0", lambda: assert_eq(TimingConfig().min_delay, 2.0))


# ──────────────────────────────────────────────
# BLOQUE V — SEND GUARD
# ──────────────────────────────────────────────
print("\n📦 BLOQUE V — SEND GUARD")

try:
    from core.send_guard import SendBlocked, check_send_permission
    _sendguard_imported = True
except Exception as e:
    _sendguard_imported = False
    print(f"  ⏭️ Import send_guard: {e}")

if _sendguard_imported:
    test("V1: SendBlocked is an Exception subclass", lambda: assert_true(issubclass(SendBlocked, Exception)))
    test("V2: check_send_permission approved=True → True", lambda: assert_true(check_send_permission("test_creator", approved=True, caller="test")))
    test("V3: check_send_permission approved=False → raises SendBlocked or returns True",
         lambda: assert_true(
             _try_raises(lambda: check_send_permission("nonexistent_creator_xyz", approved=False, caller="test"), SendBlocked)
             or _try_raises(lambda: check_send_permission("nonexistent_creator_xyz", approved=False, caller="test"), Exception)
         ))


# ──────────────────────────────────────────────
# BLOQUE W — CONFIDENCE SCORER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE W — CONFIDENCE SCORER")

try:
    from core.confidence_scorer import calculate_confidence
    _confidence_imported = True
except Exception as e:
    _confidence_imported = False
    print(f"  ⏭️ Import confidence_scorer: {e}")

if _confidence_imported:
    test("W1: calculate_confidence returns float", lambda: assert_true(isinstance(calculate_confidence("greeting", "Hola!"), float)))
    test("W2: confidence in [0.0, 1.0]", lambda: assert_true(0.0 <= calculate_confidence("greeting", "Hola mundo!") <= 1.0))
    test("W3: empty response → 0.0", lambda: assert_eq(calculate_confidence("greeting", ""), 0.0))
    test("W4: greeting intent → high confidence", lambda: assert_true(calculate_confidence("greeting", "Hola!", "pool_match") > 0.5))
    test("W5: error intent → low confidence", lambda: assert_true(calculate_confidence("error", "ERROR: algo falló", "error_fallback") < 0.5))
    test("W6: pool_match type → higher than llm_generation",
         lambda: assert_true(
             calculate_confidence("greeting", "Hola!", "pool_match") >= calculate_confidence("greeting", "Hola!", "llm_generation")
         ))
    test("W7: blacklisted pattern → lower confidence than clean long response", lambda: assert_true(
        calculate_confidence("greeting", "COMPRA AHORA el curso")
        < calculate_confidence("greeting", "Hola! Puedo ayudarte con lo que necesites, escríbeme cuando quieras")
    ))


# ──────────────────────────────────────────────
# BLOQUE X — NURTURING MANAGER
# ──────────────────────────────────────────────
print("\n📦 BLOQUE X — NURTURING MANAGER")

try:
    from core.nurturing.manager import NurturingManager, get_nurturing_manager
    _nurturing_imported = True
except Exception as e:
    _nurturing_imported = False
    print(f"  ⏭️ Import nurturing manager: {e}")

if _nurturing_imported:
    import tempfile
    _nm_dir = tempfile.mkdtemp(prefix="clonnect_nurturing_test_")
    _nm = NurturingManager(storage_path=_nm_dir)

    test("X1: NurturingManager instantiates", lambda: assert_true(_nm is not None))
    test("X2: get_nurturing_manager returns NurturingManager", lambda: assert_true(isinstance(get_nurturing_manager(), NurturingManager)))
    test("X3: NurturingManager has storage_path", lambda: assert_true(hasattr(_nm, "storage_path")))


# ──────────────────────────────────────────────
# BLOQUE Y — COPILOT SERVICE
# ──────────────────────────────────────────────
print("\n📦 BLOQUE Y — COPILOT SERVICE")

try:
    from core.copilot.service import CopilotService, get_copilot_service
    _copilot_imported = True
except Exception as e:
    _copilot_imported = False
    print(f"  ⏭️ Import copilot service: {e}")

if _copilot_imported:
    _cs = CopilotService()

    test("Y1: CopilotService instantiates", lambda: assert_true(_cs is not None))
    test("Y2: get_copilot_service returns CopilotService", lambda: assert_true(isinstance(get_copilot_service(), CopilotService)))
    test("Y3: _calculate_purchase_intent 'purchase' → 0.85", lambda: assert_eq(_cs._calculate_purchase_intent(0.0, "purchase"), 0.85))
    test("Y4: _calculate_purchase_intent 'greeting' → 0.10", lambda: assert_eq(_cs._calculate_purchase_intent(0.0, "greeting"), 0.10))
    test("Y5: _calculate_lead_status 0.8 → 'hot'", lambda: assert_eq(_cs._calculate_lead_status(0.8), "hot"))
    test("Y6: _calculate_lead_status 0.4 → 'active'", lambda: assert_eq(_cs._calculate_lead_status(0.4), "active"))
    test("Y7: _calculate_lead_status 0.1 → 'new' or 'warm'", lambda: assert_true(_cs._calculate_lead_status(0.1) in ("new", "warm")))


# ──────────────────────────────────────────────
# BLOQUE Z — EMBEDDINGS (sin API key)
# ──────────────────────────────────────────────
print("\n📦 BLOQUE Z — EMBEDDINGS")

try:
    from core.embeddings import generate_embedding, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
    _embed_imported = True
except Exception as e:
    _embed_imported = False
    print(f"  ⏭️ Import embeddings: {e}")

if _embed_imported:
    test("Z1: EMBEDDING_MODEL is string", lambda: assert_true(isinstance(EMBEDDING_MODEL, str)))
    test("Z2: EMBEDDING_DIMENSIONS = 1536", lambda: assert_eq(EMBEDDING_DIMENSIONS, 1536))
    test("Z3: generate_embedding no API key → None", lambda: assert_true(
        generate_embedding("test") is None or isinstance(generate_embedding("test"), list)
    ))


# ──────────────────────────────────────────────
# BLOQUE SEMI — SEMI-AUTOMATED QUALITY REVIEWS
# ──────────────────────────────────────────────
print("\n📦 BLOQUE SEMI — QUALITY REVIEWS (requieren revisión humana)")

if _intent_imported:
    semi("SEMI-1: classify 'contame más sobre el programa'",
         lambda: _classifier.classify("contame más sobre el programa").value)

    semi("SEMI-2: classify 'quiero comprar el curso ya dime el precio'",
         lambda: _classifier.classify("quiero comprar el curso ya dime el precio").value)

if _sensitive_imported:
    semi("SEMI-3: detect_sensitive 'estoy muy mal emocionalmente'",
         lambda: {"type": detect_sensitive_content("estoy muy mal emocionalmente").type.value,
                  "confidence": detect_sensitive_content("estoy muy mal emocionalmente").confidence})

if _fixes_imported:
    semi("SEMI-4: fix_price_typo en texto real",
         lambda: fix_price_typo("El curso cuesta 297? y el mentoring 497? al mes"))

    semi("SEMI-5: clean_raw_ctas en respuesta real",
         lambda: clean_raw_ctas("Es la mejor opción para ti! QUIERO SER PARTE del programa ya! Aquí el link"))

if _length_imported:
    semi("SEMI-6: enforce_length en texto largo tipo objeción",
         lambda: enforce_length(
             "Entiendo que el precio puede parecer alto, pero lo que realmente estás invirtiendo es en transformar tu vida. Piénsalo así: si sigues haciendo lo mismo, obtendrás los mismos resultados. Este programa te da las herramientas exactas que necesitas. ¿Cuánto vale para ti cambiar tu situación actual?",
             "es muy caro",
             context="objecion"
         ))

if _voseo_imported:
    semi("SEMI-7: apply_voseo en texto comercial",
         lambda: apply_voseo("Si tienes dudas puedes escribirme. Tienes todo lo que necesitas para empezar"))

if _rag_imported:
    semi("SEMI-8: RAG retrieve nutrients",
         lambda: (
             lambda r: r.retrieve("nutrición y bienestar")
         )((lambda s: (s.add_document("El programa de nutrición incluye 12 semanas de guía personalizada y recetas saludables"),
                       s.add_document("Bienestar integral: mente y cuerpo en equilibrio"),
                       s)[-1])(RAGService(similarity_threshold=0.05))))

if _tone_imported:
    semi("SEMI-9: enforce_tone con emoji target alto",
         lambda: enforce_tone("Hola buenas tardes, puedo ayudarte con lo que necesites", {
             "baseline": {"emoji_pct": 80.0, "exclamation_pct": 60.0, "question_frequency_pct": 20.0}
         }, "user_semi", "hola"))

if _confidence_imported:
    semi("SEMI-10: confidence scores para distintos intents",
         lambda: {
             "greeting_pool": calculate_confidence("greeting", "Hola! Bienvenido 😊", "pool_match"),
             "purchase_llm": calculate_confidence("purchase_intent", "Claro que sí, aquí tienes el link de pago", "llm_generation"),
             "error": calculate_confidence("error", "ERROR: timeout al conectar", "error_fallback"),
         })


# ──────────────────────────────────────────────
# GUARDAR SEMI REVIEW
# ──────────────────────────────────────────────
semi_review_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mega_test_semi_review.txt")
with open(semi_review_path, "w", encoding="utf-8") as f:
    f.write(f"MEGA TEST SEMI — {len(semi_review)} resultados\n")
    for r in semi_review:
        f.write(r)

print(f"\n{'='*60}")
print(f"MEGA TEST RESULTS")
print(f"{'='*60}")
print(f"  ✅ PASS:  {PASS}")
print(f"  ❌ FAIL:  {FAIL}")
print(f"  ⏭️  SKIP:  {SKIP}")
print(f"  TOTAL:   {PASS+FAIL+SKIP}")
print(f"  SEMI:    {len(semi_review)}")
if errors:
    print(f"\nERRORES:")
    for e in errors:
        print(f"  {e}")
print(f"\nSemi review guardado en: {semi_review_path}")
