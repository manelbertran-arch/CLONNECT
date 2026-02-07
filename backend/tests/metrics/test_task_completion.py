import pytest
from metrics.collectors.task_completion import TaskCompletionCollector, TaskOutcome, TaskType


class TestTaskCompletion:
    @pytest.fixture
    def collector(self):
        return TaskCompletionCollector(creator_id="test")

    def test_detects_purchase_completion(self, collector):
        messages = [
            {"content": "Hola, quiero comprar el curso", "role": "lead"},
            {"content": "Perfecto! Te cuento sobre el programa...", "role": "assistant"},
            {"content": "Gracias, ya hice la compra!", "role": "lead"},
        ]

        task_type = collector._detect_task_type(messages)
        outcome = collector._detect_outcome(messages)

        assert task_type == TaskType.PURCHASE
        assert outcome == TaskOutcome.COMPLETED

    def test_detects_info_completion(self, collector):
        messages = [
            {"content": "Quiero saber sobre el curso", "role": "lead"},
            {"content": "El programa incluye...", "role": "assistant"},
            {"content": "Vale gracias, me queda claro", "role": "lead"},
        ]

        outcome = collector._detect_outcome(messages)
        assert outcome == TaskOutcome.COMPLETED

    def test_detects_abandonment(self, collector):
        messages = [
            {"content": "Hola, info sobre el programa", "role": "lead"},
            {"content": "El programa tiene un valor de 497", "role": "assistant"},
            {"content": "No gracias, demasiado caro", "role": "lead"},
            {"content": "Lo pienso", "role": "lead"},
            {"content": "No me interesa ya", "role": "lead"},
        ]

        outcome = collector._detect_outcome(messages)
        assert outcome == TaskOutcome.ABANDONED

    def test_detects_escalation(self, collector):
        messages = [
            {"content": "No entiendo", "role": "lead"},
            {"content": "Te explico...", "role": "assistant"},
            {"content": "Quiero hablar con una persona real", "role": "lead"},
        ]

        outcome = collector._detect_outcome(messages)
        assert outcome == TaskOutcome.ESCALATED

    def test_detects_booking_type(self, collector):
        messages = [
            {"content": "Quiero agendar una cita", "role": "lead"},
            {"content": "Te paso el link de reserva", "role": "assistant"},
            {"content": "Cita confirmada, nos vemos!", "role": "lead"},
        ]

        outcome = collector._detect_outcome(messages)
        assert outcome == TaskOutcome.COMPLETED

    def test_detects_lead_qualified_type(self, collector):
        messages = [
            {"content": "Cuanto cuesta el curso?", "role": "lead"},
        ]

        task_type = collector._detect_task_type(messages)
        assert task_type == TaskType.LEAD_QUALIFIED

    def test_unknown_task_type(self, collector):
        messages = [
            {"content": "hola", "role": "lead"},
        ]

        task_type = collector._detect_task_type(messages)
        assert task_type == TaskType.UNKNOWN

    def test_pending_outcome_no_patterns(self, collector):
        messages = [
            {"content": "hola que tal", "role": "lead"},
            {"content": "bien y tu?", "role": "assistant"},
            {"content": "todo bien!", "role": "lead"},
        ]

        outcome = collector._detect_outcome(messages)
        assert outcome == TaskOutcome.PENDING
