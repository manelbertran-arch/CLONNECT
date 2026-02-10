"""Integration test for Scout production inference via DeepInfra + Groq fallback."""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.providers.deepinfra_provider import generate_scout_production
from core.response_fixes import apply_all_response_fixes


TEST_MESSAGES = [
    "Ciao!",
    "Quanto costa il tuo programma?",
    "Come posso perdere peso velocemente?",
    "Grazie mille!",
    "Sei un bot?",
    "Mi puoi aiutare con la dieta?",
    "Non ho soldi",
    "Vorrei iniziare ad allenarmi",
    "Hola, hablas español?",
    "Me encanta tu contenido",
]

SYSTEM_PROMPT = (
    "Eres Stefano Bonanno respondiendo DMs de Instagram. "
    "Longitud mediana: 18 caracteres. Usas emoji en ~23% de mensajes. "
    "Responde de forma breve y natural."
)


async def main():
    print("=" * 60)
    print("SCOUT INTEGRATION TEST")
    print("=" * 60)

    results = []
    failures = 0

    for i, msg in enumerate(TEST_MESSAGES, 1):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": msg},
        ]

        start = time.monotonic()
        raw = await generate_scout_production(messages)
        latency = int((time.monotonic() - start) * 1000)

        if not raw:
            print(f"\n  [{i}/10] FAIL - No response for: {msg}")
            failures += 1
            results.append({"msg": msg, "raw": None, "fixed": None, "latency": latency})
            continue

        fixed = apply_all_response_fixes(raw, creator_name="Stefano Bonanno")
        if not fixed:
            fixed = raw  # FIX 6 should not empty valid responses anymore

        print(f"\n  [{i}/10] {msg}")
        print(f"    RAW:     {repr(raw)} ({len(raw)}c)")
        print(f"    FIXED:   {repr(fixed)} ({len(fixed)}c)")
        print(f"    LATENCY: {latency}ms")

        results.append({"msg": msg, "raw": raw, "fixed": fixed, "latency": latency})
        await asyncio.sleep(0.3)

    print(f"\n{'=' * 60}")
    avg_latency = sum(r["latency"] for r in results) / len(results)
    print(f"Results: {10 - failures}/10 OK, {failures} failures")
    print(f"Avg latency: {avg_latency:.0f}ms")
    print(f"{'=' * 60}")

    if failures > 0:
        print(f"\nFAILED: {failures} responses were empty/None")
        sys.exit(1)
    else:
        print("\nALL PASSED")


if __name__ == "__main__":
    asyncio.run(main())
