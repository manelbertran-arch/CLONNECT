"""
ECHO Engine Stress Test.

Simulates concurrent DM load to measure latency, error rate, and resource usage.

Usage:
    python -m tests.echo.stress_test --creator stefano --concurrent 10
    python -m tests.echo.stress_test --creator stefano --concurrent 20 --duration 60

Targets:
    - p95 latency < 3 seconds
    - Error rate < 1%
    - No memory leaks over duration
"""
import os
import json
import time
import asyncio
import logging
import resource
import statistics
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONCURRENT = 10
DEFAULT_DURATION_SECS = 30
LATENCY_P95_TARGET_MS = 3000
ERROR_RATE_TARGET = 0.01  # 1%
MEMORY_GROWTH_LIMIT_MB = 50


# ---------------------------------------------------------------------------
# Stress test messages (diverse realistic DM patterns)
# ---------------------------------------------------------------------------

STRESS_MESSAGES = [
    # Short greetings
    {"message": "Hola!", "lead_category": "nuevo", "topic": "casual"},
    {"message": "Buenas Stefano", "lead_category": "nuevo", "topic": "casual"},
    {"message": "Ey que tal", "lead_category": "interesado", "topic": "casual"},
    # Price inquiries
    {"message": "Cuanto cuesta el curso de nutricion?", "lead_category": "interesado", "topic": "ventas"},
    {"message": "Hay descuento?", "lead_category": "interesado", "topic": "ventas"},
    {"message": "Se puede pagar a plazos?", "lead_category": "caliente", "topic": "ventas"},
    # Purchase intent
    {"message": "Quiero comprar el curso", "lead_category": "caliente", "topic": "ventas"},
    {"message": "Dame el link de pago", "lead_category": "caliente", "topic": "ventas"},
    # Support
    {"message": "No puedo acceder al modulo 3", "lead_category": "cliente", "topic": "soporte"},
    {"message": "El video no carga", "lead_category": "cliente", "topic": "soporte"},
    # Long messages (audio transcripts)
    {
        "message": (
            "[Audio transcrito] Hola Stefano mira te cuento que llevo un tiempo "
            "pensando en cambiar mi alimentacion porque la verdad no me siento bien "
            "con lo que como y creo que necesito ayuda profesional"
        ),
        "lead_category": "nuevo",
        "topic": "ventas",
    },
    # Ghost reactivation
    {"message": "Ey sigo aqui jaja, perdon por desaparecer", "lead_category": "fantasma", "topic": "casual"},
    # Content
    {"message": "Vi tu ultimo reel, muy bueno!", "lead_category": "interesado", "topic": "contenido"},
    # Objections
    {"message": "Es muy caro para mi", "lead_category": "caliente", "topic": "ventas"},
    {"message": "He visto otros cursos mas baratos", "lead_category": "interesado", "topic": "ventas"},
]


# ---------------------------------------------------------------------------
# Stress test runner
# ---------------------------------------------------------------------------

