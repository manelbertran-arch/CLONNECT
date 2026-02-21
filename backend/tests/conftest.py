"""
Centralized test configuration and fixtures for Clonnect backend.
All fixtures are documented and can be imported from this file.
"""
import pytest
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# Set test environment variables before importing app
os.environ["DATABASE_URL"] = ""
os.environ["TESTING"] = "true"
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["INSTAGRAM_ACCESS_TOKEN"] = "test-token"
os.environ["META_APP_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from api.main import app
from api.database import get_db
from api.auth import require_creator_access


# =============================================================================
# DEPENDENCY OVERRIDES FOR TESTING
# =============================================================================

def _mock_get_db():
    """Override get_db to return a MagicMock session instead of raising."""
    mock_session = MagicMock()
    try:
        yield mock_session
    finally:
        pass


async def _mock_require_creator_access(creator_id: str) -> str:
    """Override require_creator_access to bypass auth in tests."""
    return creator_id


# Apply overrides globally so all TestClient instances use them
app.dependency_overrides[get_db] = _mock_get_db
app.dependency_overrides[require_creator_access] = _mock_require_creator_access


# =============================================================================
# CORE FIXTURES
# =============================================================================

@pytest.fixture
def client():
    """FastAPI test client for HTTP requests."""
    return TestClient(app)


@pytest.fixture
def creator_id():
    """Default creator ID for tests."""
    return "manel"


@pytest.fixture
def async_client():
    """Async test client for async endpoint testing."""
    from httpx import AsyncClient
    return AsyncClient(app=app, base_url="http://test")


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

@pytest.fixture
def mock_supabase():
    """Mock Supabase client with common operations."""
    mock = MagicMock()

    # Mock table operations
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock.table.return_value.insert.return_value.execute.return_value.data = [{"id": "test-id"}]
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []
    mock.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []

    # Mock RPC calls
    mock.rpc.return_value.execute.return_value.data = []

    return mock


@pytest.fixture
def mock_db_conversation():
    """Sample conversation from database."""
    return {
        "follower_id": "follower_123",
        "creator_id": "manel",
        "platform": "instagram",
        "name": "Test User",
        "username": "testuser",
        "purchase_intent": 0.5,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }


@pytest.fixture
def mock_db_message():
    """Sample message from database."""
    return {
        "id": "msg_123",
        "conversation_id": "conv_123",
        "sender": "follower",
        "content": "Hola, me interesa tu curso",
        "platform": "instagram",
        "timestamp": datetime.now().isoformat()
    }


# =============================================================================
# API MOCK FIXTURES
# =============================================================================

@pytest.fixture
def mock_openai():
    """Mock OpenAI client for embeddings and completions."""
    mock = MagicMock()

    # Mock embeddings
    mock_embedding = MagicMock()
    mock_embedding.data = [MagicMock(embedding=[0.1] * 1536)]
    mock.embeddings.create.return_value = mock_embedding

    # Mock completions
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Mock response"))]
    mock.chat.completions.create.return_value = mock_completion

    return mock


@pytest.fixture
def mock_instagram_api():
    """Mock Instagram Graph API responses."""
    return {
        "send_message": {
            "recipient_id": "12345",
            "message_id": "msg_abc123"
        },
        "get_profile": {
            "id": "12345",
            "username": "testuser",
            "name": "Test User"
        },
        "webhook_message": {
            "object": "instagram",
            "entry": [{
                "id": "page_123",
                "time": 1234567890,
                "messaging": [{
                    "sender": {"id": "user_123"},
                    "recipient": {"id": "page_123"},
                    "timestamp": 1234567890,
                    "message": {
                        "mid": "msg_123",
                        "text": "Hello!"
                    }
                }]
            }]
        }
    }


@pytest.fixture
def mock_paypal_api():
    """Mock PayPal API responses."""
    return {
        "order": {
            "id": "ORDER-123",
            "status": "COMPLETED",
            "purchase_units": [{
                "amount": {"currency_code": "EUR", "value": "99.00"},
                "description": "Test Product"
            }]
        },
        "webhook": {
            "id": "WH-123",
            "event_type": "PAYMENT.SALE.COMPLETED",
            "resource": {
                "id": "SALE-123",
                "amount": {"total": "99.00", "currency": "EUR"},
                "state": "completed"
            }
        }
    }


# =============================================================================
# SIGNAL & SCORING FIXTURES
# =============================================================================

@pytest.fixture
def sample_signals():
    """Sample detected signals from messages."""
    return [
        {"type": "price_inquiry", "confidence": 0.9, "text": "cuánto cuesta"},
        {"type": "purchase_intent", "confidence": 0.85, "text": "quiero comprar"},
        {"type": "interest", "confidence": 0.7, "text": "me interesa"}
    ]


@pytest.fixture
def sample_messages_for_scoring():
    """Sample messages for intent scoring."""
    return [
        {"content": "Hola, ¿cuánto cuesta tu curso?", "expected_intent": "high"},
        {"content": "Solo estoy mirando", "expected_intent": "low"},
        {"content": "Quiero comprar ahora mismo", "expected_intent": "very_high"},
        {"content": "Gracias por la info", "expected_intent": "medium"},
    ]


@pytest.fixture
def intent_score_thresholds():
    """Thresholds for purchase intent classification."""
    return {
        "very_high": 0.8,
        "high": 0.6,
        "medium": 0.4,
        "low": 0.2,
        "none": 0.0
    }


# =============================================================================
# RAG FIXTURES
# =============================================================================

@pytest.fixture
def sample_knowledge_base():
    """Sample knowledge base documents."""
    return [
        {
            "id": "kb_1",
            "content": "El curso de marketing digital cuesta 99€ e incluye 20 horas de contenido.",
            "type": "product",
            "embedding": [0.1] * 1536
        },
        {
            "id": "kb_2",
            "content": "Ofrecemos garantía de devolución de 30 días sin preguntas.",
            "type": "faq",
            "embedding": [0.2] * 1536
        },
        {
            "id": "kb_3",
            "content": "Las clases en vivo son todos los martes a las 19:00 hora España.",
            "type": "schedule",
            "embedding": [0.3] * 1536
        }
    ]


@pytest.fixture
def sample_rag_query():
    """Sample RAG query and expected response."""
    return {
        "query": "¿Cuánto cuesta el curso?",
        "expected_sources": ["kb_1"],
        "expected_keywords": ["99€", "marketing digital"]
    }


# =============================================================================
# WEBHOOK FIXTURES
# =============================================================================

@pytest.fixture
def instagram_webhook_challenge():
    """Instagram webhook verification challenge."""
    return {
        "hub.mode": "subscribe",
        "hub.verify_token": "test-verify-token",
        "hub.challenge": "challenge_code_123"
    }


@pytest.fixture
def meta_webhook_signature():
    """Generate valid Meta webhook signature."""
    import hmac
    import hashlib

    def generate(payload: str, secret: str = "test-secret") -> str:
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    return generate


# =============================================================================
# NURTURING FIXTURES
# =============================================================================

@pytest.fixture
def sample_nurturing_sequence():
    """Sample nurturing sequence configuration."""
    return {
        "id": "seq_1",
        "type": "interest_cold",
        "name": "Cold Interest Follow-up",
        "is_active": True,
        "steps": [
            {"delay_hours": 24, "message": "Hey! ¿Sigues interesado en el curso?"},
            {"delay_hours": 72, "message": "Te cuento que tenemos descuento del 20%..."},
            {"delay_hours": 168, "message": "Última oportunidad para el descuento!"}
        ],
        "enrolled_count": 15,
        "sent_count": 45
    }


@pytest.fixture
def sample_enrolled_follower():
    """Sample enrolled follower in nurturing sequence."""
    return {
        "follower_id": "follower_123",
        "sequence_id": "seq_1",
        "current_step": 0,
        "enrolled_at": datetime.now().isoformat(),
        "next_send_at": (datetime.now() + timedelta(hours=24)).isoformat(),
        "status": "active"
    }


# =============================================================================
# UTILITY FIXTURES
# =============================================================================

@pytest.fixture
def freeze_time():
    """Fixture to freeze time for deterministic tests."""
    from unittest.mock import patch
    from datetime import datetime

    frozen = datetime(2024, 1, 15, 12, 0, 0)

    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value = frozen
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        yield frozen


@pytest.fixture
def performance_timer():
    """Timer for performance tests."""
    import time

    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def start(self):
            self.start_time = time.perf_counter()

        def stop(self):
            self.end_time = time.perf_counter()
            return self.elapsed_ms

        @property
        def elapsed_ms(self):
            if self.start_time and self.end_time:
                return (self.end_time - self.start_time) * 1000
            return 0

    return Timer()


# =============================================================================
# CLEANUP FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset any singletons between tests."""
    yield
    # Add singleton reset logic here if needed


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear any caches between tests."""
    yield
    # Add cache clearing logic here if needed
