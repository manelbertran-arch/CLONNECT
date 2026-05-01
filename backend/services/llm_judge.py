"""
LLM Judge — Reusable LLM-as-judge component for quality evaluation.

Uses Qwen3-30B-A3B via DeepInfra as judge model (avoids self-bias,
different provider from DM generation; 2x cheaper than GPT-4o-mini).

Features:
  - JSON-structured rubric evaluation
  - Anti-bias instructions (no verbosity bias, no positivity bias)
  - Graceful fallback on parse errors
  - Timeout handling (15s per judge call)

Entry point: LLMJudge.judge() — async, returns JudgementResult dict.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

JUDGE_MODEL = os.getenv("CLONE_SCORE_JUDGE_MODEL", "Qwen/Qwen3-30B-A3B")
JUDGE_TIMEOUT = float(os.getenv("CLONE_SCORE_JUDGE_TIMEOUT", "15"))
_DEEPINFRA_URL = "https://api.deepinfra.com/v1/openai/chat/completions"

_ANTI_BIAS_INSTRUCTIONS = """INSTRUCCIONES IMPORTANTES PARA EL EVALUADOR:
- NO tengas sesgo hacia respuestas mas largas. Una respuesta corta puede ser perfecta.
- NO tengas sesgo positivo. Se critico y honesto.
- NO penalices por informalidad si el contexto lo amerita (DMs son informales).
- Evalua SOLO lo que se te pide en cada dimension.
- El score debe reflejar la REALIDAD, no lo que "suena bien".
- Un 50 es NEUTRO (ni bueno ni malo). Usa el rango completo 0-100.
"""


class LLMJudge:
    """Reusable LLM-as-judge for CloneScore dimensions."""

    # Cap judge prompts to ~2000 tokens (8000 chars) to control cost
    MAX_JUDGE_PROMPT_CHARS = 8000

    async def judge(
        self,
        prompt: str,
        dimension: str,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """Execute LLM judge evaluation.

        Args:
            prompt: Full evaluation prompt with context and rubric
            dimension: Dimension name (for logging)
            max_retries: Number of retries on failure

        Returns:
            Dict with at least {"score": float, "reasoning": str}
            Returns {"score": 50.0} on failure (neutral fallback)
        """
        # Truncate long prompts to cap cost
        original_len = len(prompt)
        if original_len > self.MAX_JUDGE_PROMPT_CHARS:
            prompt = prompt[:self.MAX_JUDGE_PROMPT_CHARS]
            logger.info(
                f"[LLM_JUDGE] {dimension}: truncated prompt {original_len} -> {self.MAX_JUDGE_PROMPT_CHARS} chars"
            )

        est_tokens = len(prompt) // 4
        logger.info(f"[LLM_JUDGE] {dimension}: prompt ~{est_tokens} tokens")

        system_prompt = (
            "Eres un evaluador experto de calidad para clones de IA. "
            "Evaluas respuestas de bots de DMs comparandolas con el estilo "
            "y conocimiento del creador original.\n\n"
            f"{_ANTI_BIAS_INSTRUCTIONS}\n"
            "Responde SIEMPRE en JSON valido, sin markdown ni explicaciones fuera del JSON."
        )

        for attempt in range(max_retries + 1):
            try:
                result = await self._call_judge(
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                )

                if result is None:
                    if attempt < max_retries:
                        await asyncio.sleep(1)
                        continue
                    logger.warning(
                        f"[LLM_JUDGE] {dimension}: all {max_retries + 1} attempts returned None"
                    )
                    return {"score": 50.0, "reasoning": "judge_unavailable"}

                parsed = self._parse_judge_response(result)
                if parsed and "score" in parsed:
                    # Clamp score to 0-100
                    parsed["score"] = max(0.0, min(100.0, float(parsed["score"])))
                    logger.debug(
                        f"[LLM_JUDGE] {dimension}: score={parsed['score']:.1f}"
                    )
                    return parsed

                if attempt < max_retries:
                    logger.debug(
                        f"[LLM_JUDGE] {dimension}: parse failed, retrying "
                        f"({attempt + 1}/{max_retries + 1})"
                    )
                    await asyncio.sleep(0.5)
                    continue

            except asyncio.TimeoutError:
                logger.warning(
                    f"[LLM_JUDGE] {dimension}: timeout ({JUDGE_TIMEOUT}s) "
                    f"on attempt {attempt + 1}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue

            except Exception as e:
                logger.error(f"[LLM_JUDGE] {dimension}: error: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue

        return {"score": 50.0, "reasoning": "judge_failed_all_retries"}

    async def _call_judge(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Optional[str]:
        """Call the judge LLM (Qwen3-30B-A3B via DeepInfra OpenAI-compatible API)."""
        import httpx

        api_key = os.getenv("DEEPINFRA_API_KEY")
        if not api_key:
            logger.warning("[LLM_JUDGE] DEEPINFRA_API_KEY missing, skip judge")
            return None

        payload = {
            "model": JUDGE_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 512,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=JUDGE_TIMEOUT) as client:
                resp = await client.post(
                    _DEEPINFRA_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                return content

        except httpx.TimeoutException:
            raise asyncio.TimeoutError("DeepInfra judge timeout")
        except httpx.HTTPStatusError as e:
            logger.error(f"[LLM_JUDGE] HTTP error: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"[LLM_JUDGE] Call error: {e}")
            return None

    def _parse_judge_response(self, raw: str) -> Optional[Dict]:
        """Parse JSON response from the judge LLM."""
        if not raw:
            return None

        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and "score" in data:
                return data
            logger.warning(f"[LLM_JUDGE] JSON parsed but no 'score' key: {list(data.keys())}")
            return None
        except json.JSONDecodeError:
            # Try to extract score with regex as fallback
            score_match = re.search(r'"score"\s*:\s*(\d+(?:\.\d+)?)', raw)
            if score_match:
                return {
                    "score": float(score_match.group(1)),
                    "reasoning": "parsed_from_malformed_json",
                }
            logger.warning(f"[LLM_JUDGE] Failed to parse: {raw[:200]}")
            return None
