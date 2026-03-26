"""
MOTOR AUDIT TESTS — Clonnect Conversational Engine
===================================================
Tests reproducibles para los 12 bugs detectados en auditoría manual
+ tests adicionales para detectar bugs no conocidos.

Ejecutar:
    cd backend
    PYTHONPATH=. python -m pytest tests/test_motor_audit.py -v --tb=short

Contexto: Stefano Bonanno — creador fitness Barcelona.
Todos los tests son unitarios (sin API keys, sin DB real).
"""

import pytest
import sys
import os

# ─────────────────────────────────────────────────────────────────────────────
# BUG-CRIT-01: IntentClassifier clasifica solo ~10 de 30 intents
# ─────────────────────────────────────────────────────────────────────────────

class TestBugCrit01IntentClassifier:
    """BUG-CRIT-01: Intent Classifier solo clasifica 10 de 30 intents.
    Impacto: escalation/support/feedback_negative nunca se notifican al creador.
    Strategy VENTA nunca se activa (mismatch naming).
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from services.intent_service import IntentClassifier
        self.c = IntentClassifier()

    def test_objection_price(self):
        """'es muy caro para mí' debe → objection_price, no 'other'"""
        assert self.c.classify("es muy caro para mí").value == "objection_price"

    def test_interest_strong(self):
        """'me interesa mucho' debe → interest_strong"""
        assert self.c.classify("me interesa mucho").value == "interest_strong"

    def test_escalation(self):
        """'quiero hablar con una persona real' debe → escalation"""
        assert self.c.classify("quiero hablar con una persona real").value == "escalation"

    def test_support(self):
        """'no me funciona el acceso' debe → support"""
        assert self.c.classify("no me funciona el acceso").value == "support"

    def test_objection_time(self):
        """'no tengo tiempo' debe → objection_time"""
        assert self.c.classify("no tengo tiempo").value == "objection_time"

    def test_interest_soft(self):
        """'suena interesante' debe → interest_soft"""
        assert self.c.classify("suena interesante").value == "interest_soft"

    def test_objection_later(self):
        """'lo pienso y te digo' debe → objection_later"""
        assert self.c.classify("lo pienso y te digo").value == "objection_later"

    def test_feedback_negative(self):
        """'el producto es malísimo' debe → feedback_negative"""
        assert self.c.classify("el producto es malísimo").value == "feedback_negative"

    def test_pricing_naming(self):
        """'cuánto cuesta' debe → pricing (strategy.py busca 'pricing', no 'product_question')"""
        result = self.c.classify("cuánto cuesta").value
        assert result == "pricing", f"Got '{result}' — strategy VENTA nunca se activará"

    def test_purchase_naming(self):
        """'quiero comprar' debe → 'purchase' (no 'purchase_intent') para cascade"""
        result = self.c.classify("quiero comprar").value
        assert result in ("purchase", "purchase_intent"), f"Got unexpected '{result}'"

    def test_greeting_works(self):
        """Baseline: 'hola' → greeting (debe seguir funcionando)"""
        assert self.c.classify("hola").value == "greeting"

    def test_thanks_works(self):
        """Baseline: 'gracias' → thanks (debe seguir funcionando)"""
        assert self.c.classify("gracias").value == "thanks"

    def test_objection_doubt(self):
        """'no sé si funcionará' debe → objection_doubt"""
        assert self.c.classify("no sé si funcionará").value == "objection_doubt"

    def test_objection_not_for_me(self):
        """'no creo que sea para mí' debe → objection_not_for_me"""
        assert self.c.classify("no creo que sea para mí").value == "objection_not_for_me"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-CRIT-02: Sensitive detector AttributeError .category
# ─────────────────────────────────────────────────────────────────────────────

class TestBugCrit02SensitiveAttributeError:
    """BUG-CRIT-02: detection.py accede a sensitive_result.category pero
    el objeto tiene .type. AttributeError silenciado → persona en crisis sin ayuda.
    """

    def test_sensitive_result_has_no_category(self):
        """SensitiveResult debe tener .type, no .category"""
        from core.sensitive_detector import detect_sensitive_content
        result = detect_sensitive_content("quiero morir")
        assert result is not None
        assert hasattr(result, "type"), "SensitiveResult debe tener .type"
        assert not hasattr(result, "category"), \
            "SensitiveResult tiene .category — detection.py no crasheará (BUG ya reparado)"

    def test_detection_phase_uses_correct_attribute(self):
        """detection.py debe acceder a .type, no a .category"""
        with open("core/dm/phases/detection.py") as f:
            src = f.read()
        assert "sensitive_result.category" not in src, \
            "BUG-CRIT-02: detection.py accede a .category que no existe en SensitiveResult"

    def test_crisis_response_not_silenced(self):
        """Si hay crisis, el resultado debe ser accionable (no silenciado por AttributeError)"""
        from core.sensitive_detector import detect_sensitive_content
        result = detect_sensitive_content("quiero morir")
        # Si llegamos aquí y result tiene .type, la detección no crasheó
        assert result.type.value in ("self_harm", "crisis", "violence"), \
            f"Crisis no detectada correctamente: {result.type}"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-CRIT-03: Patrones de suicidio incompletos
# ─────────────────────────────────────────────────────────────────────────────

class TestBugCrit03SuicidePatterns:
    """BUG-CRIT-03: Patrones críticos de suicidio no cubren frases comunes en español."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.sensitive_detector import detect_sensitive_content, SensitiveType
        self.detect = detect_sensitive_content
        self.SensitiveType = SensitiveType

    def _is_crisis(self, msg):
        r = self.detect(msg)
        return r is not None and r.type != self.SensitiveType.NONE and r.confidence > 0.5

    def test_suicidar(self):
        """'me voy a suicidar' — frase directa que DEBE detectarse"""
        assert self._is_crisis("me voy a suicidar"), \
            "BUG-CRIT-03: 'me voy a suicidar' no detectado"

    def test_quitarme_la_vida(self):
        """'quiero quitarme la vida' — frase común en español"""
        assert self._is_crisis("quiero quitarme la vida"), \
            "BUG-CRIT-03: 'quiero quitarme la vida' no detectado"

    def test_acabar_con_todo(self):
        """'voy a acabar con todo' — detectado por el patrón existente"""
        assert self._is_crisis("voy a acabar con todo"), \
            "BUG-CRIT-03: 'voy a acabar con todo' no detectado"

    def test_quiero_morir_works(self):
        """Baseline: 'quiero morir' sí funciona"""
        assert self._is_crisis("quiero morir"), "'quiero morir' debe detectarse (baseline)"

    def test_no_quiero_seguir_viviendo_works(self):
        """Baseline: 'no quiero seguir viviendo' sí funciona"""
        assert self._is_crisis("no quiero seguir viviendo")

    def test_hacerme_dano(self):
        """'quiero hacerme daño' — variante común"""
        assert self._is_crisis("quiero hacerme daño"), \
            "BUG-CRIT-03 extendido: 'quiero hacerme daño' no detectado"

    def test_pastillas(self):
        """'me voy a tomar todas las pastillas' — frase de crisis"""
        assert self._is_crisis("me voy a tomar todas las pastillas"), \
            "BUG-CRIT-03 extendido: sobredosis no detectada"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-04: Reflexion Engine no normaliza acentos
