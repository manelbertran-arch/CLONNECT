import requests
import json
import time
from datetime import datetime

BASE_URL = "https://web-production-9f69.up.railway.app/dm/process"
CREATOR = "stefano_bonanno"

# 100 mensajes de test organizados por categoría
TEST_MESSAGES = {
    # Happy Path (1-10)
    "happy": [
        ["Hola! Vi tu post sobre fitness", "Me interesa perder peso", "Cuéntame más", "¿Cuánto cuesta?", "Vale, lo quiero"],
        ["Hey! Info sobre tu programa", "Quiero definir", "Sí, me interesa", "¿Qué incluye?", "Perfecto, ¿cómo pago?"],
        ["Buenas! Quiero empezar a entrenar", "Necesito ayuda", "¿Tienes algo para principiantes?", "Suena bien", "Me apunto"],
        ["Hola Stefano!", "Vi tus transformaciones", "Quiero resultados así", "¿Es posible?", "Vamos a ello"],
        ["Qué tal! Me recomendaron tu programa", "Quiero info", "¿Funciona de verdad?", "Ok me convence", "¿Link de pago?"],
        ["Holaaa", "Quiero cambiar mi físico", "¿Me puedes ayudar?", "Genial", "Lo compro"],
        ["Buenas tardes", "Busco entrenador online", "¿Qué ofreces?", "Me interesa el reto", "Adelante"],
        ["Hola! Empiezo el gym", "Necesito guía", "¿Tienes programa?", "Perfecto", "Quiero empezar"],
        ["Hey Stefano", "Quiero ponerme en forma", "¿Cómo funciona?", "Suena genial", "Cuenta conmigo"],
        ["Hola!", "Vi tu contenido", "Me motiva mucho", "Quiero ser tu alumno", "¿Cómo me inscribo?"],
    ],
    # Objeciones precio (11-20)
    "price": [
        ["Hola, info del programa", "¿Cuánto cuesta?", "Uff es caro", "No tengo tanto dinero", "Quizás más adelante"],
        ["Info please", "¿Precio?", "Es mucho para mí", "No puedo permitírmelo", "Gracias igual"],
        ["Hola", "¿Cuánto vale?", "Está fuera de mi presupuesto", "¿Hay descuento?", "Sigue siendo mucho"],
        ["Buenas", "Precio?", "Muy caro", "¿Opciones más baratas?", "No gracias"],
        ["Hey", "¿Cuánto es?", "No tengo ese dinero ahora", "¿Se puede pagar a plazos?", "Aún así es mucho"],
        ["Hola", "Info y precio", "Es bastante", "¿Vale la pena?", "Lo pensaré"],
        ["Qué tal", "¿Cuánto cuesta tu programa?", "Es más de lo que esperaba", "¿Por qué tan caro?", "Entiendo pero no puedo"],
        ["Hola!", "Precio del reto?", "Uf", "Es mucho", "Paso por ahora"],
        ["Buenas", "¿Cuánto?", "No me lo puedo permitir", "Ojalá pudiera", "Gracias"],
        ["Hey", "¿Precio?", "Demasiado", "¿Algo gratis?", "Ok"],
    ],
    # Objeciones tiempo (21-30)
    "time": [
        ["Hola, me interesa", "Pero no tengo tiempo", "Trabajo mucho", "¿Cuánto tiempo requiere?", "Es demasiado"],
        ["Info", "¿Cuántas horas al día?", "No tengo tanto tiempo", "Imposible para mí", "Quizás cuando tenga más tiempo"],
        ["Hola", "Me interesa pero viajo mucho", "¿Se puede hacer viajando?", "Difícil", "Lo veo complicado"],
        ["Buenas", "Tengo 3 hijos", "Cero tiempo libre", "¿Es realista?", "No creo que pueda"],
        ["Hey", "Trabajo 12 horas", "¿Hay versión express?", "Sigue siendo mucho", "No me da la vida"],
        ["Hola", "¿Cuánto tiempo al día?", "Mucho", "No tengo ese tiempo", "Imposible"],
        ["Qué tal", "Me interesa pero...", "Mi agenda está llena", "¿Flexible?", "Difícil"],
        ["Hola!", "No tengo tiempo para gym", "¿Se puede en casa?", "¿Cuánto dura?", "Es mucho"],
        ["Buenas", "Soy madre soltera", "Cero tiempo", "¿Opciones cortas?", "Aún así complicado"],
        ["Hey", "Tiempo?", "Mucho", "No puedo", "Gracias igual"],
    ],
    # Objeciones duda (31-40)
    "doubt": [
        ["Hola", "No sé si esto funciona", "He probado otras cosas", "¿Por qué sería diferente?", "No estoy convencido"],
        ["Info", "¿Funciona de verdad?", "Tengo dudas", "¿Garantía?", "Mmm no sé"],
        ["Hola", "Suena bien pero...", "¿Resultados reales?", "¿Testimonios?", "Sigo con dudas"],
        ["Buenas", "¿Es efectivo?", "He fallado antes", "¿Por qué funcionaría ahora?", "No confío"],
        ["Hey", "Dudas", "¿Funciona para todos?", "¿Y si no me funciona?", "Riesgo"],
        ["Hola", "No sé...", "Parece demasiado bueno", "¿Es real?", "Desconfío"],
        ["Qué tal", "Tengo mis dudas", "¿Pruebas?", "¿Casos de éxito?", "Aún no me convence"],
        ["Hola!", "¿Realmente funciona?", "Lo dudo", "¿Qué pasa si no?", "No sé"],
        ["Buenas", "Escéptico", "¿Por qué confiar?", "¿Diferencia con otros?", "Hmm"],
        ["Hey", "Dudoso", "No creo", "Convénceme", "Sigo sin verlo"],
    ],
    # Lead magnet (41-50)
    "leadmagnet": [
        ["Hola, ¿tienes algo gratis?", "Quiero probar antes", "¿Guía gratuita?", "Mándamela", "Gracias"],
        ["Hey, contenido free?", "No quiero pagar aún", "¿Algo para empezar?", "Ok", "Gracias"],
        ["Hola", "¿Recursos gratuitos?", "Quiero ver tu contenido primero", "¿PDF?", "Dale"],
        ["Buenas", "Algo gratis?", "Para probar", "¿Tienes?", "Manda"],
        ["Info gratis", "No pago sin probar", "¿Muestra?", "Ok", "Gracias"],
        ["Hola", "¿Contenido gratuito?", "Quiero conocerte primero", "¿Newsletter?", "Apúntame"],
        ["Hey", "Free content?", "Antes de comprar", "¿Tienes algo?", "Mándalo"],
        ["Hola!", "¿Guía gratis?", "Para empezar", "¿La tienes?", "Porfa"],
        ["Buenas", "Algo sin coste?", "Probar antes", "¿Sí o no?", "Ok"],
        ["Gratis?", "Free?", "¿Hay?", "Manda", "Thx"],
    ],
    # Booking (51-60)
    "booking": [
        ["Hola, quiero una llamada", "¿Podemos hablar?", "Agendar cita", "¿Cuándo puedes?", "Perfecto"],
        ["Hey, prefiero hablar por teléfono", "¿Tienes calendario?", "Quiero reservar", "Ok", "Gracias"],
        ["Hola", "¿Hacemos videollamada?", "Para resolver dudas", "¿Link?", "Agendado"],
        ["Buenas", "Quiero call contigo", "¿Disponibilidad?", "¿Cómo agendo?", "Listo"],
        ["Llamada?", "Hablar directo", "¿Se puede?", "¿Cuándo?", "Ok"],
        ["Hola", "Prefiero llamada", "¿Tienes hueco?", "Esta semana?", "Perfecto"],
        ["Hey", "¿Consulta gratuita?", "Quiero hablar", "¿Zoom?", "Dale"],
        ["Hola!", "Agendar llamada", "Para conocerte", "¿Calendario?", "Reservo"],
        ["Buenas", "Video call?", "¿Posible?", "¿Link?", "Gracias"],
        ["Call?", "Hablar?", "¿Puedes?", "¿Cuándo?", "Ok"],
    ],
    # Escalación (61-70)
    "escalation": [
        ["Hola", "Quiero hablar con Stefano", "Con el real", "No con bot", "Pásame con él"],
        ["Hey", "¿Eres Stefano de verdad?", "Quiero hablar con humano", "Persona real", "Por favor"],
        ["Hola", "Necesito atención humana", "No automática", "¿Está Stefano?", "Conecta"],
        ["Buenas", "Hablar con persona", "No bot", "Real", "Urgente"],
        ["Dame con un agente", "Humano", "Persona", "Ya", "Por favor"],
        ["Hola", "Esto es un bot?", "Quiero humano", "Stefano real", "Pasa"],
        ["Hey", "Prefiero hablar con Stefano", "Directamente", "¿Está?", "Conecta"],
        ["Hola!", "Atención personalizada", "No automática", "Humano", "Gracias"],
        ["Buenas", "Bot?", "Humano please", "Real", "Ya"],
        ["Stefano?", "Real?", "Humano?", "Pásame", "Ya"],
    ],
    # Preguntas producto (71-80)
    "product": [
        ["Hola", "¿Qué incluye el programa?", "¿Cuánto dura?", "¿Hay seguimiento?", "¿Soporte?"],
        ["Hey", "Info completa", "¿Qué obtengo?", "¿Plan nutricional?", "¿Ejercicios?"],
        ["Hola", "Detalles del reto", "¿11 días?", "¿Qué pasa después?", "¿Mantenimiento?"],
        ["Buenas", "¿Cómo funciona?", "¿App?", "¿Videos?", "¿PDFs?"],
        ["Info", "¿Qué es exactamente?", "¿Para quién?", "¿Resultados?", "¿Garantía?"],
        ["Hola", "Cuéntame todo", "¿Dieta?", "¿Entreno?", "¿Suplementos?"],
        ["Hey", "¿Qué diferencia hay con otros?", "¿Por qué el tuyo?", "¿Único?", "Explica"],
        ["Hola!", "Programa completo?", "¿Todo incluido?", "¿Extra?", "¿Comunidad?"],
        ["Buenas", "Detalles", "Más info", "¿Acceso?", "¿Duración?"],
        ["Info?", "Qué es?", "Cómo?", "Cuánto?", "Incluye?"],
    ],
    # Respuestas cortas (81-90)
    "short": [
        ["si"], ["no"], ["ok"], ["vale"], ["mm"],
        ["jaja"], ["👍"], ["🤔"], ["?"], ["..."],
    ],
    # Edge cases (91-100)
    "edge": [
        ["Hello! I want info", "How much?", "Thanks"],
        ["Hola crack", "Eres el mejor", "Quiero ser como tú", "Máquina", "Ídolo"],
        ["🔥🔥🔥", "💪💪", "🙌", "❤️", "👏"],
        ["asdfghjkl", "???", "...", "jsjsjsjs", "xd"],
        ["HOLA", "QUIERO INFO", "PRECIO", "OK", "GRACIAS"],
        ["Hola. Punto.", "Info. Punto.", "Ya.", "Aja.", "Bien."],
        ["Oye una pregunta", "Bueno da igual", "Nada", "Olvídalo", "Chao"],
        ["Hola qué tal cómo estás espero que bien te escribo porque vi tu perfil", "Me interesa todo lo que haces", "Eres increíble"],
        ["hla", "kiero inf", "qnto csta", "ok", "thnks"],
        ["¿Hola?", "¿Info?", "¿Precio?", "¿Sí?", "¿No?"],
    ],
}