class StressTestRunner:
    """Runs concurrent stress tests against the DM pipeline."""

    def __init__(
        self,
        pipeline=None,
        concurrent: int = DEFAULT_CONCURRENT,
        duration_secs: int = DEFAULT_DURATION_SECS,
    ):
        self.pipeline = pipeline
        self.concurrent = concurrent
        self.duration_secs = duration_secs

    async def run(self) -> dict:
        """
        Run stress test with concurrent conversations.

        Returns latency percentiles, error rates, and resource usage.
        """
        results: list[dict] = []
        errors: list[dict] = []
        start_time = time.perf_counter()
        memory_samples = []

        # Track initial memory
        initial_memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
        memory_samples.append({"time_s": 0, "memory_mb": initial_memory_mb})

        semaphore = asyncio.Semaphore(self.concurrent)
        request_id = 0
        stop_event = asyncio.Event()

        async def send_message(msg_template: dict, req_id: int) -> dict | None:
            async with semaphore:
                if stop_event.is_set():
                    return None

                msg_start = time.perf_counter()
                try:
                    if self.pipeline:
                        response = await asyncio.wait_for(
                            self.pipeline.process_dm(
                                message=msg_template["message"],
                                sender_id=f"stress-lead-{req_id % 100:04d}",
                                metadata={
                                    "lead_stage": msg_template.get("lead_category", "nuevo"),
                                },
                            ),
                            timeout=10.0,
                        )
                        content = response.content
                        tokens = response.tokens_used
                    else:
                        # Simulate pipeline latency for testing the framework itself
                        await asyncio.sleep(0.05 + (req_id % 10) * 0.01)
                        content = f"Mock response #{req_id}"
                        tokens = 100

                    elapsed_ms = (time.perf_counter() - msg_start) * 1000

                    return {
                        "request_id": req_id,
                        "latency_ms": elapsed_ms,
                        "tokens": tokens,
                        "success": True,
                        "lead_category": msg_template.get("lead_category"),
                        "topic": msg_template.get("topic"),
                        "response_length": len(content),
                    }

                except asyncio.TimeoutError:
                    elapsed_ms = (time.perf_counter() - msg_start) * 1000
                    return {
                        "request_id": req_id,
                        "latency_ms": elapsed_ms,
                        "success": False,
                        "error": "timeout",
                    }
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - msg_start) * 1000
                    return {
                        "request_id": req_id,
                        "latency_ms": elapsed_ms,
                        "success": False,
                        "error": str(e),
                    }

        # Fire requests for the duration — use create_task to start immediately
        tasks: list[asyncio.Task] = []
        msg_index = 0

        while (time.perf_counter() - start_time) < self.duration_secs:
            msg_template = STRESS_MESSAGES[msg_index % len(STRESS_MESSAGES)]
            request_id += 1
            task = asyncio.create_task(send_message(msg_template, request_id))
            tasks.append(task)
            msg_index += 1

            # Small delay to stagger requests naturally
            await asyncio.sleep(0.05)

            # Memory sample every second
            elapsed = time.perf_counter() - start_time
            if len(memory_samples) < int(elapsed) + 1:
                current_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
                memory_samples.append({"time_s": round(elapsed, 1), "memory_mb": current_mem})

        stop_event.set()

        # Wait for all in-flight tasks to complete
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        total_time = time.perf_counter() - start_time

        # Process results
        for r in raw_results:
            if isinstance(r, Exception):
                errors.append({"error": str(r)})
            elif r is not None:
                if r.get("success"):
                    results.append(r)
                else:
                    errors.append(r)

        # Final memory
        final_memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
        memory_growth_mb = final_memory_mb - initial_memory_mb

        return self._compute_report(
            results, errors, total_time, memory_samples, memory_growth_mb
        )

    def _compute_report(
        self,
        results: list[dict],
        errors: list[dict],
        total_time: float,
        memory_samples: list[dict],
        memory_growth_mb: float,
    ) -> dict:
        """Compute stress test report from raw results."""
        total_requests = len(results) + len(errors)

        if not results:
            return {
                "status": "FAIL",
                "message": f"All {total_requests} requests failed",
                "total_requests": total_requests,
                "successful": 0,
                "errors": len(errors),
                "error_rate": 1.0,
                "pass": False,
            }

        # Latency percentiles
        latencies = sorted(r["latency_ms"] for r in results)
        n = len(latencies)

        latency_stats = {
            "avg_ms": round(statistics.mean(latencies), 1),
            "p50_ms": round(latencies[n // 2], 1),
            "p90_ms": round(latencies[int(n * 0.9)], 1),
            "p95_ms": round(latencies[int(n * 0.95)], 1),
            "p99_ms": round(latencies[int(n * 0.99)], 1),
            "min_ms": round(min(latencies), 1),
            "max_ms": round(max(latencies), 1),
        }

        error_rate = len(errors) / max(total_requests, 1)

        # Throughput
        throughput_rps = total_requests / max(total_time, 0.001)

        # Token stats
        total_tokens = sum(r.get("tokens", 0) for r in results)

        # Per-category latencies
        from collections import defaultdict
        cat_latencies: dict[str, list[float]] = defaultdict(list)
        for r in results:
            cat = r.get("lead_category", "unknown")
            cat_latencies[cat].append(r["latency_ms"])

        by_category = {
            cat: {
                "count": len(lats),
                "avg_ms": round(statistics.mean(lats), 1),
                "p95_ms": round(sorted(lats)[int(len(lats) * 0.95)], 1) if len(lats) > 1 else round(lats[0], 1),
            }
            for cat, lats in cat_latencies.items()
        }

        # Determine pass/fail
        p95_pass = latency_stats["p95_ms"] < LATENCY_P95_TARGET_MS
        error_pass = error_rate < ERROR_RATE_TARGET
        memory_pass = memory_growth_mb < MEMORY_GROWTH_LIMIT_MB

        all_pass = p95_pass and error_pass and memory_pass
        status = "PASS" if all_pass else "FAIL"

        issues = []
        if not p95_pass:
            issues.append(f"p95 latency {latency_stats['p95_ms']}ms > {LATENCY_P95_TARGET_MS}ms target")
        if not error_pass:
            issues.append(f"Error rate {error_rate*100:.1f}% > {ERROR_RATE_TARGET*100:.0f}% target")
        if not memory_pass:
            issues.append(f"Memory growth {memory_growth_mb:.1f}MB > {MEMORY_GROWTH_LIMIT_MB}MB limit")

        return {
            "status": status,
            "pass": all_pass,
            "total_requests": total_requests,
            "successful": len(results),
            "errors": len(errors),
            "error_rate": round(error_rate, 4),
            "duration_secs": round(total_time, 1),
            "concurrent": self.concurrent,
            "throughput_rps": round(throughput_rps, 2),
            "latency": latency_stats,
            "by_category": by_category,
            "total_tokens": total_tokens,
            "memory": {
                "growth_mb": round(memory_growth_mb, 2),
                "samples": memory_samples[:10],  # First 10 samples
                "limit_mb": MEMORY_GROWTH_LIMIT_MB,
            },
            "targets": {
                "p95_pass": p95_pass,
                "error_pass": error_pass,
                "memory_pass": memory_pass,
            },
            "issues": issues,
        }


def print_stress_report(result: dict) -> None:
    """Print stress test report."""
    status_icon = "✓" if result["pass"] else "✗"

    print(f"\n{'='*60}")
    print(f"  Stress Test: {result['status']} {status_icon}")
    print(f"{'='*60}")
    print(f"  Concurrent workers: {result.get('concurrent', '?')}")
    print(f"  Duration: {result.get('duration_secs', 0):.1f}s")
    print(f"  Total requests: {result['total_requests']}")
    print(f"  Successful: {result['successful']}")
    print(f"  Errors: {result['errors']} ({result['error_rate']*100:.1f}%)")
    print(f"  Throughput: {result.get('throughput_rps', 0):.1f} req/s")

    lat = result.get("latency", {})
    print(f"\n  Latency:")
    print(f"    avg:  {lat.get('avg_ms', 0):>8.1f} ms")
    print(f"    p50:  {lat.get('p50_ms', 0):>8.1f} ms")
    print(f"    p90:  {lat.get('p90_ms', 0):>8.1f} ms")
    print(f"    p95:  {lat.get('p95_ms', 0):>8.1f} ms  (target: <{LATENCY_P95_TARGET_MS}ms)")
    print(f"    p99:  {lat.get('p99_ms', 0):>8.1f} ms")
    print(f"    max:  {lat.get('max_ms', 0):>8.1f} ms")

    if result.get("by_category"):
        print(f"\n  By Lead Category:")
        for cat, data in sorted(result["by_category"].items()):
            print(f"    {cat:15s}: n={data['count']:3d}, avg={data['avg_ms']:.0f}ms, p95={data['p95_ms']:.0f}ms")

    mem = result.get("memory", {})
    print(f"\n  Memory:")
    print(f"    Growth: {mem.get('growth_mb', 0):.1f} MB (limit: {mem.get('limit_mb', MEMORY_GROWTH_LIMIT_MB)} MB)")

    if result.get("issues"):
        print(f"\n  Issues:")
        for issue in result["issues"]:
            print(f"    ✗ {issue}")

    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ECHO Engine stress test")
    parser.add_argument("--concurrent", type=int, default=DEFAULT_CONCURRENT, help="Concurrent workers")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION_SECS, help="Test duration in seconds")
    parser.add_argument("--no-pipeline", action="store_true", help="Run with mock pipeline")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    pipeline = None
    if not args.no_pipeline:
        try:
            # Try to import real pipeline
            from core.dm_agent_v2 import DMResponderAgentV2
            pipeline = DMResponderAgentV2()
            logger.info("Using real DM pipeline")
        except ImportError:
            logger.info("Real pipeline not available, using mock")

    runner = StressTestRunner(
        pipeline=pipeline,
        concurrent=args.concurrent,
        duration_secs=args.duration,
    )

    result = asyncio.run(runner.run())
    print_stress_report(result)

    exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
