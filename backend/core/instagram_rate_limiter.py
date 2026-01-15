"""
Instagram API Rate Limiter - Maneja rate limits con backoff exponencial.

Meta Graph API limits:
- 200 calls/user/hour para la mayoría de endpoints
- Más restrictivo para mensajes de Instagram

Implementa:
1. Backoff exponencial con retry
2. Throttling entre llamadas
3. Detección de errores de rate limit
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable
from functools import wraps
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class InstagramRateLimitError(Exception):
    """Error cuando Instagram API devuelve rate limit."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)


@dataclass
class RateLimitConfig:
    """Configuración del rate limiter."""
    max_retries: int = 5
    base_delay: float = 30.0  # segundos
    max_delay: float = 300.0  # 5 minutos máximo
    calls_per_minute: int = 20  # Throttle
    batch_size: int = 10
    batch_delay: float = 30.0  # segundos entre batches


class InstagramRateLimiter:
    """
    Rate limiter para Instagram Graph API.

    Uso:
        limiter = InstagramRateLimiter()

        async with limiter.throttle():
            response = await client.get(url)
            limiter.check_response(response)
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._last_call_time: float = 0
        self._call_count: int = 0
        self._minute_start: float = 0

    def check_response(self, response_data: Dict[str, Any]) -> None:
        """
        Verificar si la respuesta contiene un error de rate limit.

        Args:
            response_data: JSON response de la API

        Raises:
            InstagramRateLimitError: Si hay rate limit
        """
        error = response_data.get("error", {})

        # Error code 4 = Rate limit
        if error.get("code") == 4:
            message = error.get("message", "Rate limit reached")
            # Algunos errores incluyen retry_after
            retry_after = error.get("error_data", {}).get("retry_after")
            raise InstagramRateLimitError(message, retry_after)

        # Error code 17 = User request limit reached
        if error.get("code") == 17:
            raise InstagramRateLimitError(error.get("message", "User request limit"))

        # Error subcode 1349210 = Traffic limit
        if error.get("error_subcode") == 1349210:
            raise InstagramRateLimitError(error.get("message", "Traffic limit"))

    async def throttle(self) -> None:
        """
        Aplicar throttling entre llamadas.
        Espera si estamos haciendo demasiadas llamadas por minuto.
        """
        now = time.time()

        # Reset contador cada minuto
        if now - self._minute_start >= 60:
            self._minute_start = now
            self._call_count = 0

        # Si excedemos el límite, esperar
        if self._call_count >= self.config.calls_per_minute:
            wait_time = 60 - (now - self._minute_start)
            if wait_time > 0:
                logger.info(f"[RateLimiter] Throttling: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self._minute_start = time.time()
                self._call_count = 0

        # Delay mínimo entre llamadas (evitar ráfagas)
        min_interval = 60.0 / self.config.calls_per_minute
        time_since_last = now - self._last_call_time
        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)

        self._last_call_time = time.time()
        self._call_count += 1

    def calculate_backoff(self, attempt: int, retry_after: Optional[int] = None) -> float:
        """
        Calcular tiempo de espera con backoff exponencial.

        Args:
            attempt: Número de intento (0-indexed)
            retry_after: Tiempo sugerido por la API (opcional)

        Returns:
            Segundos a esperar
        """
        if retry_after:
            return min(retry_after, self.config.max_delay)

        # Backoff exponencial: 30s, 60s, 120s, 240s...
        delay = self.config.base_delay * (2 ** attempt)
        return min(delay, self.config.max_delay)


def with_rate_limit_retry(limiter: InstagramRateLimiter):
    """
    Decorador para retry automático con backoff en rate limits.

    Uso:
        limiter = InstagramRateLimiter()

        @with_rate_limit_retry(limiter)
        async def fetch_messages(conv_id: str):
            response = await client.get(url)
            return response.json()
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(limiter.config.max_retries):
                try:
                    # Aplicar throttling antes de la llamada
                    await limiter.throttle()
                    return await func(*args, **kwargs)

                except InstagramRateLimitError as e:
                    last_error = e

                    if attempt == limiter.config.max_retries - 1:
                        logger.error(f"[RateLimiter] Max retries reached: {e.message}")
                        raise

                    delay = limiter.calculate_backoff(attempt, e.retry_after)
                    logger.warning(
                        f"[RateLimiter] Rate limit hit, attempt {attempt + 1}/{limiter.config.max_retries}, "
                        f"waiting {delay:.0f}s"
                    )
                    await asyncio.sleep(delay)

            raise last_error

        return wrapper
    return decorator


async def process_in_batches(
    items: list,
    processor: Callable,
    limiter: InstagramRateLimiter,
    on_progress: Optional[Callable[[int, int], None]] = None
) -> Dict[str, Any]:
    """
    Procesar items en batches con rate limiting.

    Args:
        items: Lista de items a procesar
        processor: Función async que procesa cada item
        limiter: Instancia del rate limiter
        on_progress: Callback opcional (processed, total)

    Returns:
        Dict con resultados y errores
    """
    results = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "errors": [],
        "data": []
    }

    total = len(items)
    batch_size = limiter.config.batch_size

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = items[batch_start:batch_end]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        logger.info(f"[RateLimiter] Processing batch {batch_num}/{total_batches}")

        for item in batch:
            try:
                await limiter.throttle()
                result = await processor(item)
                results["data"].append(result)
                results["success"] += 1
            except InstagramRateLimitError as e:
                # En rate limit, esperar y reintentar este item
                delay = limiter.calculate_backoff(0, e.retry_after)
                logger.warning(f"[RateLimiter] Rate limit in batch, waiting {delay:.0f}s")
                await asyncio.sleep(delay)

                try:
                    result = await processor(item)
                    results["data"].append(result)
                    results["success"] += 1
                except Exception as retry_error:
                    results["failed"] += 1
                    results["errors"].append(str(retry_error))
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(str(e))

            results["processed"] += 1

            if on_progress:
                on_progress(results["processed"], total)

        # Pausa entre batches (excepto el último)
        if batch_end < total:
            logger.info(f"[RateLimiter] Batch complete, waiting {limiter.config.batch_delay}s before next")
            await asyncio.sleep(limiter.config.batch_delay)

    return results