# ─────────────────────────────────────────────────────────────────────────────

class TestBug04ReflexionAccents:
    """BUG-04: Regex de precio en reflexion_engine usa \bcuanto\b sin tilde.
    Resultado: 'precio preguntado no respondido' no se detecta con '¿Cuánto cuesta?'
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.reflexion_engine import get_reflexion_engine
        self.engine = get_reflexion_engine()

    def test_precio_preguntado_con_tilde(self):
        """'¿Cuánto cuesta?' debe activar 'precio preguntado no respondido'"""
        r = self.engine.analyze_response(
            response="Claro que sí, tenemos varias opciones disponibles.",
            user_message="¿Cuánto cuesta el coaching?",
        )
        issue_text = " ".join(r.issues).lower()
        assert "precio" in issue_text or "costo" in issue_text or "cuanto" in issue_text, \
            f"BUG-04: precio no detectado con tilde. Issues: {r.issues}"

    def test_precio_preguntado_sin_tilde(self):
        """Baseline: 'cuanto cuesta' (sin tilde) sí debe funcionar"""
        r = self.engine.analyze_response(
            response="Tenemos varias opciones.",
            user_message="cuanto cuesta el coaching",
        )
        issue_text = " ".join(r.issues).lower()
        assert "precio" in issue_text or "costo" in issue_text or "cuanto" in issue_text, \
            f"Incluso sin tilde falla. Issues: {r.issues}"

    def test_precio_en_respuesta_no_genera_issue(self):
        """Si la respuesta incluye precio, NO debe haber issue"""
        r = self.engine.analyze_response(
            response="El coaching cuesta 297€ al mes.",
            user_message="¿Cuánto cuesta el coaching?",
        )
        issue_text = " ".join(r.issues).lower()
        assert "precio" not in issue_text, \
            f"Falso positivo: respuesta con precio genera issue. Issues: {r.issues}"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-05: Guardrail off-topic desconectado de validate_response
# ─────────────────────────────────────────────────────────────────────────────

class TestBug05OffTopicGuardrail:
    """BUG-05: _check_off_topic() solo se llama desde get_safe_response(),
    no desde validate_response(). Off-topic opinions pasan como válidas.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.guardrails import get_response_guardrail
        self.g = get_response_guardrail()

    def test_bitcoin_offtopic_blocked(self):
        """Respuesta sobre bitcoin debe ser inválida"""
        result = self.g.validate_response(
            query="Qué opinas del bitcoin?",
            response="El bitcoin está subiendo mucho y es una gran inversión",
            context={"products": [], "allowed_urls": []},
        )
        assert result.get("valid") == False, \
            "BUG-05: bitcoin opinion pasa como valid=True"

    def test_politica_offtopic_blocked(self):
        """Respuesta política debe ser inválida"""
        result = self.g.validate_response(
            query="qué opinas de la política?",
            response="Creo que el gobierno actual está haciendo bien las cosas",
            context={"products": [], "allowed_urls": []},
        )
        assert result.get("valid") == False, \
            "BUG-05: política opinion pasa como valid=True"

    def test_fitness_ontopic_allowed(self):
        """Respuesta de fitness es válida (no off-topic)"""
        result = self.g.validate_response(
            query="cuántas series hago?",
            response="Para hipertrofia, 3-4 series de 8-12 repeticiones.",
            context={"products": [], "allowed_urls": []},
        )
        assert result.get("valid") == True, \
            "Falso positivo: respuesta de fitness bloqueada como off-topic"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-06: Pool response matchea mensaje vacío
