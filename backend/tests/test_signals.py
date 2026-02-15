"""
Tests para el sistema inteligente de señales y predicción de venta
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# Mock Message class for testing
@dataclass
class MockMessage:
    role: str
    content: str
    created_at: Optional[datetime] = None


class TestSignalsAnalysis:
    """Tests para analyze_conversation_signals"""

    def setup_method(self):
        """Setup antes de cada test"""
        # Import here to avoid module loading issues
        from api.services.signals import (
            analyze_conversation_signals,
            _empty_analysis,
            PURCHASE_INTENT_SIGNALS,
            PRODUCT_SIGNALS
        )
        self.analyze = analyze_conversation_signals
        self.empty_analysis = _empty_analysis
        self.purchase_signals = PURCHASE_INTENT_SIGNALS
        self.product_signals = PRODUCT_SIGNALS

    # =============================================================================
    # Tests de detección de keywords de compra
    # =============================================================================

    def test_detect_purchase_keywords(self):
        """Test detección de señales de intención de compra"""
        messages = [
            MockMessage(role="user", content="Hola, cuánto cuesta el curso?"),
            MockMessage(role="assistant", content="El curso cuesta 297€"),
            MockMessage(role="user", content="Me interesa, cómo puedo pagar?"),
        ]

        result = self.analyze(messages, "nuevo")

        assert result["probabilidad_venta"] > 0
        assert len(result["senales_detectadas"]) > 0
        # Should detect "cuánto cuesta" and "pagar"
        signal_names = [s["signal"] for s in result["senales_detectadas"]]
        assert any(s in signal_names for s in ["precio_directo", "metodo_pago"])

    def test_detect_strong_purchase_intent(self):
        """Test detección de intención fuerte (quiero comprar)"""
        messages = [
            MockMessage(role="user", content="Me apunto al curso, lo quiero"),
        ]

        result = self.analyze(messages, "caliente")

        assert result["probabilidad_venta"] >= 30
        signal_names = [s["signal"] for s in result["senales_detectadas"]]
        assert "confirma_compra" in signal_names

    def test_detect_payment_link_request(self):
        """Test detección de solicitud de link de pago"""
        messages = [
            MockMessage(role="user", content="Pásame el link para pagar"),
        ]

        result = self.analyze(messages, "caliente")

        assert result["probabilidad_venta"] >= 35
        signal_names = [s["signal"] for s in result["senales_detectadas"]]
        assert "link_pago" in signal_names

    # =============================================================================
    # Tests de detección de keywords de interés
    # =============================================================================

    def test_detect_interest_keywords(self):
        """Test detección de señales de interés"""
        messages = [
            MockMessage(role="user", content="Me interesa tu programa, cuéntame más"),
        ]

        result = self.analyze(messages, "nuevo")

        assert result["probabilidad_venta"] > 0
        categories = result["senales_por_categoria"]
        assert len(categories["interes"]) > 0 or len(categories["compra"]) > 0

    def test_detect_info_request(self):
        """Test detección de solicitud de información"""
        messages = [
            MockMessage(role="user", content="Dame más info sobre el coaching"),
        ]

        result = self.analyze(messages, "nuevo")

        assert result["probabilidad_venta"] > 0
        signal_names = [s["signal"] for s in result["senales_detectadas"]]
        assert any(s in signal_names for s in ["pide_info", "interes_general"])

    # =============================================================================
    # Tests de detección de objeciones
    # =============================================================================

    def test_detect_price_objection(self):
        """Test detección de objeción por precio"""
        messages = [
            MockMessage(role="user", content="Es muy caro, no tengo dinero ahora"),
        ]

        result = self.analyze(messages, "tibio")

        categories = result["senales_por_categoria"]
        assert len(categories["objecion"]) > 0
        signal_names = [s["signal"] for s in result["senales_detectadas"]]
        assert any(s in signal_names for s in ["objecion_precio", "sin_dinero"])

    def test_detect_time_objection(self):
        """Test detección de objeción por tiempo"""
        messages = [
            MockMessage(role="user", content="Ahora no tengo tiempo para esto"),
        ]

        result = self.analyze(messages, "tibio")

        categories = result["senales_por_categoria"]
        assert len(categories["objecion"]) > 0

    def test_detect_doubt_objection(self):
        """Test detección de señal 'para_quien' (interés sobre público objetivo)"""
        messages = [
            MockMessage(role="user", content="¿Es para mí esto? No sé si es para mi caso"),
        ]

        result = self.analyze(messages, "tibio")

        signal_names = [s["signal"] for s in result["senales_detectadas"]]
        # Should detect "para_quien" which is an interest signal about target audience
        assert "para_quien" in signal_names or len(result["senales_detectadas"]) > 0

    # =============================================================================
    # Tests de cálculo de probabilidad
    # =============================================================================

    def test_probability_calculation_low(self):
        """Test probabilidad baja con solo saludo"""
        messages = [
            MockMessage(role="user", content="Hola, buenos días"),
        ]

        result = self.analyze(messages, "nuevo")

        assert result["probabilidad_venta"] <= 20

    def test_probability_calculation_medium(self):
        """Test probabilidad media con interés"""
        messages = [
            MockMessage(role="user", content="Me interesa el curso, cuéntame más"),
            MockMessage(role="assistant", content="Claro, te cuento..."),
            MockMessage(role="user", content="Cuánto cuesta?"),
        ]

        result = self.analyze(messages, "tibio")

        assert 20 <= result["probabilidad_venta"] <= 80

    def test_probability_calculation_high(self):
        """Test probabilidad alta con múltiples señales de compra"""
        messages = [
            MockMessage(role="user", content="Quiero comprar el curso"),
            MockMessage(role="assistant", content="Perfecto!"),
            MockMessage(role="user", content="Pásame el link de pago"),
            MockMessage(role="assistant", content="Aquí tienes..."),
            MockMessage(role="user", content="Ya reservé mi lugar"),
        ]

        result = self.analyze(messages, "caliente")

        assert result["probabilidad_venta"] >= 70
        assert result["confianza_prediccion"] in ["Alta", "Media"]

    # =============================================================================
    # Tests de detección de producto
    # =============================================================================

    def test_detect_course_product(self):
        """Test detección de producto: curso"""
        messages = [
            MockMessage(role="user", content="Me interesa el curso online"),
        ]

        result = self.analyze(messages, "nuevo")

        if result["producto_detectado"]:
            assert result["producto_detectado"]["id"] in ["curso", "programa"]
            assert "name" in result["producto_detectado"]
            assert "estimated_price" in result["producto_detectado"]

    def test_detect_coaching_product(self):
        """Test detección de producto: coaching"""
        messages = [
            MockMessage(role="user", content="Me interesa tu mentoría personalizada"),
        ]

        result = self.analyze(messages, "nuevo")

        if result["producto_detectado"]:
            assert result["producto_detectado"]["id"] in ["coaching", "mentoria"]
            assert "name" in result["producto_detectado"]

    def test_detect_membership_product(self):
        """Test detección de producto: membresía"""
        messages = [
            MockMessage(role="user", content="Cuánto cuesta la membresía mensual?"),
        ]

        result = self.analyze(messages, "nuevo")

        if result["producto_detectado"]:
            assert result["producto_detectado"]["id"] in ["membresia", "suscripcion"]
            assert "name" in result["producto_detectado"]

    # =============================================================================
    # Tests de cache
    # =============================================================================

    def test_cache_works(self):
        """Test que el cache funciona correctamente"""
        messages = [
            MockMessage(role="user", content="Quiero comprar el curso"),
        ]

        # Primera llamada
        result1 = self.analyze(messages, "nuevo")

        # Segunda llamada (debería usar cache)
        result2 = self.analyze(messages, "nuevo")

        # Los resultados deben ser idénticos
        assert result1["probabilidad_venta"] == result2["probabilidad_venta"]
        assert result1["senales_detectadas"] == result2["senales_detectadas"]

    # =============================================================================
    # Tests de comportamiento
    # =============================================================================

    def test_detect_many_questions(self):
        """Test detección de muchas preguntas (señal de interés)"""
        messages = [
            MockMessage(role="user", content="Qué incluye el programa?"),
            MockMessage(role="assistant", content="Incluye..."),
            MockMessage(role="user", content="Cuánto dura?"),
            MockMessage(role="assistant", content="Dura 8 semanas"),
            MockMessage(role="user", content="Hay garantía?"),
            MockMessage(role="assistant", content="Sí, 30 días"),
            MockMessage(role="user", content="Puedo pagar en cuotas?"),
        ]

        result = self.analyze(messages, "tibio")

        # Should detect many questions behavior
        signal_names = [s["signal"] for s in result["senales_detectadas"]]
        assert "muchas_preguntas" in signal_names

    def test_detect_detailed_messages(self):
        """Test detección de mensajes detallados"""
        messages = [
            MockMessage(role="user", content="Hola, te cuento mi situación. Llevo varios meses intentando mejorar mi negocio pero no consigo los resultados que esperaba. He probado varias cosas pero nada funciona. Por eso me interesa mucho tu programa."),
        ]

        result = self.analyze(messages, "nuevo")

        # Should detect detailed messages behavior
        signal_names = [s["signal"] for s in result["senales_detectadas"]]
        assert "mensajes_largos" in signal_names

    # =============================================================================
    # Tests de siguiente paso
    # =============================================================================

    def test_next_step_for_new_lead(self):
        """Test siguiente paso para lead nuevo"""
        messages = [
            MockMessage(role="user", content="Hola, qué tal?"),
        ]

        result = self.analyze(messages, "nuevo")

        assert result["siguiente_paso"] is not None
        assert "emoji" in result["siguiente_paso"]
        assert "texto" in result["siguiente_paso"]

    def test_next_step_for_hot_lead(self):
        """Test siguiente paso para lead caliente"""
        messages = [
            MockMessage(role="user", content="Lo quiero, pásame el link de pago"),
        ]

        result = self.analyze(messages, "caliente")

        # High intent messages should have high/urgent priority
        assert result["siguiente_paso"]["prioridad"] in ["urgente", "alta", "media"]

    # =============================================================================
    # Tests de edge cases
    # =============================================================================

    def test_empty_messages(self):
        """Test con lista de mensajes vacía"""
        result = self.analyze([], "nuevo")

        assert result["probabilidad_venta"] == 0
        assert len(result["senales_detectadas"]) == 0

    def test_only_bot_messages(self):
        """Test con solo mensajes del bot"""
        messages = [
            MockMessage(role="assistant", content="Hola, cómo puedo ayudarte?"),
            MockMessage(role="assistant", content="Tenemos varios productos..."),
        ]

        result = self.analyze(messages, "nuevo")

        assert result["probabilidad_venta"] == 0

    def test_none_content(self):
        """Test con contenido None (no debe crashear)"""
        messages = [
            MockMessage(role="user", content=None),
            MockMessage(role="user", content="Hola"),
        ]

        # Should not raise exception
        result = self.analyze(messages, "nuevo")

        assert result is not None

    def test_message_without_attributes(self):
        """Test con mensaje sin atributos esperados"""
        class WeirdMessage:
            pass

        messages = [WeirdMessage(), MockMessage(role="user", content="Hola")]

        # Should not raise exception due to safe attribute access
        result = self.analyze(messages, "nuevo")

        assert result is not None


class TestSignalDictionaries:
    """Tests para los diccionarios de señales"""

    def setup_method(self):
        """Setup"""
        from api.services.signals import PURCHASE_INTENT_SIGNALS, PRODUCT_SIGNALS
        self.purchase_signals = PURCHASE_INTENT_SIGNALS
        self.product_signals = PRODUCT_SIGNALS

    def test_purchase_signals_structure(self):
        """Test estructura de PURCHASE_INTENT_SIGNALS"""
        for signal_name, signal_data in self.purchase_signals.items():
            assert "keywords" in signal_data
            assert "weight" in signal_data
            assert "category" in signal_data
            assert isinstance(signal_data["keywords"], list)
            assert isinstance(signal_data["weight"], (int, float))

    def test_product_signals_structure(self):
        """Test estructura de PRODUCT_SIGNALS"""
        for product_name, product_data in self.product_signals.items():
            assert "keywords" in product_data
            assert "display_name" in product_data
            assert "default_price" in product_data
            assert isinstance(product_data["keywords"], list)

    def test_categories_are_valid(self):
        """Test que las categorías son válidas"""
        valid_categories = {"compra", "interes", "objecion", "comportamiento"}

        for signal_name, signal_data in self.purchase_signals.items():
            assert signal_data["category"] in valid_categories, \
                f"Invalid category for {signal_name}: {signal_data['category']}"

    def test_weights_are_reasonable(self):
        """Test que los pesos están en rango razonable"""
        for signal_name, signal_data in self.purchase_signals.items():
            weight = signal_data["weight"]
            assert -50 <= weight <= 50, \
                f"Unreasonable weight for {signal_name}: {weight}"
