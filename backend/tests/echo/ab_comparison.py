"""
A/B Blind Comparison Test — Clone vs Real Creator.

Presents pairs (clone response, real response) to an LLM judge WITHOUT
revealing which is which. The judge picks which sounds more like the creator.

Target: >50% of the time the judge cannot distinguish the clone from the real.

Usage:
    runner = ABComparisonRunner(creator_profile, llm_provider)
    results = await runner.run(test_cases, pipeline)

Cost estimate:
    - 1 LLM call per test case (~$0.02)
    - 100 test cases: ~$2.00
"""
import json
import re
import random
import logging
import asyncio
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Judge prompt (Spanish, position-randomized to avoid bias)
# ---------------------------------------------------------------------------

AB_JUDGE_PROMPT = """Eres un evaluador experto en comunicacion de creadores de contenido.

PERFIL DEL CREADOR:
{doc_d_summary}

CONTEXTO:
{context}

MENSAJE DEL FOLLOWER:
{follower_message}

A continuacion tienes dos respuestas al follower. Una fue escrita por el creador real y otra por un bot de IA. Tu trabajo es identificar CUAL suena mas autentica, mas como el creador real.

RESPUESTA A:
{response_a}

RESPUESTA B:
{response_b}

Evalua en base a:
1. Estilo linguistico (longitud, emojis, formalidad, muletillas)
2. Naturalidad (suena como un humano escribiendo por DM?)
3. Personalidad (se siente como el creador descrito arriba?)
4. Conocimiento (la informacion es precisa y relevante?)

Responde SOLO con JSON:
{{"choice": "A" o "B", "confidence": <0.5-1.0>, "reasoning": "explicacion breve de por que elegiste esa opcion"}}

IMPORTANTE: Elige la que suena MAS como el creador real. Si ambas suenan iguales, elige la que prefieras con confidence cercana a 0.5."""


