"""
Tests for ConversationBoundaryDetector.

Covers all 10 functional test cases from the spec:
1. Messages 4h apart → different session
2. Messages 5 min apart → same session
3. "Hola" after 2h gap → new session
4. Topic shift without time gap → same session (time < threshold)
5. Resume previous topic after short break → same session
6. 50-message conversation over 3 hours → all same session
7. Lead messages 3 different topics in 1 day → depends on time gaps
8. Works for Catalan? Spanish? English? Mixed?
9. Works for Stefano's leads (different style)
10. Retroactive tagging on messages → sessions make sense
"""

import pytest
from datetime import datetime, timedelta, timezone

from core.conversation_boundary import ConversationBoundaryDetector, segment_sessions


def _msg(role: str, content: str, ts: datetime) -> dict:
    """Helper to create a message dict."""
    return {"role": role, "content": content, "created_at": ts}


def _ts(base: datetime, minutes: int = 0, hours: int = 0, days: int = 0) -> datetime:
    """Helper to create timestamps relative to a base."""
    return base + timedelta(minutes=minutes, hours=hours, days=days)


BASE = datetime(2026, 3, 31, 10, 0, 0, tzinfo=timezone.utc)


class TestTimeBoundaries:
    """Test 1, 2: Time gap thresholds."""

    def test_4h_gap_different_session(self):
        """Test 1: Messages 4h apart → different session."""
        msgs = [
            _msg("user", "Quiero apuntarme a barre", BASE),
            _msg("assistant", "Genial! Dime tu nombre", _ts(BASE, minutes=1)),
            _msg("user", "Com esta la teva mare??", _ts(BASE, hours=4, minutes=5)),
            _msg("assistant", "Baby demà et va bé?", _ts(BASE, hours=4, minutes=6)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2
        assert len(sessions[0]) == 2
        assert len(sessions[1]) == 2

    def test_5min_gap_same_session(self):
        """Test 2: Messages 5 min apart → same session."""
        msgs = [
            _msg("user", "Hola", BASE),
            _msg("assistant", "Hola! Que tal?", _ts(BASE, minutes=1)),
            _msg("user", "Quiero info sobre clases", _ts(BASE, minutes=5)),
            _msg("assistant", "Claro! Tenemos...", _ts(BASE, minutes=6)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_24h_always_new_session(self):
        """Messages 24h+ apart → always new session."""
        msgs = [
            _msg("user", "Vale", BASE),
            _msg("user", "Vale", _ts(BASE, days=1, minutes=5)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2


class TestGreetingBoundary:
    """Test 3: Greeting after gap → new session."""

    def test_hola_after_2h_gap_new_session(self):
        """Test 3: 'Hola' after 2h gap → new session."""
        msgs = [
            _msg("user", "Perfecto, gracias!", BASE),
            _msg("assistant", "De nada!", _ts(BASE, minutes=1)),
            _msg("user", "Hola! Una pregunta", _ts(BASE, hours=2)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2

    def test_greeting_without_gap_same_session(self):
        """Greeting within 5 min → same session (just polite)."""
        msgs = [
            _msg("user", "Ok gracias", BASE),
            _msg("assistant", "De nada!", _ts(BASE, minutes=1)),
            _msg("user", "Hola, otra cosa", _ts(BASE, minutes=3)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_bon_dia_after_gap(self):
        """Catalan greeting 'Bon dia' after 1h gap → new session."""
        msgs = [
            _msg("user", "Adeu!", BASE),
            _msg("assistant", "Adeu!", _ts(BASE, minutes=1)),
            _msg("user", "Bon dia! Com estàs?", _ts(BASE, hours=1)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2


class TestTopicShift:
    """Test 4, 5: Topic shifts and resumption."""

    def test_topic_shift_without_time_gap_same_session(self):
        """Test 4: Topic shift without time gap → same session (time rules)."""
        msgs = [
            _msg("user", "Quiero info sobre barre", BASE),
            _msg("assistant", "Tenemos clases de barre lunes y miércoles", _ts(BASE, minutes=1)),
            _msg("user", "Oye y como está tu madre?", _ts(BASE, minutes=2)),
            _msg("assistant", "Está mejor, gracias!", _ts(BASE, minutes=3)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_resume_after_short_break_same_session(self):
        """Test 5: Resume topic after 20 min break → same session."""
        msgs = [
            _msg("user", "Cuánto cuestan las clases?", BASE),
            _msg("assistant", "Son 45€ al mes", _ts(BASE, minutes=1)),
            _msg("user", "Y hay descuento para 3 meses?", _ts(BASE, minutes=20)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1


class TestLongConversation:
    """Test 6: Long conversation over hours."""

    def test_50_messages_3_hours_same_session(self):
        """Test 6: 50 messages over 3 hours with small gaps → all same session."""
        msgs = []
        t = BASE
        for i in range(50):
            role = "user" if i % 2 == 0 else "assistant"
            gap = timedelta(minutes=random_gap(i))  # 1-5 min gaps
            t = t + gap
            msgs.append(_msg(role, f"Message {i}", t))
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_messages_with_4h_gap_in_middle(self):
        """Conversation with a 4h gap in the middle → 2 sessions."""
        msgs = []
        t = BASE
        for i in range(10):
            t = t + timedelta(minutes=2)
            msgs.append(_msg("user" if i % 2 == 0 else "assistant", f"Msg {i}", t))
        # 4h gap
        t = t + timedelta(hours=4, minutes=10)
        for i in range(10, 20):
            t = t + timedelta(minutes=2)
            msgs.append(_msg("user" if i % 2 == 0 else "assistant", f"Msg {i}", t))
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2


class TestMultipleTopicsOneDay:
    """Test 7: Multiple topics in one day."""

    def test_3_conversations_1_day(self):
        """Test 7: 3 separate conversations in 1 day (with >4h gaps)."""
        msgs = [
            # Morning conversation
            _msg("user", "Buenos días! Info sobre yoga?", BASE),
            _msg("assistant", "Buenos días! Tenemos yoga los martes", _ts(BASE, minutes=1)),
            _msg("user", "Perfecto, me apunto", _ts(BASE, minutes=3)),
            _msg("assistant", "Genial!", _ts(BASE, minutes=4)),
            # Afternoon (5h gap)
            _msg("user", "Oye, se me olvidó preguntar el horario", _ts(BASE, hours=5)),
            _msg("assistant", "Es a las 18:00", _ts(BASE, hours=5, minutes=1)),
            # Evening (5h gap)
            _msg("user", "Hola! Puedo llevar a una amiga?", _ts(BASE, hours=10)),
            _msg("assistant", "Claro! Primera clase gratis", _ts(BASE, hours=10, minutes=1)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 3


class TestMultilingual:
    """Test 8: Works for Catalan, Spanish, English, mixed."""

    def test_catalan_greetings(self):
        """Catalan greetings detected."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("Bon dia! Com vas?")
        assert detector._is_greeting("Bona tarda")
        assert detector._is_greeting("Ei! Una cosa")
        assert detector._is_greeting("Hola, tinc una pregunta")

    def test_spanish_greetings(self):
        """Spanish greetings detected."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("Hola!")
        assert detector._is_greeting("Buenos días")
        assert detector._is_greeting("Buenas tardes")
        assert detector._is_greeting("Hey que tal")
        assert detector._is_greeting("Buenas!")

    def test_english_greetings(self):
        """English greetings detected."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("Hi there!")
        assert detector._is_greeting("Hello")
        assert detector._is_greeting("Hey!")
        assert detector._is_greeting("Good morning")

    def test_portuguese_greetings(self):
        """Portuguese greetings detected."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("Olá! Tudo bem?")
        assert detector._is_greeting("Oi!")
        assert detector._is_greeting("Bom dia")

    def test_french_greetings(self):
        """French greetings detected (BUG-CB-03 fix)."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("Bonjour!")
        assert detector._is_greeting("Salut, comment ça va?")
        assert detector._is_greeting("Coucou")
        assert detector._is_greeting("Bonsoir")

    def test_german_greetings(self):
        """German greetings detected (BUG-CB-03 fix)."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("Hallo!")
        assert detector._is_greeting("Guten Morgen")
        assert detector._is_greeting("Guten Tag")
        assert detector._is_greeting("Moin!")
        assert detector._is_greeting("Servus")

    def test_arabic_greetings(self):
        """Arabic greetings detected — native + transliterated (BUG-CB-03 fix)."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("مرحبا")
        assert detector._is_greeting("السلام عليكم")
        assert detector._is_greeting("marhaba")
        assert detector._is_greeting("salam")

    def test_cjk_greetings(self):
        """Japanese, Korean, Chinese greetings detected (BUG-CB-03 fix)."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("こんにちは")
        assert detector._is_greeting("おはよう")
        assert detector._is_greeting("안녕하세요")
        assert detector._is_greeting("你好")
        assert detector._is_greeting("您好")

    def test_non_greetings(self):
        """Non-greetings not detected."""
        detector = ConversationBoundaryDetector()
        assert not detector._is_greeting("Quiero info")
        assert not detector._is_greeting("45€ me parece bien")
        assert not detector._is_greeting("Vale, perfecto")
        assert not detector._is_greeting("😂😂")

    def test_farewells(self):
        """Farewell detection multilingual."""
        detector = ConversationBoundaryDetector()
        assert detector._is_farewell("Adéu!")
        assert detector._is_farewell("Adiós, hasta luego")
        assert detector._is_farewell("Bye!")
        assert detector._is_farewell("Hasta mañana")
        assert detector._is_farewell("Nos vemos")
        assert not detector._is_farewell("Quiero más info")


class TestDifferentCreatorStyles:
    """Test 9: Works for different creator styles."""

    def test_italian_style_messages(self):
        """Italian-style messages (Stefano) with greetings."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("Ciao!")
        assert detector._is_greeting("Buongiorno")
        assert detector._is_greeting("Salve")

    def test_informal_style(self):
        """Informal messages still detected."""
        detector = ConversationBoundaryDetector()
        assert detector._is_greeting("ey!")
        assert detector._is_greeting("eyyy")
        assert detector._is_greeting("wena!")


class TestSegmentSessions:
    """Test full segmentation pipeline."""

    def test_empty_messages(self):
        """Empty message list → empty sessions."""
        assert segment_sessions([]) == []

    def test_single_message(self):
        """Single message → one session."""
        msgs = [_msg("user", "Hola", BASE)]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1
        assert len(sessions[0]) == 1

    def test_realistic_iris_pattern(self):
        """Realistic Iris conversation pattern from the spec."""
        msgs = [
            # Monday conversation
            _msg("user", "Hola, quiero apuntarme a barre", datetime(2026, 3, 31, 10, 0, tzinfo=timezone.utc)),
            _msg("assistant", "Genial! Dime tu nombre", datetime(2026, 3, 31, 10, 1, tzinfo=timezone.utc)),
            _msg("user", "Me llamo María", datetime(2026, 3, 31, 10, 5, tzinfo=timezone.utc)),
            _msg("assistant", "Apuntada!", datetime(2026, 3, 31, 10, 6, tzinfo=timezone.utc)),
            # Thursday conversation (3 days later)
            _msg("user", "Com esta la teva mare??", datetime(2026, 4, 3, 18, 0, tzinfo=timezone.utc)),
            _msg("assistant", "Baby demà a les 11 et va bé?", datetime(2026, 4, 3, 18, 1, tzinfo=timezone.utc)),
            _msg("user", "Vale ens veiem", datetime(2026, 4, 3, 18, 2, tzinfo=timezone.utc)),
            _msg("assistant", "Perfect", datetime(2026, 4, 3, 18, 3, tzinfo=timezone.utc)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2
        assert sessions[0][0]["content"] == "Hola, quiero apuntarme a barre"
        assert sessions[1][0]["content"] == "Com esta la teva mare??"

    def test_farewell_plus_gap_new_session(self):
        """Farewell in last message + 45 min gap → new session."""
        msgs = [
            _msg("user", "Genial, gracias!", BASE),
            _msg("assistant", "De nada! Hasta luego!", _ts(BASE, minutes=1)),
            _msg("user", "Oye una cosa más", _ts(BASE, minutes=46)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2

    def test_session_ids_assigned(self):
        """Each message gets a session_id."""
        detector = ConversationBoundaryDetector()
        msgs = [
            _msg("user", "Hola", BASE),
            _msg("assistant", "Hola!", _ts(BASE, minutes=1)),
            _msg("user", "Info?", _ts(BASE, hours=5)),
        ]
        tagged = detector.tag_sessions(msgs)
        assert all("session_id" in m for m in tagged)
        assert tagged[0]["session_id"] == tagged[1]["session_id"]
        assert tagged[0]["session_id"] != tagged[2]["session_id"]

    def test_get_current_session(self):
        """Get only the current session's messages."""
        detector = ConversationBoundaryDetector()
        msgs = [
            _msg("user", "Old conversation", BASE),
            _msg("assistant", "Old reply", _ts(BASE, minutes=1)),
            _msg("user", "New conversation", _ts(BASE, hours=5)),
            _msg("assistant", "New reply", _ts(BASE, hours=5, minutes=1)),
        ]
        current = detector.get_current_session(msgs)
        assert len(current) == 2
        assert current[0]["content"] == "New conversation"


class TestEdgeCases:
    """Edge cases and robustness."""

    def test_messages_without_timestamps(self):
        """Messages without created_at → all in one session."""
        msgs = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hey"},
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_string_timestamps(self):
        """ISO string timestamps handled."""
        msgs = [
            {"role": "user", "content": "Hola", "created_at": "2026-03-31T10:00:00+00:00"},
            {"role": "assistant", "content": "Hey", "created_at": "2026-03-31T10:01:00+00:00"},
            {"role": "user", "content": "New topic", "created_at": "2026-03-31T15:00:00+00:00"},
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2

    def test_greeting_in_middle_of_burst_not_boundary(self):
        """'Hola' in middle of rapid exchange → NOT a boundary."""
        msgs = [
            _msg("user", "Si, quiero", BASE),
            _msg("assistant", "Genial", _ts(BASE, minutes=1)),
            _msg("user", "Hola, perdona, una duda más", _ts(BASE, minutes=2)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_malformed_timestamp_string(self):
        """Malformed timestamp string → treated as no timestamp."""
        msgs = [
            {"role": "user", "content": "Hola", "created_at": "not-a-date"},
            {"role": "assistant", "content": "Hey", "created_at": "also-bad"},
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1  # no timestamps → all same session

    def test_user_farewell_then_bot_reply_then_gap(self):
        """User says farewell, bot replies quickly, then gap → new session.
        Tests the prev_prev_msg farewell lookback logic.
        """
        msgs = [
            _msg("user", "Adéu, fins demà!", BASE),
            _msg("assistant", "Adéu!", _ts(BASE, minutes=1)),
            _msg("user", "Tinc una altra pregunta", _ts(BASE, minutes=45)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2

    def test_tag_sessions_does_not_mutate_input(self):
        """tag_sessions should NOT mutate the original messages."""
        detector = ConversationBoundaryDetector()
        msgs = [
            _msg("user", "Hola", BASE),
            _msg("assistant", "Hola!", _ts(BASE, minutes=1)),
        ]
        original_keys = set(msgs[0].keys())
        detector.tag_sessions(msgs)
        assert set(msgs[0].keys()) == original_keys  # no session_id added


class TestAssistantGapNotBoundary:
    """Critical fix: bot/creator slow replies should NOT trigger new sessions."""

    def test_bot_responds_6h_later_same_session(self):
        """Creator takes 6h to respond → same session, not new."""
        msgs = [
            _msg("user", "Cuánto cuesta el pack mensual?", BASE),
            _msg("assistant", "Son 45€/mes!", _ts(BASE, hours=6)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_bot_responds_next_day_same_session(self):
        """Creator responds next day → same session (bot response ≠ new session)."""
        msgs = [
            _msg("user", "Me interesa la clase de yoga", BASE),
            _msg("assistant", "Genial! Las clases son los martes a las 18h", _ts(BASE, days=1)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_user_returns_after_bot_slow_reply(self):
        """User → (6h) → Bot → (5min) → User = same session (bot was just slow)."""
        msgs = [
            _msg("user", "Info sobre clases?", BASE),
            _msg("assistant", "Tenemos yoga y barre!", _ts(BASE, hours=6)),
            _msg("user", "Y cuánto cuesta?", _ts(BASE, hours=6, minutes=5)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_user_returns_after_long_gap_new_session(self):
        """User → Bot → (5h gap) → User = new session (USER came back after 5h)."""
        msgs = [
            _msg("user", "Gracias!", BASE),
            _msg("assistant", "De nada!", _ts(BASE, minutes=1)),
            _msg("user", "Oye, otra cosa", _ts(BASE, hours=5)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2

    def test_1_msg_per_day_5_days_separate_sessions(self):
        """User sends 1 message per day for 5 days → 5 sessions."""
        msgs = [
            _msg("user", "Hola", BASE),
            _msg("user", "Que tal?", _ts(BASE, days=1)),
            _msg("user", "Info?", _ts(BASE, days=2)),
            _msg("user", "Gracias", _ts(BASE, days=3)),
            _msg("user", "Bye", _ts(BASE, days=4)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 5

    def test_copilot_mode_slow_approval(self):
        """Copilot mode: creator approves after 3h → same session."""
        msgs = [
            _msg("user", "Hola! Me interesa el pack premium", BASE),
            _msg("assistant", "El pack premium son 89€/mes con acceso ilimitado", _ts(BASE, hours=3)),
            _msg("user", "Perfecto, me apunto!", _ts(BASE, hours=3, minutes=2)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1


class TestDiscourseMarkers:
    """Discourse marker detection — Topic Shift Detection papers (2023-24).

    Discourse markers like "por cierto", "by the way", "otra cosa" signal
    explicit topic changes. They fire ONLY in the 30min-4h zone (same tier
    as farewell), never in <5min or 5-30min zones.
    """

    def test_discourse_marker_detection_multilingual(self):
        """Discourse markers detected across 7 languages."""
        detector = ConversationBoundaryDetector()
        # Spanish
        assert detector._is_discourse_marker("Por cierto, una cosa")
        assert detector._is_discourse_marker("Otra cosa que quería decir")
        assert detector._is_discourse_marker("Cambiando de tema")
        assert detector._is_discourse_marker("Te quería preguntar algo")
        # Catalan
        assert detector._is_discourse_marker("Per cert, una pregunta")
        assert detector._is_discourse_marker("Una altra cosa")
        # English
        assert detector._is_discourse_marker("By the way")
        assert detector._is_discourse_marker("Another thing")
        assert detector._is_discourse_marker("I wanted to ask you")
        # Portuguese
        assert detector._is_discourse_marker("A propósito")
        # Italian
        assert detector._is_discourse_marker("A proposito")
        assert detector._is_discourse_marker("Un'altra cosa")
        # French
        assert detector._is_discourse_marker("Au fait")
        assert detector._is_discourse_marker("Autre chose")
        # German
        assert detector._is_discourse_marker("Übrigens")
        assert detector._is_discourse_marker("Noch etwas")

    def test_non_discourse_markers(self):
        """Regular messages not falsely detected as discourse markers."""
        detector = ConversationBoundaryDetector()
        assert not detector._is_discourse_marker("Quiero info sobre yoga")
        assert not detector._is_discourse_marker("45€ me parece bien")
        assert not detector._is_discourse_marker("Hola!")
        assert not detector._is_discourse_marker("Vale perfecto")
        assert not detector._is_discourse_marker("")
        assert not detector._is_discourse_marker("😂😂")

    def test_discourse_marker_mid_sentence_not_detected(self):
        """'por cierto' mid-sentence should NOT match (must be at start)."""
        detector = ConversationBoundaryDetector()
        assert not detector._is_discourse_marker("Le dije por cierto que sí")
        assert not detector._is_discourse_marker("Y por cierto también")
        assert not detector._is_discourse_marker("Quiero otra cosa del menú")

    def test_discourse_marker_after_45min_new_session(self):
        """'Por cierto' after 45 min gap → new session (30min-4h zone)."""
        msgs = [
            _msg("user", "Genial, gracias!", BASE),
            _msg("assistant", "De nada!", _ts(BASE, minutes=1)),
            _msg("user", "Por cierto, quería preguntarte sobre yoga", _ts(BASE, minutes=46)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2

    def test_discourse_marker_after_2h_new_session(self):
        """'By the way' after 2h gap → new session."""
        msgs = [
            _msg("user", "Ok sounds good", BASE),
            _msg("assistant", "Great!", _ts(BASE, minutes=1)),
            _msg("user", "By the way, can I bring a friend?", _ts(BASE, hours=2)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2

    def test_discourse_marker_within_5min_same_session(self):
        """'Por cierto' within 5 min → same session (time tier overrides)."""
        msgs = [
            _msg("user", "Vale!", BASE),
            _msg("assistant", "Ok", _ts(BASE, minutes=1)),
            _msg("user", "Por cierto, otra cosa", _ts(BASE, minutes=3)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_discourse_marker_at_15min_same_session(self):
        """'Por cierto' after 15 min → same session (5-30min: only greetings)."""
        msgs = [
            _msg("user", "Vale", BASE),
            _msg("assistant", "Ok", _ts(BASE, minutes=1)),
            _msg("user", "Por cierto, una duda", _ts(BASE, minutes=16)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 1

    def test_catalan_discourse_marker_after_50min(self):
        """Catalan 'Per cert' after 50 min → new session."""
        msgs = [
            _msg("user", "Val ens veiem", BASE),
            _msg("assistant", "Perfecto", _ts(BASE, minutes=1)),
            _msg("user", "Per cert, et volia preguntar una cosa", _ts(BASE, minutes=51)),
        ]
        sessions = segment_sessions(msgs)
        assert len(sessions) == 2


def random_gap(i: int) -> int:
    """Deterministic 'random' gap for test reproducibility."""
    return 1 + (i * 7 % 5)  # 1-5 minutes
