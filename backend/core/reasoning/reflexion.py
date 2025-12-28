from typing import Protocol, Dict, Any, List, Optional
import logging

logger = logging.getLogger("clonnect.reasoning.reflexion")

class LLMClient(Protocol):
    async def generate(self, prompt: str, temperature: float = 0.7) -> str: ...

class Reflexion:
    def __init__(self, llm_client: LLMClient, max_iterations: int = 3, default_temperature: float = 0.7):
        self.llm = llm_client
        self.max_iterations = max_iterations
        self.default_temperature = default_temperature

    async def generate_answer(self, query: str, context: str = "", temperature: Optional[float] = None) -> str:
        temp = temperature if temperature is not None else self.default_temperature
        user_prompt = query
        if context:
            user_prompt = f"Contexto:\n{context}\n\nPregunta: {query}"
        try:
            return await self.llm.generate(user_prompt, temperature=temp)
        except Exception as e:
            return f"Error: {str(e)}"

    async def critique_answer(self, query: str, answer: str) -> str:
        critique_prompt = f"Pregunta original: {query}\n\nRespuesta a evaluar: {answer}\n\nCritica esta respuesta. Identifica errores, debilidades y areas de mejora."
        try:
            return await self.llm.generate(critique_prompt, temperature=0.3)
        except Exception as e:
            return f"Error criticando: {str(e)}"

    async def refine_answer(self, query: str, answer: str, critique: str) -> str:
        refine_prompt = f"Pregunta original: {query}\n\nRespuesta anterior: {answer}\n\nCritica recibida: {critique}\n\nProporciona una respuesta mejorada:"
        try:
            return await self.llm.generate(refine_prompt, temperature=self.default_temperature)
        except Exception as e:
            return answer

    async def solve(self, query: str, context: str = "", min_iterations: int = 1) -> Dict[str, Any]:
        iterations = []
        answer = await self.generate_answer(query, context)
        for i in range(self.max_iterations):
            critique = await self.critique_answer(query, answer)
            iterations.append({"iteration": i + 1, "answer": answer, "critique": critique})
            if i + 1 >= min_iterations:
                if "no hay errores" in critique.lower() or "esta bien" in critique.lower():
                    break
            refined = await self.refine_answer(query, answer, critique)
            if refined.strip() == answer.strip():
                break
            answer = refined
        return {"final_answer": answer, "iterations": iterations, "num_iterations": len(iterations)}

    async def improve_response(self, response: str, target_quality: str = "persuasivo y empatico") -> Dict[str, Any]:
        query = f"Mejora esta respuesta para que sea mas {target_quality}:\n\n{response}"
        return await self.solve(query, min_iterations=2)
