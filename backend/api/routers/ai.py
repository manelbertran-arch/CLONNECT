"""
AI Router - AI personality generation endpoints (Grok API)
Extracted from main.py as part of refactoring
"""
import json
import logging
import os
import re

import httpx
from fastapi import APIRouter, Body, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------------------------------------------------------
# AI PERSONALITY GENERATION
# ---------------------------------------------------------
@router.post("/generate-rules")
async def generate_ai_rules(request: dict = Body(...)):
    """Generate bot personality rules using AI (Grok)"""
    prompt = request.get("prompt", "")

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt required")

    xai_api_key = (os.getenv("XAI_API_KEY") or "").strip()

    if not xai_api_key:
        # Fallback: generate basic rules locally
        rules = f"- {prompt}"
        return {"rules": rules, "source": "fallback"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {xai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Genera 5-7 reglas claras y concisas para un chatbot de ventas. Cada regla empieza con '- '. Solo devuelve las reglas, sin explicaciones adicionales. Las reglas deben ser en español.",
                        },
                        {
                            "role": "user",
                            "content": f"El usuario quiere un bot con esta personalidad: {prompt}",
                        },
                    ],
                    "max_tokens": 300,
                    "temperature": 0.7,
                },
            )

            if response.status_code == 200:
                data = response.json()
                rules = data["choices"][0]["message"]["content"]
                return {"rules": rules, "source": "grok"}
            else:
                logger.warning(f"Grok API error: {response.status_code}")
                # Fallback
                rules = f"- {prompt}"
                return {"rules": rules, "source": "fallback"}

    except Exception as e:
        logger.error(f"Error calling Grok API: {e}")
        # Fallback
        rules = f"- {prompt}"
        return {"rules": rules, "source": "fallback"}


@router.post("/generate-knowledge-full")
async def generate_knowledge_full(request: dict = Body(...)):
    """Generate FAQs + extract 'About' info from content"""
    content = request.get("content", "") or request.get("prompt", "")

    if not content:
        raise HTTPException(status_code=400, detail="Content required")

    logger.info(f"Generating full knowledge for: {content[:100]}...")

    xai_api_key = (os.getenv("XAI_API_KEY") or "").strip()

    if not xai_api_key:
        logger.warning("XAI_API_KEY not configured, using fallback")
        fallback_faqs = generate_fallback_faqs(content)
        fallback_about = generate_fallback_about(content)
        return {"faqs": fallback_faqs, "about": fallback_about, "source": "fallback"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            system_prompt = """Genera FAQs PERFECTAS. Eres un experto en redacción comercial.

## REGLAS CRÍTICAS:

1. PRECIOS: Menciona TODOS los productos con nombre y precio exacto
   MAL: "Los precios varían según el producto"
   BIEN: "Curso Trading Pro: 297€. Mentoría 1:1: 500€/mes."

2. NO MEZCLAR PRODUCTOS: Cada producto tiene su propia descripción
   MAL: "Incluye 20h de vídeo... La mentoría cuesta 500€"
   BIEN: "El Curso Trading Pro incluye 20h de vídeo, comunidad y plantillas."

3. REDACCIÓN LIMPIA - EVITA ESTOS ERRORES:
   MAL: "Atendemos de atención:"
   BIEN: "Atendemos de lunes a viernes de 9:00 a 18:00"
   MAL: "El precio es Curso Trading"
   BIEN: "El Curso Trading Pro cuesta 297€"

4. RESPUESTAS COMPLETAS: 20-60 palabras cada una, datos específicos

5. GARANTÍA: Siempre el número exacto de días
   MAL: "Hay garantía de satisfacción"
   BIEN: "Garantía de 30 días con devolución completa"

## GENERA:

1. ABOUT (perfil):
   - bio: 1-2 frases sobre quién es
   - specialties: lista separada por comas
   - experience: años concretos
   - audience: público objetivo

2. FAQS (6-8): precios, qué incluye, garantía, pagos, horario, cómo empezar

## FORMATO JSON (solo esto):
{
  "about": {"bio": "...", "specialties": "...", "experience": "...", "audience": "..."},
  "faqs": [{"question": "?", "answer": "respuesta específica con datos"}]
}"""

            user_message = f"""Extrae la información de este negocio:

{content}

Genera el JSON con about + faqs:"""

            logger.info("Calling Grok API for full knowledge generation...")
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {xai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "max_tokens": 2500,
                    "temperature": 0.05,
                },
            )

            if response.status_code == 200:
                data = response.json()
                result = data["choices"][0]["message"]["content"]
                logger.info(f"Grok full knowledge response: {result[:500]}...")

                # Clean up
                result = re.sub(r"```json\s*", "", result)
                result = re.sub(r"```\s*", "", result)
                result = result.strip()

                json_match = re.search(r"\{[\s\S]*\}", result)
                if json_match:
                    result = json_match.group()

                parsed = json.loads(result)

                # Validate and clean FAQs
                validated_faqs = []
                for faq in parsed.get("faqs", []):
                    answer = faq.get("answer", "")
                    question = faq.get("question", "")

                    # Skip too short answers
                    if len(answer) < 20:
                        continue

                    # Post-process: fix common redundancies
                    answer = answer.replace("Atendemos de atención:", "Atendemos")
                    answer = answer.replace("Atendemos de Atención:", "Atendemos")
                    answer = answer.replace("El precio es Curso", "El Curso")
                    answer = answer.replace("El precio es curso", "El curso")
                    answer = re.sub(r"\s+", " ", answer).strip()  # Fix double spaces

                    # Skip generic answers
                    generic_phrases = ["contacta para más", "contáctanos para", "escríbenos para"]
                    if any(phrase in answer.lower() for phrase in generic_phrases):
                        continue

                    validated_faqs.append({"question": question, "answer": answer})

                logger.info(f"Generated {len(validated_faqs)} FAQs + about info")
                return {"about": parsed.get("about", {}), "faqs": validated_faqs, "source": "grok"}
            else:
                logger.warning(f"Grok API error: {response.status_code}")

    except Exception as e:
        logger.error(f"Error generating full knowledge: {e}")
        import traceback

        logger.error(traceback.format_exc())

    # Fallback
    fallback_faqs = generate_fallback_faqs(content)
    fallback_about = generate_fallback_about(content)
    return {"faqs": fallback_faqs, "about": fallback_about, "source": "fallback"}


