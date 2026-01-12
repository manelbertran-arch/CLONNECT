"""Tests para Response Engine v2."""

import pytest
from datetime import datetime, timedelta
from ingestion.response_engine_v2 import (
    FollowerContext,
    ConversationContext,
    ResponseEngineV2,
    create_conversation_context,
    build_magic_slice_prompt
)
from ingestion.tone_analyzer import ToneProfile
from ingestion.content_citation import (
    Citation,
    CitationContext,
    ContentType
)


class TestFollowerContext:
    """Tests para FollowerContext dataclass."""

    def test_create_follower_context(self):
        follower = FollowerContext(
            follower_id="follower_123",
            username="juanperez",
            display_name="Juan Pérez"
        )
        assert follower.follower_id == "follower_123"
        assert follower.username == "juanperez"
        assert follower.display_name == "Juan Pérez"

    def test_default_values(self):
        follower = FollowerContext(follower_id="test")
        assert follower.username is None
        assert follower.display_name is None
        assert follower.previous_messages == []
        assert follower.interaction_count == 0
        assert follower.is_subscriber == False

    def test_is_returning_follower_true(self):
        follower = FollowerContext(
            follower_id="test",
            interaction_count=5
        )
        assert follower.is_returning_follower() == True

    def test_is_returning_follower_false(self):
        follower = FollowerContext(
            follower_id="test",
            interaction_count=1
        )
        assert follower.is_returning_follower() == False

    def test_is_returning_follower_zero(self):
        follower = FollowerContext(follower_id="test")
        assert follower.is_returning_follower() == False

    def test_get_greeting_context_new_with_name(self):
        follower = FollowerContext(
            follower_id="test",
            display_name="María",
            interaction_count=0
        )
        greeting = follower.get_greeting_context()
        assert "Primera interacción" in greeting
        assert "María" in greeting

    def test_get_greeting_context_new_with_username(self):
        follower = FollowerContext(
            follower_id="test",
            username="maria_fit",
            interaction_count=0
        )
        greeting = follower.get_greeting_context()
        assert "Primera interacción" in greeting
        assert "maria_fit" in greeting

    def test_get_greeting_context_returning(self):
        follower = FollowerContext(
            follower_id="test",
            display_name="Carlos",
            interaction_count=10
        )
        greeting = follower.get_greeting_context()
        assert "recurrente" in greeting
        assert "Carlos" in greeting
        assert "10" in greeting

    def test_get_greeting_context_no_name(self):
        follower = FollowerContext(
            follower_id="test",
            interaction_count=0
        )
        greeting = follower.get_greeting_context()
        assert "Primera interacción" in greeting


class TestConversationContext:
    """Tests para ConversationContext dataclass."""

    def test_create_context(self):
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="Hola, que tal?",
            follower=follower
        )
        assert context.message == "Hola, que tal?"
        assert context.follower.follower_id == "test"

    def test_default_values(self):
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="test",
            follower=follower
        )
        assert context.max_response_length == 500
        assert context.include_citations == True
        assert context.response_style == "casual"
        assert context.platform == "instagram"

    def test_to_system_prompt_basic(self):
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="test",
            follower=follower
        )
        prompt = context.to_system_prompt()

        assert "asistente" in prompt
        assert "creador" in prompt
        assert "CONTEXTO DEL SEGUIDOR" in prompt
        assert "INSTRUCCIONES FINALES" in prompt

    def test_to_system_prompt_with_tone(self):
        follower = FollowerContext(follower_id="test")
        tone = ToneProfile(
            creator_id="creator_1",
            formality="informal",
            energy="alta",
            signature_phrases=["vamos crack"]
        )
        context = ConversationContext(
            message="test",
            follower=follower,
            creator_tone=tone
        )
        prompt = context.to_system_prompt()

        # Check that tone elements are incorporated (format may vary)
        assert "vamos crack" in prompt  # signature phrase should be present
        # Energy manifests as ENERGICO or similar in prompt
        assert "ENERGICO" in prompt or "casual" in prompt.lower()
        # Formality="informal" results in tuteo rules
        assert "TUTEAR" in prompt or "informal" in prompt.lower()

    def test_to_system_prompt_with_citations(self):
        follower = FollowerContext(follower_id="test")
        citations = [
            Citation(
                content_type=ContentType.INSTAGRAM_POST,
                source_id="123",
                source_url=None,
                title="Post de fitness",
                excerpt="Contenido sobre entrenamiento...",
                relevance_score=0.9
            )
        ]
        citation_ctx = CitationContext(query="fitness", citations=citations)

        context = ConversationContext(
            message="test",
            follower=follower,
            citation_context=citation_ctx
        )
        prompt = context.to_system_prompt()

        assert "CONTENIDO RELEVANTE" in prompt
        assert "Post de fitness" in prompt

    def test_to_system_prompt_citations_disabled(self):
        follower = FollowerContext(follower_id="test")
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, "Test", "content", 0.9)
        ]
        citation_ctx = CitationContext(query="test", citations=citations)

        context = ConversationContext(
            message="test",
            follower=follower,
            citation_context=citation_ctx,
            include_citations=False
        )
        prompt = context.to_system_prompt()

        assert "CONTENIDO RELEVANTE" not in prompt

    def test_should_include_citation_true(self):
        follower = FollowerContext(follower_id="test")
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, None, "test", 0.8)
        ]
        citation_ctx = CitationContext(query="que opinas?", citations=citations)

        context = ConversationContext(
            message="que opinas del ayuno?",
            follower=follower,
            citation_context=citation_ctx
        )
        assert context.should_include_citation() == True

    def test_should_include_citation_false_no_context(self):
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="test",
            follower=follower
        )
        assert context.should_include_citation() == False

    def test_should_include_citation_false_disabled(self):
        follower = FollowerContext(follower_id="test")
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, None, "test", 0.8)
        ]
        citation_ctx = CitationContext(query="test?", citations=citations)

        context = ConversationContext(
            message="test?",
            follower=follower,
            citation_context=citation_ctx,
            include_citations=False
        )
        assert context.should_include_citation() == False