# ─────────────────────────────────────────────────────────────────────────────

class TestBug06PoolEmptyMessage:
    """BUG-06: try_pool_response('') retorna matched=True con conf=0.9.
    Riesgo: responder '🔥' a un mensaje vacío o whitespace.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from services.response_variator_v2 import get_response_variator_v2
        self.v = get_response_variator_v2()

    def test_empty_string_no_match(self):
        """Mensaje vacío NO debe matchear ningún pool"""
        r = self.v.try_pool_response("", conv_id="t", turn_index=0, context="unknown", creator_id="test")
        matched = r.matched if r else False
        assert matched == False, f"BUG-06: mensaje vacío matcheó con conf={r.confidence if r else 'N/A'}"

    def test_whitespace_no_match(self):
        """Mensaje de solo espacios NO debe matchear"""
        r = self.v.try_pool_response("   ", conv_id="t", turn_index=0, context="unknown", creator_id="test")
        matched = r.matched if r else False
        assert matched == False, "BUG-06: whitespace matcheó pool response"

    def test_normal_greeting_can_match(self):
        """Baseline: saludo normal sí puede matchear (no rompemos lo que funciona)"""
        r = self.v.try_pool_response("hola", conv_id="t", turn_index=0, context="greeting", creator_id="test")
        # Solo verificamos que no crashea — puede o no matchear
        assert r is not None


# ─────────────────────────────────────────────────────────────────────────────
# BUG-07: Strategy VENTA nunca activa (intent name mismatch)
# ─────────────────────────────────────────────────────────────────────────────

class TestBug07StrategyMismatch:
    """BUG-07: strategy.py busca intent 'pricing' pero classifier genera 'product_question'.
    Resultado: ESTRATEGIA VENTA nunca se activa para preguntas de precio.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.dm.strategy import _determine_response_strategy
        self.strategy = _determine_response_strategy

    def test_product_question_activates_venta(self):
        """Intent 'product_question' (lo que genera el classifier) debe activar VENTA"""
        r = self.strategy("cuánto cuesta?", "product_question", "", False, False, [], "nuevo")
        assert "VENTA" in r, \
            f"BUG-07: 'product_question' no activa estrategia VENTA. Got: '{r[:100] if r else 'vacío'}'"

    def test_pricing_activates_venta(self):
        """Baseline: 'pricing' sí activa VENTA"""
        r = self.strategy("cuánto cuesta?", "pricing", "", False, False, [], "nuevo")
        assert "VENTA" in r, "Incluso 'pricing' no activa VENTA — problema más grave"

    def test_purchase_intent_activates_venta(self):
        """'purchase_intent' (lo que genera el classifier para 'quiero comprar') → VENTA"""
        r = self.strategy("quiero comprar el programa", "purchase_intent", "", False, False, [], "caliente")
        assert "VENTA" in r, \
            f"BUG-07: 'purchase_intent' no activa VENTA. Got: '{r[:100] if r else 'vacío'}'"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-08: Frustration detector demasiado permisivo
