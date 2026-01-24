"""
Personalized Ranking - Re-ranking de resultados según perfil del lead.

Adapta los resultados de búsqueda según:
- Intereses del lead
- Contenido que ha preferido antes
- Productos de interés
"""
import math
import logging
from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .user_profiles import UserProfile

logger = logging.getLogger("clonnect.personalized_ranking")


def personalize_results(
    results: List[Dict[str, Any]],
    user_profile: 'UserProfile',
    alpha: float = 0.3,
    score_key: str = "score",
    content_key: str = "content"
) -> List[Dict[str, Any]]:
    """
    Re-rankea resultados según perfil del usuario.

    Args:
        results: Resultados de búsqueda con scores
        user_profile: Perfil del usuario
        alpha: Peso de personalización (0=sin personalización, 1=solo personalización)
        score_key: Key del score base en cada resultado
        content_key: Key del contenido en cada resultado

    Returns:
        Resultados re-ordenados con scores personalizados
    """
    if not results or not user_profile:
        return results

    personalized = []
    interests = dict(user_profile.get_top_interests(20))

    for result in results:
        base_score = result.get(score_key, 0.0)
        content = result.get(content_key, "").lower()
        content_id = result.get("id", "")

        # 1. Score por contenido preferido previamente
        content_pref_score = user_profile.get_content_score(content_id)

        # 2. Score por match con intereses
        interest_score = 0.0
        for interest, weight in interests.items():
            if interest in content:
                interest_score += weight

        # Normalizar scores
        if interests:
            max_interest = max(interests.values()) if interests else 1
            interest_score = min(interest_score / (max_interest * 3), 1.0)

        content_pref_normalized = 1 / (1 + math.exp(-content_pref_score / 5))

        # Combinar: personal_score = promedio de interest + content_pref
        personal_score = (interest_score + content_pref_normalized) / 2

        # Score final: (1-alpha) * base + alpha * personal
        final_score = (1 - alpha) * base_score + alpha * personal_score

        # Crear resultado personalizado
        personalized_result = result.copy()
        personalized_result["base_score"] = float(base_score)
        personalized_result["personal_score"] = float(personal_score)
        personalized_result["final_score"] = float(final_score)

        personalized.append(personalized_result)

    # Ordenar por score final
    personalized.sort(key=lambda x: x["final_score"], reverse=True)

    return personalized


def adapt_system_prompt(
    base_prompt: str,
    user_profile: 'UserProfile'
) -> str:
    """
    Adapta system prompt según preferencias del usuario.

    Args:
        base_prompt: Prompt base del sistema
        user_profile: Perfil del usuario

    Returns:
        Prompt adaptado con instrucciones de personalización
    """
    if not user_profile:
        return base_prompt

    summary = user_profile.get_summary()
    adaptations = []

    # Añadir contexto de intereses
    if summary["top_interests"]:
        interests_str = ", ".join([i[0] for i in summary["top_interests"][:3]])
        adaptations.append(f"El usuario ha mostrado interés en: {interests_str}.")

    # Añadir contexto de objeciones previas
    if summary["recent_objections"]:
        objections_str = ", ".join(summary["recent_objections"])
        adaptations.append(f"Ha mencionado estas objeciones antes: {objections_str}. Tenlo en cuenta.")

    # Añadir productos de interés
    if summary["interested_products"]:
        products_str = ", ".join([p for p in summary["interested_products"] if p])
        if products_str:
            adaptations.append(f"Ha preguntado por: {products_str}.")

    # Estilo de respuesta
    prefs = summary.get("preferences", {})
    style = prefs.get("response_style", "balanced")
    if style == "concise":
        adaptations.append("Sé conciso y directo.")
    elif style == "detailed":
        adaptations.append("Proporciona explicaciones detalladas.")

    # Combinar
    if adaptations:
        context = "\n\nCONTEXTO DEL USUARIO:\n" + "\n".join(f"- {a}" for a in adaptations)
        return base_prompt + context

    return base_prompt
