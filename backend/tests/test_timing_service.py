"""Tests para el servicio de timing."""
import pytest

from services.timing_service import TimingConfig, TimingService


@pytest.fixture
def timing_service():
    return TimingService()


class TestDelayCalculation:
    """Tests para cálculo de delay."""

    def test_minimum_delay(self, timing_service):
        """Delay mínimo de 2 segundos."""
        for _ in range(20):
            delay = timing_service.calculate_delay(10, 10)
            assert delay >= 2.0, f"Delay {delay} es menor que 2 segundos"

    def test_maximum_delay(self, timing_service):
        """Delay máximo de 30 segundos."""
        for _ in range(20):
            delay = timing_service.calculate_delay(1000, 1000)
            assert delay <= 30.0, f"Delay {delay} es mayor que 30 segundos"

    def test_longer_response_more_delay(self, timing_service):
        """Respuestas largas deben tener más delay."""
        short_delays = [timing_service.calculate_delay(10, 10) for _ in range(10)]
        long_delays = [timing_service.calculate_delay(200, 10) for _ in range(10)]

        avg_short = sum(short_delays) / len(short_delays)
        avg_long = sum(long_delays) / len(long_delays)

        assert avg_long > avg_short, (
            f"Avg long ({avg_long}) debería ser > avg short ({avg_short})"
        )

    def test_delay_has_variation(self, timing_service):
        """Delay debe variar entre llamadas."""
        delays = [timing_service.calculate_delay(50, 20) for _ in range(10)]
        unique = set(delays)
        assert len(unique) > 1, "Delays deberían variar"


class TestActiveHours:
    """Tests para horarios activos."""

    def test_config_defaults(self, timing_service):
        """Verificar configuración por defecto."""
        assert timing_service.config.active_hours_start == 8
        assert timing_service.config.active_hours_end == 23
        assert timing_service.config.timezone == "Europe/Madrid"


class TestOffHoursResponse:
    """Tests para respuestas fuera de horario."""

    def test_off_hours_sometimes_responds(self, timing_service):
        """10% de probabilidad de responder fuera de horario."""
        responses = [timing_service.should_respond_off_hours() for _ in range(100)]
        true_count = sum(responses)
        # Debería estar entre 2 y 25 (10% ± variación)
        assert 2 <= true_count <= 25, f"Off hours responses: {true_count}/100"


class TestDelayForRealResponses:
    """Tests con respuestas reales."""

    def test_short_emoji_response(self, timing_service):
        delay = timing_service.get_delay_for_response("💙", "Gracias!")
        assert 2.0 <= delay <= 5.0

    def test_medium_response(self, timing_service):
        delay = timing_service.get_delay_for_response(
            "El precio es 150€ la sesión individual 😊",
            "Cuánto cuesta el coaching?",
        )
        assert 2.0 <= delay <= 10.0

    def test_long_response(self, timing_service):
        long_response = (
            "El Círculo de Hombres es una comunidad donde nos reunimos "
            "semanalmente para trabajar temas de desarrollo personal masculino. "
            "Incluye sesiones grupales, recursos y acceso a eventos especiales."
        )
        delay = timing_service.get_delay_for_response(
            long_response, "Qué es el Círculo de Hombres?"
        )
        assert 3.0 <= delay <= 15.0


class TestConfiguration:
    """Tests para configuración personalizada."""

    def test_custom_config(self):
        config = TimingConfig(
            min_delay=1.0,
            max_delay=10.0,
            chars_per_second=100.0,
        )
        service = TimingService(config)

        assert service.config.min_delay == 1.0
        assert service.config.max_delay == 10.0

    def test_custom_min_respected(self):
        config = TimingConfig(min_delay=5.0)
        service = TimingService(config)

        for _ in range(10):
            delay = service.calculate_delay(10, 10)
            assert delay >= 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
