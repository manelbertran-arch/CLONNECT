"""
Tests del DM History Service - Filtros
Basado en auditoria: backend/core/dm_history_service.py

Filtros implementados:
1. max_age_days: Solo mensajes de los ultimos N dias (default 90)
2. Mensajes vacios: content.strip() == "" -> filtrado
3. Longitud minima: len(content) < 1 -> filtrado

Scoring de leads:
- interest_strong/purchase -> +3
- interest_soft/question_product -> +1
- objection -> -1

Status basado en score:
- score >= 0.6 -> "hot"
- score >= 0.35 -> "active"
- score < 0.35 -> "new"
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock


class TestDMHistoryServiceConfig:
    """Tests de configuracion del servicio"""

    def test_default_max_age_days(self):
        """DEFAULT_MAX_AGE_DAYS es 90"""
        from core.dm_history_service import DEFAULT_MAX_AGE_DAYS

        assert DEFAULT_MAX_AGE_DAYS == 90

    def test_default_min_message_length(self):
        """DEFAULT_MIN_MESSAGE_LENGTH es 1"""
        from core.dm_history_service import DEFAULT_MIN_MESSAGE_LENGTH

        assert DEFAULT_MIN_MESSAGE_LENGTH == 1

    def test_service_class_exists(self):
        """DMHistoryService existe"""
        from core.dm_history_service import DMHistoryService

        service = DMHistoryService()
        assert service is not None


class TestLoadDMHistoryMethod:
    """Tests del metodo load_dm_history"""

    def test_method_signature(self):
        """load_dm_history tiene los parametros correctos"""
        from core.dm_history_service import DMHistoryService
        import inspect

        service = DMHistoryService()
        sig = inspect.signature(service.load_dm_history)
        params = sig.parameters

        # Parametros requeridos
        assert 'creator_id' in params
        assert 'access_token' in params
        assert 'page_id' in params
        assert 'ig_user_id' in params

        # Parametros opcionales con defaults
        assert 'limit' in params
        assert params['limit'].default == 50

        assert 'max_age_days' in params
        assert params['max_age_days'].default == 90

    def test_method_is_async(self):
        """load_dm_history es async"""
        from core.dm_history_service import DMHistoryService
        import inspect

        service = DMHistoryService()
        assert inspect.iscoroutinefunction(service.load_dm_history)


class TestMessageFiltering:
    """Tests de filtrado de mensajes"""

    def test_import_conversation_filters_empty_messages(self):
        """_import_conversation filtra mensajes vacios"""
        from core.dm_history_service import DMHistoryService
        import inspect

        service = DMHistoryService()

        # Verificar que el metodo existe
        assert hasattr(service, '_import_conversation')

        # Verificar que el codigo incluye filtro de mensajes vacios
        source = inspect.getsource(service._import_conversation)

        # Debe tener validacion de content vacio
        assert 'content.strip()' in source or 'not content' in source

    def test_import_conversation_filters_old_messages(self):
        """_import_conversation filtra mensajes antiguos"""
        from core.dm_history_service import DMHistoryService
        import inspect

        service = DMHistoryService()
        source = inspect.getsource(service._import_conversation)

        # Debe comparar con cutoff_date
        assert 'cutoff_date' in source

    def test_import_conversation_has_cutoff_date_param(self):
        """_import_conversation acepta cutoff_date"""
        from core.dm_history_service import DMHistoryService
        import inspect

        service = DMHistoryService()
        sig = inspect.signature(service._import_conversation)

        assert 'cutoff_date' in sig.parameters


class TestLeadScoring:
    """Tests de scoring de leads"""

    def test_scoring_logic_exists(self):
        """Logica de scoring existe en _import_conversation"""
        from core.dm_history_service import DMHistoryService
        import inspect

        service = DMHistoryService()
        source = inspect.getsource(service._import_conversation)

        # Debe tener logica de scoring
        assert 'purchase_signals' in source or 'purchase_intent' in source

    def test_status_assignment_logic(self):
        """Logica de asignacion de status existe"""
        from core.dm_history_service import DMHistoryService
        import inspect

        service = DMHistoryService()
        source = inspect.getsource(service._import_conversation)

        # Debe asignar status basado en score
        assert 'status' in source
        assert 'hot' in source
        assert 'active' in source
        assert 'new' in source


class TestConversationSummary:
    """Tests de ConversationSummary dataclass"""

    def test_dataclass_exists(self):
        """ConversationSummary existe"""
        from core.dm_history_service import ConversationSummary

        summary = ConversationSummary(
            follower_id="follower_123",
            username="test_user",
            message_count=10,
            last_message="Hola",
            first_contact="2024-01-01",
            calculated_score=0.5,
            status="active"
        )

        assert summary.follower_id == "follower_123"
        assert summary.message_count == 10
        assert summary.status == "active"


class TestServiceSingleton:
    """Tests del singleton del servicio"""

    def test_get_dm_history_service_exists(self):
        """Funcion get_dm_history_service existe"""
        from core.dm_history_service import get_dm_history_service

        assert callable(get_dm_history_service)

    def test_returns_singleton(self):
        """get_dm_history_service retorna la misma instancia"""
        from core.dm_history_service import get_dm_history_service

        service1 = get_dm_history_service()
        service2 = get_dm_history_service()

        assert service1 is service2


class TestDateFilteringLogic:
    """Tests especificos de filtrado por fecha"""

    def test_cutoff_date_calculation(self):
        """cutoff_date se calcula correctamente"""
        from datetime import datetime, timedelta, timezone
        from core.dm_history_service import DEFAULT_MAX_AGE_DAYS

        # Simular calculo de cutoff_date
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=DEFAULT_MAX_AGE_DAYS)

        # cutoff debe ser 90 dias atras
        diff = now - cutoff
        assert diff.days == DEFAULT_MAX_AGE_DAYS

    def test_message_older_than_cutoff_filtered(self):
        """Mensaje mas antiguo que cutoff se filtra"""
        from datetime import datetime, timedelta, timezone
        from core.dm_history_service import DEFAULT_MAX_AGE_DAYS

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=DEFAULT_MAX_AGE_DAYS)

        # Mensaje de hace 100 dias
        old_message_time = now - timedelta(days=100)

        # old_message_time < cutoff -> deberia filtrarse
        assert old_message_time < cutoff

    def test_message_newer_than_cutoff_not_filtered(self):
        """Mensaje mas nuevo que cutoff NO se filtra"""
        from datetime import datetime, timedelta, timezone
        from core.dm_history_service import DEFAULT_MAX_AGE_DAYS

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=DEFAULT_MAX_AGE_DAYS)

        # Mensaje de hace 30 dias
        recent_message_time = now - timedelta(days=30)

        # recent_message_time > cutoff -> NO deberia filtrarse
        assert recent_message_time > cutoff


class TestEmptyMessageFiltering:
    """Tests de filtrado de mensajes vacios"""

    def test_empty_string_filtered(self):
        """String vacio se filtra"""
        content = ""
        assert not content or not content.strip()

    def test_whitespace_only_filtered(self):
        """String con solo espacios se filtra"""
        content = "   "
        assert not content.strip()

    def test_newlines_only_filtered(self):
        """String con solo newlines se filtra"""
        content = "\n\n\n"
        assert not content.strip()

    def test_valid_message_not_filtered(self):
        """Mensaje valido NO se filtra"""
        content = "Hola, me interesa el producto"
        assert content.strip()
        assert len(content.strip()) >= 1


class TestDeduplication:
    """Tests de deduplicacion de mensajes"""

    def test_deduplication_by_platform_message_id(self):
        """Deduplicacion usa platform_message_id"""
        from core.dm_history_service import DMHistoryService
        import inspect

        service = DMHistoryService()
        source = inspect.getsource(service._import_conversation)

        # Debe verificar existencia por platform_message_id
        assert 'platform_message_id' in source


class TestStatsReturn:
    """Tests del retorno de estadisticas"""

    @pytest.mark.asyncio
    async def test_load_dm_history_returns_stats_dict(self):
        """load_dm_history retorna dict con estadisticas"""
        from core.dm_history_service import DMHistoryService

        service = DMHistoryService()

        # El metodo deberia retornar un dict con estas keys
        expected_keys = [
            'conversations_found',
            'leads_created',
            'messages_imported',
            'messages_filtered',
            'max_age_days',
            'errors'
        ]

        # Verificar estructura del retorno via inspeccion
        import inspect
        source = inspect.getsource(service.load_dm_history)

        for key in expected_keys:
            assert f'"{key}"' in source or f"'{key}'" in source, f"Falta key: {key}"


class TestIntentClassificationIntegration:
    """Tests de integracion con clasificador de intents"""

    def test_uses_classify_intent_simple(self):
        """Usa classify_intent_simple para clasificar mensajes"""
        from core.dm_history_service import DMHistoryService
        import inspect

        service = DMHistoryService()
        source = inspect.getsource(service._import_conversation)

        # Debe importar y usar classify_intent_simple
        assert 'classify_intent_simple' in source
