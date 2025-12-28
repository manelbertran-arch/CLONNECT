from typing import Protocol, Dict, Any, Optional
import logging

logger = logging.getLogger("clonnect.reasoning.chain_of_thought")

class LLMClient(Protocol):
    async def generate(self, prompt: str, temperature: float = 0.7) -> str: ...

class ChainOfThought:
    def __init__(self, llm_client: LLMClient, default_temperature: float = 0.7):
        self.llm = llm_client
        self.default_temperature = default_temperature

    async def generate(self, query: str, context: str = "", temperature: Optional[float] = None) -> Dict[str, Any]:
        temp = temperature if temperature is not None else self.default_temperature
        system_prompt = "Eres un asistente que piensa paso a paso. Para cada pregunta debes: 1. Descomponer el problema en pasos 2. Razonar explicitamente cada paso 3. Llegar a una respuesta final. Formato: RAZONAMIENTO: Paso 1: ... RESPUESTA: [respuesta final]"
        user_prompt = query
        if context:
            user_prompt = f"Contexto:\n{context}\n\nPregunta: {query}"
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        try:
            content = await self.llm.generate(full_prompt, temperature=temp)
            parts = content.split("RESPUESTA:")
            reasoning = parts[0].replace("RAZONAMIENTO:", "").strip()
            answer = parts[1].strip() if len(parts) > 1 else content
            return {"reasoning": reasoning, "answer": answer, "full_response": content}
        except Exception as e:
            logger.error(f"CoT fallo: {e}")
            return {"reasoning": "", "answer": f"Error: {str(e)}", "full_response": ""}

    async def solve_complex(self, query: str, context: str = "", require_steps: int = 3) -> Dict[str, Any]:
        result = await self.generate(query, context)
        step_count = result["reasoning"].count("Paso") + result["reasoning"].count("Step")
        if step_count < require_steps:
            retry_prompt = f"Analiza en al menos {require_steps} pasos: {query}"
            result = await self.generate(retry_prompt, context)
        return result