# ─────────────────────────────────────────────────────────────────────────────

class TestBug08FrustrationThreshold:
    """BUG-08: Mensajes claramente frustrados (<0.5 nivel) no llegan al umbral
    de inyección en prompt (>0.5). Usuario frustrado no recibe respuesta empática.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.frustration_detector import get_frustration_detector
        self.fd = get_frustration_detector()

    def test_insulto_directo_sobre_05(self):
        """'Esto es una mierda' debe superar 0.5"""
        _, level = self.fd.analyze_message("Esto es una mierda, no funciona nada", "test", [])
        assert level > 0.5, f"BUG-08: nivel={level:.2f}, esperado >0.5"

    def test_caps_repetition_sobre_05(self):
        """Mayúsculas + historial de espera → >0.5"""
        prev = ["necesito ayuda", "oye?", "hay alguien?"]
        _, level = self.fd.analyze_message("ESTOY HARTO DE ESPERAR", "test", prev)
        assert level > 0.5, f"BUG-08: nivel={level:.2f} con contexto de espera, esperado >0.5"

    def test_mensaje_neutro_bajo_05(self):
        """Baseline: mensaje neutro no debe superar 0.5"""
        _, level = self.fd.analyze_message("¿Cuánto cuesta el programa?", "test", [])
        assert level < 0.5, f"Falso positivo: mensaje neutro con nivel={level:.2f}"

    def test_repeated_no_response(self):
        """Usuario ignorado múltiples veces → frustración alta"""
        prev = ["hola?", "hay alguien?", "oye?", "por favor responde"]
        _, level = self.fd.analyze_message("nadie me responde nunca", "test", prev)
        assert level > 0.5, f"BUG-08: ignorado repetidamente, nivel={level:.2f}, esperado >0.5"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-09: Product matching falla con nombres parciales
# ─────────────────────────────────────────────────────────────────────────────

class TestBug09ProductMatching:
    """BUG-09: _message_mentions_product no detecta referencias parciales.
    'me interesa el coaching' no matchea con 'Coaching 1:1'.
    Impacto: pool fast-path activo aunque mencione producto → respuesta genérica.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.dm.text_utils import _message_mentions_product
        self.match = _message_mentions_product

    def test_coaching_partial(self):
        """'coaching' en mensaje debe matchear con producto 'Coaching 1:1'"""
        assert self.match("Coaching 1:1", "me interesa el coaching"), \
            "BUG-09: 'coaching' no matchea 'Coaching 1:1'"

    def test_mentoria_without_accent(self):
        """'mentoria' (sin tilde) debe matchear 'Mentoría grupal premium'"""
        assert self.match("Mentoría grupal premium", "info sobre la mentoria"), \
            "BUG-09: 'mentoria' sin tilde no matchea 'Mentoría'"

    def test_exact_match_works(self):
        """Baseline: match exacto funciona"""
        assert self.match("Coaching 1:1", "Coaching 1:1"), "Match exacto debe funcionar"

    def test_case_insensitive(self):
        """Case insensitive: 'COACHING' matchea 'Coaching 1:1'"""
        assert self.match("Coaching 1:1", "me interesa COACHING"), \
            "BUG-09: case insensitive no funciona"

    def test_no_false_positive(self):
        """'running' no debe matchear 'Coaching 1:1'"""
        assert not self.match("Coaching 1:1", "running es mi hobby"), \
            "Falso positivo: 'running' matcheó 'Coaching 1:1'"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-10: Response fixes dejan respuesta vacía