def generate_fallback_about(content: str) -> dict:
    """Extract about info from content when API is unavailable"""
    content_lower = content.lower()

    about = {"bio": "", "specialties": "", "experience": "", "audience": ""}

    # Extract bio - first sentence or "Soy..." pattern
    soy_match = re.search(r"[Ss]oy\s+([^.]+)", content)
    if soy_match:
        about["bio"] = f"Soy {soy_match.group(1).strip()}."

    # Extract experience - "desde 2018" or "X años"
    exp_match = re.search(r"desde\s+(\d{4})", content_lower)
    if exp_match:
        year = int(exp_match.group(1))
        years = 2024 - year
        about["experience"] = f"{years} años"
    else:
        years_match = re.search(r"(\d+)\s*años", content_lower)
        if years_match:
            about["experience"] = f"{years_match.group(1)} años"

    # Extract specialties
    specialties = []
    keywords = [
        "trading",
        "criptomonedas",
        "crypto",
        "fitness",
        "coaching",
        "marketing",
        "diseño",
        "programación",
    ]
    for kw in keywords:
        if kw in content_lower:
            specialties.append(kw.capitalize())
    if specialties:
        about["specialties"] = ", ".join(specialties[:3])

    return about


@router.post("/generate-knowledge")
async def generate_ai_knowledge(request: dict = Body(...)):
    """Generate knowledge base content using AI (Grok)"""
    prompt = request.get("prompt", "")
    content_type = request.get("type", "faqs")  # "faqs" or "about"

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt required")

    logger.info(f"Generating {content_type} for content: {prompt[:100]}...")

    xai_api_key = (os.getenv("XAI_API_KEY") or "").strip()

    if not xai_api_key:
        logger.warning("XAI_API_KEY not configured, using smart fallback")
        # Smart fallback: generate FAQs based on keywords in the content
        if content_type == "faqs":
            fallback_faqs = generate_fallback_faqs(prompt)
            return {"faqs": fallback_faqs, "source": "fallback"}
        else:
            return {"about": {"bio": prompt}, "source": "fallback"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if content_type == "faqs":
                system_prompt = """Genera FAQs PERFECTAS para un negocio.

REGLAS ESTRICTAS:

1. PRECIOS: Si hay múltiples productos, lista TODOS con nombre y precio exacto
   MAL: "El precio es 297€"
   BIEN: "El Curso Trading Pro cuesta 297€. La Mentoría 1:1 cuesta 500€/mes."

2. CONTENIDO: Si un producto incluye varias cosas, lista TODO
   MAL: "Incluye videos y comunidad"
   BIEN: "Incluye 20 horas de vídeo, comunidad privada en Telegram, sesiones Q&A semanales, plantillas y acceso de por vida."

3. NO MEZCLAR PRODUCTOS: Cada producto debe tener su propia descripción
   MAL: "Incluye videos... Mentoría 500€/mes..." (mezclado)
   BIEN: Separar en FAQs diferentes

4. REDACCIÓN LIMPIA: Sin redundancias ni errores
   MAL: "Atendemos de atención: Lunes..."
   BIEN: "Atendemos de lunes a viernes de 9:00 a 18:00."

5. RESPUESTAS COMPLETAS: Mínimo 15 palabras, máximo 60

FORMATO (solo JSON, sin explicaciones):
{"faqs":[{"question":"?","answer":"respuesta completa"}]}

EJEMPLO:
Texto: "Curso A: 100€ (videos, comunidad). Mentoría: 200€/mes. Garantía 30 días."
{"faqs":[
{"question":"¿Cuánto cuestan tus productos?","answer":"El Curso A cuesta 100€. La Mentoría cuesta 200€/mes."},
{"question":"¿Qué incluye el Curso A?","answer":"Incluye videos y acceso a comunidad."},
{"question":"¿Qué es la Mentoría?","answer":"Es acompañamiento personalizado por 200€/mes."},
{"question":"¿Tienen garantía?","answer":"Sí, 30 días de garantía de devolución."}
]}"""
            else:
                system_prompt = """Extrae informacion clave sobre el negocio/creador.
Devuelve SOLO un JSON valido:
{"bio": "descripcion breve", "specialties": ["especialidad1"], "experience": "experiencia", "target_audience": "publico"}"""

            user_message = f"""Genera 6-8 FAQs para este negocio:

{prompt}

CHECKLIST antes de responder:
- ¿Mencioné TODOS los productos con sus precios exactos?
- ¿Cada respuesta es completa y específica?
- ¿No hay frases redundantes como "Atendemos de atención"?
- ¿No mezclé información de diferentes productos en la misma respuesta?
- ¿Listó TODO lo que incluye cada producto?

JSON:"""

            logger.info("Calling Grok API with perfected prompt...")
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {xai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.05,
                },
            )

            logger.info(f"Grok API response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if "choices" not in data or len(data["choices"]) == 0:
                    logger.error(f"Grok response missing choices: {data}")
                    raise Exception("Invalid Grok response")

                content = data["choices"][0]["message"]["content"]
                logger.info(f"Grok raw response: {content[:500]}...")

                # Clean up response - remove markdown code blocks
                content = re.sub(r"```json\s*", "", content)
                content = re.sub(r"```\s*", "", content)
                content = content.strip()

                # Try to extract JSON if there's extra text
                json_match = re.search(r"\{[\s\S]*\}", content)
                if json_match:
                    content = json_match.group()

                # Try to parse as JSON
                try:
                    parsed = json.loads(content)

                    if content_type == "faqs":
                        # Handle both {"faqs": [...]} and [...] formats
                        faqs_list = (
                            parsed.get("faqs", parsed) if isinstance(parsed, dict) else parsed
                        )

                        if not isinstance(faqs_list, list):
                            faqs_list = [faqs_list]

                        # POST-GENERATION VALIDATION & CLEANUP
                        validated_faqs = []
                        seen_answers = set()

                        for faq in faqs_list:
                            answer = faq.get("answer", "").strip()
                            question = faq.get("question", "").strip()

                            # Fix common redundancies
                            answer = answer.replace("Atendemos de atención:", "Atendemos")
                            answer = answer.replace("Atendemos de atención", "Atendemos")
                            answer = answer.replace("El precio es Curso", "El Curso")
                            answer = answer.replace("El precio es el Curso", "El Curso")
                            answer = re.sub(r"\s+", " ", answer)  # Fix double spaces

                            # Skip empty or very short answers
                            if len(answer) < 15:
                                logger.warning(f"Skipping short answer: '{answer}'")
                                continue

                            # Skip absurd answers
                            absurd_answers = [
                                "tarjeta",
                                "incluye: tarjeta",
                                "tarjeta.",
                                "stripe",
                                "paypal",
                            ]
                            if answer.lower().strip().rstrip(".") in absurd_answers:
                                logger.warning(f"Skipping absurd answer: '{answer}'")
                                continue

                            # Skip duplicates
                            answer_normalized = answer.lower()[:50]
                            if answer_normalized in seen_answers:
                                logger.warning(f"Skipping duplicate answer: '{answer[:50]}...'")
                                continue
                            seen_answers.add(answer_normalized)

                            validated_faqs.append({"question": question, "answer": answer})

                        logger.info(
                            f"Validated {len(validated_faqs)} FAQs from Grok (filtered from {len(faqs_list)})"
                        )
                        return {"faqs": validated_faqs, "source": "grok"}
                    else:
                        return {"about": parsed, "source": "grok"}

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse Grok response as JSON: {e}")
                    logger.warning(f"Content was: {content}")
                    # Try to extract FAQs from text
                    if content_type == "faqs":
                        extracted = extract_faqs_from_text(content)
                        if extracted:
                            return {"faqs": extracted, "source": "grok-extracted"}
                        return {
                            "faqs": [{"question": "FAQ generado", "answer": content}],
                            "source": "grok-text",
                        }
                    else:
                        return {"about": {"bio": content}, "source": "grok-text"}
            else:
                logger.warning(f"Grok API error: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Error calling Grok API for knowledge: {e}")
        import traceback

        logger.error(traceback.format_exc())

    # Smart fallback
    logger.info("Using smart fallback for FAQ generation")
    if content_type == "faqs":
        fallback_faqs = generate_fallback_faqs(prompt)
        return {"faqs": fallback_faqs, "source": "fallback"}
    else:
        return {"about": {"bio": prompt}, "source": "fallback"}


def generate_fallback_faqs(content: str) -> list:
    """Generate FAQs locally when API is not available - extracts EXACT SPECIFIC data"""
    faqs = []
    content_lower = content.lower()

    # Extract product names with prices (e.g., "Curso Trading Pro: 297€" or "Mentoría 1:1: 500€/mes")
    product_price_patterns = [
        r"[-•]\s*([^:]+?):\s*(\d+)[€$](?:/(\w+))?",  # "- Curso X: 297€" or "- Mentoría: 500€/mes"
        r"([Cc]urso[^:]+?):\s*(\d+)[€$]",  # "Curso Trading Pro: 297€"
        r"([Mm]entoría[^:]+?):\s*(\d+)[€$](?:/(\w+))?",  # "Mentoría 1:1: 500€/mes"
    ]

    products = []
    seen_prices = set()  # Track prices to avoid duplicates

    for pattern in product_price_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            if len(match) >= 2:
                name = match[0].strip()
                price = match[1]
                period = match[2] if len(match) > 2 and match[2] else None

                # Skip if we've already seen this price (avoid duplicates)
                price_key = f"{price}-{period or ''}"
                if price_key in seen_prices:
                    continue
                seen_prices.add(price_key)

                if period:
                    products.append(f"{name}: {price}€/{period}")
                else:
                    products.append(f"{name}: {price}€")

    # If no structured products found, try simple price extraction
    if not products:
        simple_prices = re.findall(r"(\d+)\s*[€$]", content)
        if simple_prices:
            products = [f"{p}€" for p in simple_prices]

    # Build price FAQ
    if products:
        if len(products) == 1:
            faqs.append({"question": "¿Cuánto cuesta?", "answer": f"El precio es {products[0]}."})
        else:
            faqs.append(
                {
                    "question": "¿Cuánto cuesta?",
                    "answer": f"Tenemos varias opciones: {'. '.join(products)}.",
                }
            )

    # Extract what's included - look for parentheses after price OR after "incluye"
    # IMPORTANT: Skip small parentheses with payment words like "(tarjeta)"
    included_text = None

    # First, try to find parentheses that come after a price (e.g., "297€ (20h vídeo, comunidad...)")
    price_paren_match = re.search(
        r"\d+[€$]\s*\(([^)]{15,})\)", content
    )  # Min 15 chars to avoid "(tarjeta)"
    if price_paren_match:
        included_text = price_paren_match.group(1)
    else:
        # Try any parentheses with substantial content (not payment-related)
        all_parens = re.findall(r"\(([^)]+)\)", content)
        for paren_content in all_parens:
            paren_lower = paren_content.lower()
            # Skip payment-related parentheses
            if any(word in paren_lower for word in ["tarjeta", "card", "visa", "mastercard"]):
                continue
            # Skip very short content
            if len(paren_content) < 15:
                continue
            included_text = paren_content
            break

    if included_text:
        faqs.append({"question": "¿Qué incluye?", "answer": f"Incluye: {included_text}."})
    else:
        # Try "incluye:" pattern
        incluye_match = re.search(r"[Ii]ncluye[:\s]+([^.]+)", content)
        if incluye_match:
            faqs.append(
                {
                    "question": "¿Qué incluye?",
                    "answer": f"Incluye: {incluye_match.group(1).strip()}.",
                }
            )

    # Extract guarantee - multiple patterns
    guarantee_patterns = [
        r"[Gg]arantía[:\s]+(\d+)\s*(días?|semanas?|meses?)",
        r"(\d+)\s*(días?|semanas?|meses?)\s*(?:de\s*)?(?:garantía|devolución)",
        r"[Gg]arantía\s*(?:de\s*)?(\d+)\s*(días?|semanas?|meses?)",
    ]

    guarantee = None
    for pattern in guarantee_patterns:
        match = re.search(pattern, content)
        if match:
            guarantee = f"{match.group(1)} {match.group(2)}"
            break

    if guarantee:
        faqs.append(
            {
                "question": "¿Tienen garantía de devolución?",
                "answer": f"Sí, {guarantee} de garantía. Si no estás satisfecho, te devolvemos el dinero.",
            }
        )

    # Extract payment methods - be specific
    payment_methods = []
    if "stripe" in content_lower:
        payment_methods.append("Stripe (tarjeta)")
    elif "tarjeta" in content_lower:
        payment_methods.append("tarjeta")
    if "paypal" in content_lower:
        payment_methods.append("PayPal")
    if "bizum" in content_lower:
        payment_methods.append("Bizum")
    if "transferencia" in content_lower:
        payment_methods.append("transferencia bancaria")

    if payment_methods:
        faqs.append(
            {
                "question": "¿Cuáles son los métodos de pago?",
                "answer": f"Puedes pagar con {', '.join(payment_methods)}.",
            }
        )

    # Extract schedule/hours
    horario_match = re.search(r"[Hh]orario[:\s]+([^\n.]+)", content)
    if horario_match:
        faqs.append(
            {
                "question": "¿Cuál es el horario de atención?",
                "answer": f"Atendemos {horario_match.group(1).strip()}.",
            }
        )

    # Access duration
    if "de por vida" in content_lower or "acceso de por vida" in content_lower:
        faqs.append(
            {
                "question": "¿Por cuánto tiempo tengo acceso?",
                "answer": "Tienes acceso de por vida al contenido.",
            }
        )
    elif "vida" in content_lower:
        faqs.append(
            {"question": "¿Por cuánto tiempo tengo acceso?", "answer": "El acceso es de por vida."}
        )

    # Extract hours of content
    hours_match = re.search(
        r"(\d+)\s*h(?:oras?)?\s*(?:de\s*)?(?:vídeo|video|contenido)", content_lower
    )
    if hours_match:
        faqs.append(
            {
                "question": "¿Cuánto contenido incluye?",
                "answer": f"Incluye {hours_match.group(1)} horas de vídeo.",
            }
        )

    # How to start - only if we have some FAQs
    if faqs:
        faqs.append(
            {
                "question": "¿Cómo puedo empezar?",
                "answer": "Escríbeme y te cuento los pasos para comenzar.",
            }
        )

    return faqs[:8]  # Return max 8 FAQs


def extract_faqs_from_text(text: str) -> list:
    """Try to extract Q&A pairs from unstructured text"""
    faqs = []

    # Try to find Q: A: patterns
    qa_pattern = r"[¿?]([^?¿]+)\?[:\s]*([^¿?]+?)(?=[¿?]|$)"
    matches = re.findall(qa_pattern, text, re.DOTALL)

    for q, a in matches:
        q = q.strip()
        a = a.strip()
        if len(q) > 5 and len(a) > 5:
            faqs.append({"question": f"¿{q}?", "answer": a})

    return faqs if faqs else None