results = {
    "total": 0,
    "pass": 0,
    "fail": 0,
    "errors": [],
    "by_category": {}
}

def send_message(follower_id, message, follower_name="Test User", retries=3):
    for attempt in range(retries):
        try:
            response = requests.post(BASE_URL, json={
                "creator_id": CREATOR,
                "follower_id": follower_id,
                "follower_name": follower_name,
                "message": message,
                "platform": "instagram"
            }, timeout=30)
            return response.json()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return {"error": str(e)}

def run_conversation(conv_id, messages, category):
    follower_id = f"test100_{category}_{conv_id}_{int(time.time())}"
    conv_results = []

    for i, msg in enumerate(messages):
        result = send_message(follower_id, msg)
        is_ok = "response" in result or "error" not in result
        conv_results.append({
            "message": msg[:50],
            "response": str(result.get("response", result.get("error", "NO RESPONSE")))[:100],
            "intent": result.get("intent", "unknown"),
            "ok": is_ok
        })
        time.sleep(0.3)  # Rate limit

    return conv_results

def run_all_tests():
    print(f"🚀 Starting 100 conversation tests at {datetime.now()}")
    print("=" * 60)

    conv_num = 0
    for category, conversations in TEST_MESSAGES.items():
        print(f"\n📁 Category: {category.upper()} ({len(conversations)} convs)")
        results["by_category"][category] = {"pass": 0, "fail": 0, "details": []}

        for conv_idx, messages in enumerate(conversations):
            conv_num += 1
            conv_results = run_conversation(conv_num, messages, category)

            # Check if conversation passed
            errors_in_conv = [r for r in conv_results if not r["ok"]]
            passed = len(errors_in_conv) == 0

            results["total"] += 1
            if passed:
                results["pass"] += 1
                results["by_category"][category]["pass"] += 1
                status = "✅"
            else:
                results["fail"] += 1
                results["by_category"][category]["fail"] += 1
                results["errors"].append({
                    "conv": conv_num,
                    "category": category,
                    "errors": errors_in_conv
                })
                status = "❌"

            # Show progress
            print(f"  {status} Conv {conv_num:3d}: {len(messages)} msgs, {len(errors_in_conv)} errors")

            results["by_category"][category]["details"].append({
                "conv": conv_num,
                "passed": passed,
                "messages": len(messages),
                "results": conv_results
            })

    # Final summary
    print("\n" + "=" * 60)
    print("📊 FINAL RESULTS")
    print("=" * 60)
    print(f"Total: {results['total']}")
    print(f"Pass: {results['pass']} ({results['pass']/results['total']*100:.1f}%)")
    print(f"Fail: {results['fail']} ({results['fail']/results['total']*100:.1f}%)")
    print("\nBy category:")
    for cat, data in results["by_category"].items():
        total_cat = data['pass'] + data['fail']
        print(f"  {cat:12s}: {data['pass']}/{total_cat} pass ({data['pass']/total_cat*100:.0f}%)")

    if results["errors"]:
        print(f"\n❌ ERRORS FOUND ({len(results['errors'])}):")
        for err in results["errors"][:10]:  # Show first 10
            print(f"  Conv {err['conv']} ({err['category']})")
            for e in err['errors'][:2]:
                print(f"    - {e['message'][:40]}... → {e['response'][:50]}...")

    print("\n" + "=" * 60)
    print(f"🏁 Completed at {datetime.now()}")
    return results

if __name__ == "__main__":
    run_all_tests()