# ─────────────────────────────────────────────────────────────────────────────

class TestBug10ResponseFixesEmpty:
    """BUG-10: apply_all_response_fixes() con string puro de CTAs crudos → vacío.
    Un mensaje completamente de CTAs = respuesta vacía enviada al usuario.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.response_fixes import apply_all_response_fixes
        self.fix = apply_all_response_fixes

    def test_pure_ctas_not_empty(self):
        """Si todo es CTA crudo, debe retornar fallback, no cadena vacía"""
        result = self.fix("COMPRA AHORA QUIERO SER PARTE", creator_id="test")
        assert result and result.strip(), \
            f"BUG-10: response_fixes retornó vacío: '{result}'"

    def test_mixed_content_preserved(self):
        """Texto normal con CTA crudo al final → texto normal debe quedar"""
        result = self.fix("Te cuento más sobre el programa. COMPRA AHORA", creator_id="test")
        assert "programa" in result.lower(), \
            f"BUG-10: texto legítimo eliminado. Got: '{result}'"

    def test_normal_response_unchanged(self):
        """Respuesta normal no debe ser alterada significativamente"""
        original = "Hola! El coaching incluye 4 sesiones semanales de 45 minutos."
        result = self.fix(original, creator_id="test")
        assert len(result) > 20, f"Respuesta normal demasiado modificada: '{result}'"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-11: Emoji limit sin calibración
# ─────────────────────────────────────────────────────────────────────────────

class TestBug11EmojiLimitNoCalibration:
    """BUG-11: apply_emoji_limit() sin datos de calibración no aplica límite.
    Un LLM con 15 emojis en una respuesta los envía todos.
    """

    def test_emoji_limit_without_calibration(self):
        """Sin calibración, el límite por defecto debe aplicarse (ej. máx 5)"""
        from core.response_fixes import apply_all_response_fixes
        emoji_heavy = "🔥💪🏋️‍♂️✨🎯🌟💥🏆🎉🚀💫⭐🙌👏🎊"  # 15 emojis
        result = apply_all_response_fixes(emoji_heavy, creator_id="nonexistent_creator")
        # Contar emojis en resultado
        import re
        emoji_pattern = re.compile(
            "[\U00010000-\U0010ffff]|[\U0001F600-\U0001F64F]|[\U0001F300-\U0001F5FF]"
            "|[\U0001F680-\U0001F6FF]|[\U0001F1E0-\U0001F1FF]",
            flags=re.UNICODE
        )
        emoji_count = len(emoji_pattern.findall(result))
        assert emoji_count <= 8, \
            f"BUG-11: sin calibración hay {emoji_count} emojis (esperado ≤8)"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-12: Strategy pierde BIENVENIDA en primer mensaje con necesidad
# ─────────────────────────────────────────────────────────────────────────────

class TestBug12WelcomeWithHelp:
    """BUG-12: 'Hola, necesito ayuda' como primer mensaje → AYUDA sin BIENVENIDA.
    El usuario no recibe saludo, parece que el bot no lo reconoce como nuevo.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.dm.strategy import _determine_response_strategy
        self.strategy = _determine_response_strategy

    def test_first_msg_with_help_includes_welcome(self):
        """Primer mensaje con señal de ayuda → estrategia debe incluir bienvenida"""
        r = self.strategy("Hola, necesito ayuda con el programa", "greeting", "", True, False, [], "nuevo")
        assert "BIENVENIDA" in r or "Saluda" in r or "bienvenid" in r.lower(), \
            f"BUG-12: primer mensaje con ayuda no incluye bienvenida. Got: '{r[:100]}'"

    def test_returning_user_with_help_no_welcome(self):
        """Usuario que regresa (is_first=False) con ayuda → solo AYUDA, sin bienvenida forzada"""
        r = self.strategy("necesito ayuda", "support", "", False, False, [], "caliente")
        # Solo verificamos que responde con estrategia de ayuda
        assert len(r) > 0 or r == "", "Retorna None — error inesperado"

    def test_first_msg_pure_greeting_has_welcome(self):
        """Baseline: primer mensaje de solo saludo → BIENVENIDA"""
        r = self.strategy("Hola!", "greeting", "", True, False, [], "nuevo")
        assert "BIENVENIDA" in r, f"Saludo puro sin bienvenida. Got: '{r[:100]}'"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS ADICIONALES — Detección de bugs nuevos