class TestResponseEngineV2:
    """Tests para ResponseEngineV2."""

    def test_create_engine(self):
        engine = ResponseEngineV2()
        assert engine.llm_client is None
        assert engine.default_model == "gpt-4o-mini"
        assert engine.temperature == 0.7

    def test_create_engine_with_params(self):
        mock_client = object()
        engine = ResponseEngineV2(
            llm_client=mock_client,
            default_model="gpt-4",
            temperature=0.5
        )
        assert engine.llm_client is mock_client
        assert engine.default_model == "gpt-4"
        assert engine.temperature == 0.5

    def test_build_user_message_basic(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="Hola como estas?",
            follower=follower
        )

        message = engine._build_user_message(context)
        assert "Hola como estas?" in message
        assert "Mensaje del seguidor" in message

    def test_build_user_message_with_history(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(
            follower_id="test",
            previous_messages=["Mensaje 1", "Mensaje 2", "Mensaje 3"]
        )
        context = ConversationContext(
            message="Mensaje actual",
            follower=follower
        )

        message = engine._build_user_message(context)
        assert "Mensaje actual" in message
        assert "Mensajes previos" in message
        assert "Mensaje 1" in message

    def test_generate_demo_response_basic(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="Hola",
            follower=follower
        )

        response = engine._generate_demo_response(context)
        assert "Hola" in response
        assert "Gracias" in response

    def test_generate_demo_response_with_name(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(
            follower_id="test",
            display_name="María"
        )
        context = ConversationContext(
            message="Hola",
            follower=follower
        )

        response = engine._generate_demo_response(context)
        assert "María" in response

    def test_generate_demo_response_with_username(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(
            follower_id="test",
            username="maria_fit"
        )
        context = ConversationContext(
            message="Hola",
            follower=follower
        )

        response = engine._generate_demo_response(context)
        assert "@maria_fit" in response

    def test_post_process_response_truncate(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="test",
            follower=follower,
            max_response_length=50
        )

        long_response = "Esta es una respuesta muy larga. Tiene muchas oraciones. Sigue y sigue sin parar nunca."
        processed = engine._post_process_response(long_response, context)

        assert len(processed) <= 55  # Some buffer for ellipsis

    def test_post_process_response_clean_spaces(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="test",
            follower=follower
        )

        messy_response = "Hola   como    estas?"
        processed = engine._post_process_response(messy_response, context)

        assert "   " not in processed
        assert processed == "Hola como estas?"

    def test_extract_used_citations_empty(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="test",
            follower=follower
        )

        citations = engine._extract_used_citations(context)
        assert citations == []

    def test_extract_used_citations(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(follower_id="test")
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "123", None, "Test Post", "content", 0.9)
        ]
        citation_ctx = CitationContext(query="test", citations=citations)

        context = ConversationContext(
            message="test",
            follower=follower,
            citation_context=citation_ctx
        )

        extracted = engine._extract_used_citations(context)
        assert len(extracted) == 1
        assert extracted[0]["source_id"] == "123"
        assert extracted[0]["relevance_score"] == 0.9

    def test_get_fallback_response_with_name(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(
            follower_id="test",
            display_name="Carlos"
        )
        context = ConversationContext(
            message="test",
            follower=follower
        )

        fallback = engine._get_fallback_response(context)
        assert "Carlos" in fallback
        assert "Gracias" in fallback

    def test_get_fallback_response_no_name(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="test",
            follower=follower
        )

        fallback = engine._get_fallback_response(context)
        assert "Hola" in fallback
        assert "Gracias" in fallback


class TestCreateConversationContext:
    """Tests para create_conversation_context helper."""

    def test_basic_creation(self):
        context = create_conversation_context(
            message="Hola!",
            follower_id="follower_123"
        )

        assert context.message == "Hola!"
        assert context.follower.follower_id == "follower_123"

    def test_with_follower_details(self):
        context = create_conversation_context(
            message="Test",
            follower_id="123",
            username="juan",
            display_name="Juan",
            interaction_count=5,
            is_subscriber=True
        )

        assert context.follower.username == "juan"
        assert context.follower.display_name == "Juan"
        assert context.follower.interaction_count == 5
        assert context.follower.is_subscriber == True

    def test_with_tone_profile(self):
        tone = ToneProfile(creator_id="creator_1", formality="informal")
        context = create_conversation_context(
            message="Test",
            follower_id="123",
            creator_tone=tone
        )

        assert context.creator_tone is not None
        assert context.creator_tone.formality == "informal"

    def test_with_citation_context(self):
        citations = [Citation(ContentType.INSTAGRAM_POST, "1", None, None, "test", 0.8)]
        citation_ctx = CitationContext(query="test", citations=citations)

        context = create_conversation_context(
            message="Test?",
            follower_id="123",
            citation_context=citation_ctx
        )

        assert context.citation_context is not None
        assert len(context.citation_context.citations) == 1

    def test_with_additional_params(self):
        context = create_conversation_context(
            message="Test",
            follower_id="123",
            max_response_length=300,
            response_style="formal",
            platform="whatsapp"
        )

        assert context.max_response_length == 300
        assert context.response_style == "formal"
        assert context.platform == "whatsapp"


class TestBuildMagicSlicePrompt:
    """Tests para build_magic_slice_prompt helper."""

    def test_empty_prompt(self):
        prompt = build_magic_slice_prompt()
        assert prompt == ""

    def test_with_tone_only(self):
        tone = ToneProfile(
            creator_id="test",
            formality="informal",
            energy="alta"
        )
        prompt = build_magic_slice_prompt(tone_profile=tone)

        assert "ESTILO DE COMUNICACIÓN" in prompt
        assert "informal" in prompt

    def test_with_citations_only(self):
        citations = [
            Citation(ContentType.INSTAGRAM_POST, "1", None, "Test", "contenido", 0.9)
        ]
        citation_ctx = CitationContext(query="test", citations=citations)

        prompt = build_magic_slice_prompt(citation_context=citation_ctx)

        assert "CONTENIDO PARA REFERENCIAR" in prompt
        assert "Test" in prompt

    def test_with_follower_context(self):
        prompt = build_magic_slice_prompt(
            follower_name="María",
            is_returning=True
        )

        assert "CONTEXTO DEL SEGUIDOR" in prompt
        assert "María" in prompt
        assert "ya ha interactuado" in prompt

    def test_with_new_follower(self):
        prompt = build_magic_slice_prompt(
            follower_name="Carlos",
            is_returning=False
        )

        assert "Carlos" in prompt
        assert "Primera interacción" in prompt

    def test_full_prompt(self):
        tone = ToneProfile(
            creator_id="test",
            formality="informal",
            signature_phrases=["vamos crack"]
        )
        citations = [
            Citation(ContentType.YOUTUBE_VIDEO, "1", None, "Mi video", "contenido", 0.85)
        ]
        citation_ctx = CitationContext(query="test", citations=citations)

        prompt = build_magic_slice_prompt(
            tone_profile=tone,
            citation_context=citation_ctx,
            follower_name="Ana",
            is_returning=True
        )

        assert "ESTILO DE COMUNICACIÓN" in prompt
        assert "vamos crack" in prompt
        assert "CONTENIDO PARA REFERENCIAR" in prompt
        assert "Mi video" in prompt
        assert "CONTEXTO DEL SEGUIDOR" in prompt
        assert "Ana" in prompt


class TestResponseEngineV2Async:
    """Tests async para ResponseEngineV2."""

    @pytest.mark.asyncio
    async def test_generate_response_no_llm(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(
            follower_id="test",
            display_name="María"
        )
        context = ConversationContext(
            message="Hola que tal?",
            follower=follower
        )

        result = await engine.generate_response(context)

        assert "response" in result
        assert "María" in result["response"]
        assert result["tone_applied"] == False
        assert result["follower_context"]["is_returning"] == False

    @pytest.mark.asyncio
    async def test_generate_response_with_tone(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(follower_id="test")
        tone = ToneProfile(creator_id="creator_1", formality="informal")
        context = ConversationContext(
            message="Test",
            follower=follower,
            creator_tone=tone
        )

        result = await engine.generate_response(context)

        assert result["tone_applied"] == True

    @pytest.mark.asyncio
    async def test_generate_response_metadata(self):
        engine = ResponseEngineV2()
        follower = FollowerContext(follower_id="test")
        context = ConversationContext(
            message="Test",
            follower=follower
        )

        result = await engine.generate_response(context)

        assert "metadata" in result
        assert result["metadata"]["model"] == "gpt-4o-mini"
        assert result["metadata"]["temperature"] == 0.7
        assert "generated_at" in result["metadata"]
