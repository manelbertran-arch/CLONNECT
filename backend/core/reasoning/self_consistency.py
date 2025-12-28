from typing import Protocol, Dict, Any, List, Optional
from collections import Counter
import logging

logger = logging.getLogger("clonnect.reasoning.self_consistency")

class LLMClient(Protocol):
    async def generate(self, prompt: str, temperature: float = 0.7) -> str: ...

class SelfConsistency:
    def __init__(self, llm_client: LLMClient, default_temperature: float = 0.7):
        self.llm = llm_client
        self.default_temperature = default_temperature

    async def generate_multiple(self, query: str, n: int = 5, context: str = "", temperature: Optional[float] = None) -> List[str]:
        temp = temperature if temperature is not None else self.default_temperature
        user_prompt = query
        if context:
            user_prompt = f"Contexto:\n{context}\n\nPregunta: {query}"
        answers = []
        for i in range(n):
            try:
                response = await self.llm.generate(user_prompt, temperature=temp)
                answers.append(response.strip())
            except Exception as e:
                logger.warning(f"Generacion {i+1}/{n} fallo: {e}")
        return answers

    def find_consensus(self, answers: List[str]) -> Dict[str, Any]:
        if not answers:
            return {"consensus": "", "confidence": 0.0, "all_answers": []}
        answer_counts = Counter(answers)
        most_common = answer_counts.most_common()
        consensus = most_common[0][0]
        confidence = most_common[0][1] / len(answers)
        return {"consensus": consensus, "confidence": confidence, "all_answers": [{"answer": ans, "count": count} for ans, count in most_common]}

    async def solve(self, query: str, n: int = 5, context: str = "", temperature: Optional[float] = None) -> Dict[str, Any]:
        answers = await self.generate_multiple(query, n=n, context=context, temperature=temperature)
        result = self.find_consensus(answers)
        logger.info(f"SelfConsistency: {n} respuestas, confidence={result['confidence']:.2f}")
        return result

    async def verify_response(self, proposed_response: str, query: str, context: str = "", threshold: float = 0.6) -> Dict[str, Any]:
        result = await self.solve(query, n=5, context=context)
        proposed_lower = proposed_response.lower().strip()
        consensus_lower = result["consensus"].lower().strip()
        is_similar = proposed_lower in consensus_lower or consensus_lower in proposed_lower or proposed_lower == consensus_lower
        is_valid = is_similar and result["confidence"] >= threshold
        return {"is_valid": is_valid, "confidence": result["confidence"], "suggested_response": result["consensus"] if not is_valid else proposed_response, "all_answers": result["all_answers"]}