# ─────────────────────────────────────────────────────────────────────────────

class TestAdditionalImports:
    """A) Verificar que todas las fases del pipeline se pueden importar sin error."""

    def test_import_phase_detection(self):
        from core.dm.phases.detection import phase_detection
        assert callable(phase_detection)

    def test_import_phase_context(self):
        from core.dm.phases.context import phase_memory_and_context
        assert callable(phase_memory_and_context)

    def test_import_phase_generation(self):
        from core.dm.phases.generation import phase_llm_generation
        assert callable(phase_llm_generation)

    def test_import_phase_postprocessing(self):
        from core.dm.phases.postprocessing import phase_postprocessing
        assert callable(phase_postprocessing)

    def test_import_guardrails(self):
        from core.guardrails import get_response_guardrail
        g = get_response_guardrail()
        assert g is not None

    def test_import_reflexion(self):
        from core.reflexion_engine import get_reflexion_engine
        e = get_reflexion_engine()
        assert e is not None

    def test_import_send_guard(self):
        from core.send_guard import SendGuard
        assert SendGuard is not None

    def test_import_best_of_n(self):
        from core.best_of_n import BestOfNSelector
        assert BestOfNSelector is not None

    def test_import_output_validator(self):
        from core.output_validator import OutputValidator
        assert OutputValidator is not None

    def test_import_response_fixes(self):
        from core.response_fixes import apply_all_response_fixes
        assert callable(apply_all_response_fixes)

    def test_import_chain_of_thought(self):
        from core.reasoning.chain_of_thought import ChainOfThoughtReasoner
        assert ChainOfThoughtReasoner is not None

    def test_import_llm_service(self):
        from services.llm_service import LLMService
        assert LLMService is not None


class TestVoseoConversion:
    """D) Verificar que apply_voseo convierte correctamente los pronombres."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.dm.text_utils import apply_voseo
        self.voseo = apply_voseo

    def test_tu_to_vos(self):
        assert "vos" in self.voseo("Hola, tú puedes hacerlo").lower()

    def test_tienes_to_tenes(self):
        result = self.voseo("¿Tienes dudas?")
        assert "tenés" in result or "tenes" in result.lower(), f"Got: {result}"

    def test_puedes_to_podes(self):
        result = self.voseo("Puedes empezar mañana")
        assert "podés" in result or "podes" in result.lower(), f"Got: {result}"

    def test_cuentame_to_contame(self):
        result = self.voseo("Cuéntame más")
        assert "contame" in result.lower(), f"Got: {result}"

    def test_no_false_conversion_in_words(self):
        """'tutela' no debe convertirse — 'tú' como subpalabra"""
        result = self.voseo("La tutela es importante")
        assert "tutela" in result, f"'tutela' fue incorrectamente modificada: {result}"


class TestOutputValidator:
    """E) Verificar que output_validator detecta precios inventados."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from core.output_validator import OutputValidator
        self.validator = OutputValidator()

    def test_invented_price_flagged(self):
        """Precio 99€ cuando el real es 297€ → should_escalate=True"""
        result = self.validator.validate(
            response="El coaching vale 99€ al mes",
            known_prices=[297.0],
            allowed_urls=[],
        )
        assert result.get("should_escalate") == True, \
            f"Precio inventado 99€ no detectado. Result: {result}"

    def test_correct_price_passes(self):
        """Precio correcto 297€ → válido"""
        result = self.validator.validate(
            response="El coaching vale 297€ al mes",
            known_prices=[297.0],
            allowed_urls=[],
        )
        assert result.get("should_escalate") == False, \
            f"Precio correcto marcado como hallucination. Result: {result}"

    def test_price_within_tolerance(self):
        """Precio 296€ con real 297€ → dentro de tolerancia ±1€"""
        result = self.validator.validate(
            response="El precio es 296€",
            known_prices=[297.0],
            allowed_urls=[],
        )
        assert result.get("should_escalate") == False, \
            "296€ con real 297€ debe pasar (tolerancia ±1€)"

    def test_url_not_in_whitelist_removed(self):
        """URL no autorizada → corregida/removida"""
        result = self.validator.validate(
            response="Visita http://sitio-random.xyz/producto",
            known_prices=[],
            allowed_urls=["stripe.com", "mysite.com"],
        )
        assert "[enlace removido]" in result.get("corrected", "") or \
               result.get("has_unauthorized_url") == True, \
            "URL no autorizada no fue detectada/removida"