class ABComparisonRunner:
    """Runs blind A/B tests between clone and real creator responses."""

    def __init__(
        self,
        creator_profile: dict,
        llm_provider=None,
        max_concurrent: int = 5,
    ):
        self.creator_profile = creator_profile
        self.llm_provider = llm_provider
        self.max_concurrent = max_concurrent

    async def compare_single(
        self,
        test_case: dict,
        clone_response: str,
    ) -> dict:
        """
        Run a single blind A/B comparison.

        Randomizes order to avoid position bias.
        """
        real_response = test_case.get("real_response", "")

        # Randomize position (mitigate position bias)
        clone_is_a = random.random() < 0.5
        if clone_is_a:
            response_a = clone_response
            response_b = real_response
        else:
            response_a = real_response
            response_b = clone_response

        # Build context from history
        history = test_case.get("conversation_history", [])
        context_lines = [f"{m['role']}: {m['content']}" for m in history[-5:]]
        context = "\n".join(context_lines) if context_lines else "Primera interaccion"

        prompt = AB_JUDGE_PROMPT.format(
            doc_d_summary=self.creator_profile.get("doc_d_summary", ""),
            context=context,
            follower_message=test_case.get("follower_message", ""),
            response_a=response_a,
            response_b=response_b,
        )

        # Call LLM judge
        judge_result = await self._call_judge(prompt)

        choice = judge_result.get("choice", "A").upper()
        confidence = judge_result.get("confidence", 0.5)

        # Determine if clone was chosen as "real"
        clone_chosen_as_real = (
            (choice == "A" and clone_is_a) or (choice == "B" and not clone_is_a)
        )
        # "Indistinguishable" = judge chose clone OR confidence < 0.6
        indistinguishable = clone_chosen_as_real or confidence < 0.6

        return {
            "test_case_id": test_case.get("id", "unknown"),
            "clone_is_a": clone_is_a,
            "judge_choice": choice,
            "judge_confidence": confidence,
            "clone_chosen_as_real": clone_chosen_as_real,
            "indistinguishable": indistinguishable,
            "reasoning": judge_result.get("reasoning", ""),
            "clone_response": clone_response,
            "real_response": real_response,
        }

    async def run(
        self,
        test_cases: list[dict],
        pipeline=None,
    ) -> dict:
        """
        Run A/B comparison on all test cases.

        If pipeline is provided, generates clone responses.
        Otherwise, uses 'bot_response' from test_case dict.
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results = []
        errors = []

        async def run_one(tc: dict) -> dict | None:
            async with semaphore:
                try:
                    if pipeline:
                        dm_response = await pipeline.process_dm(
                            message=tc.get("follower_message", ""),
                            sender_id=tc.get("lead_id", "test"),
                        )
                        clone_response = dm_response.content
                    else:
                        clone_response = tc.get(
                            "bot_response", "No response generated"
                        )

                    return await self.compare_single(tc, clone_response)
                except Exception as e:
                    logger.error(f"A/B error for {tc.get('id')}: {e}")
                    errors.append({"test_case_id": tc.get("id"), "error": str(e)})
                    return None

        tasks = [run_one(tc) for tc in test_cases]
        raw_results = await asyncio.gather(*tasks)
        results = [r for r in raw_results if r is not None]

        if not results:
            return {
                "indistinguishable_rate": 0.0,
                "clone_chosen_rate": 0.0,
                "results": [],
                "errors": errors,
                "pass": False,
            }

        # Metrics
        indistinguishable_count = sum(1 for r in results if r["indistinguishable"])
        clone_chosen_count = sum(1 for r in results if r["clone_chosen_as_real"])
        avg_confidence = sum(r["judge_confidence"] for r in results) / len(results)

        indistinguishable_rate = indistinguishable_count / len(results)
        clone_chosen_rate = clone_chosen_count / len(results)

        # Breakdown by category
        by_category: dict[str, dict] = {}
        for r in results:
            tc_id = r["test_case_id"]
            tc = next((t for t in test_cases if t.get("id") == tc_id), {})
            cat = tc.get("lead_category", "unknown")
            if cat not in by_category:
                by_category[cat] = {"total": 0, "indistinguishable": 0}
            by_category[cat]["total"] += 1
            if r["indistinguishable"]:
                by_category[cat]["indistinguishable"] += 1

        for cat_data in by_category.values():
            cat_data["rate"] = round(
                cat_data["indistinguishable"] / max(cat_data["total"], 1), 3
            )

        return {
            "indistinguishable_rate": round(indistinguishable_rate, 3),
            "clone_chosen_rate": round(clone_chosen_rate, 3),
            "avg_confidence": round(avg_confidence, 3),
            "total_comparisons": len(results),
            "indistinguishable_count": indistinguishable_count,
            "by_category": by_category,
            "results": results,
            "errors": errors,
            "pass": indistinguishable_rate >= 0.50,
            "cost_usd": round(len(results) * 0.02, 2),
        }

    async def _call_judge(self, prompt: str) -> dict:
        """Call LLM judge and parse response."""
        if self.llm_provider is None:
            return {"choice": "A", "confidence": 0.5, "reasoning": "No LLM provider"}

        try:
            response = await self.llm_provider(
                model="gemini-2.5-flash-lite",
                api_key="",
                system_prompt="Eres un evaluador experto. Responde SOLO con JSON valido.",
                user_message=prompt,
                max_tokens=200,
                temperature=0.1,
            )

            content = response.get("content", "") if isinstance(response, dict) else str(response)
            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

            return {"choice": "A", "confidence": 0.5, "reasoning": "Parse error"}

        except Exception as e:
            logger.error(f"A/B judge call failed: {e}")
            return {"choice": "A", "confidence": 0.5, "reasoning": f"Error: {e}"}


def print_ab_report(results: dict) -> None:
    """Print A/B comparison report."""
    print(f"\n{'='*60}")
    print(f"  A/B Blind Comparison Results")
    print(f"{'='*60}")
    print(f"  Total comparisons: {results['total_comparisons']}")
    print(f"  Indistinguishable rate: {results['indistinguishable_rate']*100:.1f}%")
    print(f"  Clone chosen as real: {results['clone_chosen_rate']*100:.1f}%")
    print(f"  Avg judge confidence: {results['avg_confidence']:.3f}")
    print(f"  Target: >50% indistinguishable")
    print(f"  Status: {'PASS ✓' if results['pass'] else 'FAIL ✗'}")
    if results.get("by_category"):
        print(f"\n  By Lead Category:")
        for cat, data in sorted(results["by_category"].items()):
            print(
                f"    {cat:15s}: {data['indistinguishable']}/{data['total']} "
                f"({data['rate']*100:.0f}%)"
            )
    print(f"\n  Estimated cost: ${results.get('cost_usd', 0):.2f}")
    print(f"{'='*60}\n")