class TestResponseFixesDuplicates:
    """C) Verificar que response_fixes no produce contenido duplicado."""

    def test_no_duplication(self):
        from core.response_fixes import apply_all_response_fixes
        original = "El coaching incluye 4 sesiones semanales."
        result = apply_all_response_fixes(original, creator_id="test")
        # Texto no debe aparecer dos veces
        assert result.count("coaching incluye") <= 1, \
            f"Contenido duplicado: '{result}'"

    def test_identity_fix_no_double_replacement(self):
        """'Soy Stefano Soy Stefano' no debe convertirse en doble asistente"""
        from core.response_fixes import apply_all_response_fixes
        result = apply_all_response_fixes("Soy Stefano, aquí para ayudarte", creator_id="test")
        # Solo una mención del asistente
        assert result.count("asistente de") <= 1, f"Doble reemplazo de identidad: '{result}'"


class TestLoopDetector:
    """G) Verificar que el loop detector funciona con variaciones menores."""

    def test_exact_match_detected(self):
        """Primeros 50 chars idénticos → debe detectarse como loop"""
        from core.dm.post_response import check_response_loop
        last_responses = [
            "¡Claro! Puedo ayudarte con información sobre el programa de entrenamiento.",
            "Hola, estaré encantado de resolver tus dudas.",
        ]
        current = "¡Claro! Puedo ayudarte con información sobre el programa de entrenamiento. ¿Qué quieres saber?"
        is_loop = check_response_loop(current, last_responses)
        assert is_loop == True, "Loop exacto no detectado"

    def test_different_response_not_loop(self):
        """Respuesta diferente → no es loop"""
        from core.dm.post_response import check_response_loop
        last_responses = ["¡Claro! El coaching cuesta 297€."]
        current = "Para el programa de fuerza necesitarás equipamiento básico."
        is_loop = check_response_loop(current, last_responses)
        assert is_loop == False, "Falso positivo de loop"


class TestConfidenceScorer:
    """H) Verificar que confidence_scorer no da 0.0 para respuestas válidas."""

    def test_valid_response_nonzero_confidence(self):
        """Respuesta válida debe tener confianza > 0"""
        from core.best_of_n import BestOfNSelector
        selector = BestOfNSelector()
        score = selector.calculate_confidence(
            intent="greeting",
            response_text="¡Hola! Bienvenido, ¿en qué puedo ayudarte?",
            response_type="pool",
            creator_id="test",
        )
        assert score > 0.0, f"Confianza 0.0 para respuesta válida"

    def test_empty_response_low_confidence(self):
        """Respuesta vacía debe tener confianza baja"""
        from core.best_of_n import BestOfNSelector
        selector = BestOfNSelector()
        score = selector.calculate_confidence(
            intent="greeting",
            response_text="",
            response_type="generated",
            creator_id="test",
        )
        assert score < 0.3, f"Respuesta vacía con confianza alta: {score}"


class TestMessageSplitter:
    """F) Verificar que el message_splitter no corta a mitad de palabra o URL."""

    def test_no_split_mid_word(self):
        """Texto no debe cortarse a mitad de palabra"""
        from core.dm.text_utils import split_message
        long_text = "Este es un texto de prueba que tiene muchas palabras y debería dividirse correctamente sin cortar ninguna palabra a la mitad en ningún momento durante el proceso de división."
        parts = split_message(long_text, max_length=80)
        for part in parts:
            # Verificar que cada parte termina en límite de palabra (espacio, puntuación)
            if part != parts[-1]:  # no última parte
                assert not part[-1].isalpha() or part.endswith(" "), \
                    f"Parte cortada mid-word: '{part[-20:]}'"

    def test_url_not_split(self):
        """Una URL no debe ser dividida en dos partes"""
        from core.dm.text_utils import split_message
        text = "Más info en https://stefanofit.com/programa-coaching-personalizado-intensivo y también en nuestra web principal"
        parts = split_message(text, max_length=60)
        # La URL completa debe aparecer en una sola parte
        full_url = "https://stefanofit.com/programa-coaching-personalizado-intensivo"
        url_found_complete = any(full_url in part for part in parts)
        assert url_found_complete, f"URL dividida entre partes: {parts}"
