#!/usr/bin/env python3
"""
Clonnect Creators - Interactive Onboarding Script
Configura un nuevo creador de forma interactiva
"""

import os
import sys
import json
import re
from pathlib import Path

# Agregar el directorio raiz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.creator_config import CreatorConfig, CreatorConfigManager
from core.products import Product, ProductManager
from core.auth import get_auth_manager


def clear_screen():
    """Limpiar pantalla"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    """Mostrar cabecera"""
    print("\n" + "=" * 60)
    print("    CLONNECT CREATORS - ONBOARDING")
    print("    Configura tu clon de IA para responder DMs")
    print("=" * 60 + "\n")


def get_input(prompt: str, default: str = "", required: bool = True) -> str:
    """Obtener input del usuario con valor por defecto"""
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "

    while True:
        value = input(prompt).strip()
        if not value and default:
            return default
        if value or not required:
            return value
        print("  Este campo es obligatorio. Intenta de nuevo.")


def get_choice(prompt: str, options: list, default: int = 1) -> str:
    """Obtener una opcion de una lista"""
    print(f"\n{prompt}")
    for i, option in enumerate(options, 1):
        marker = "*" if i == default else " "
        print(f"  {marker} {i}. {option}")

    while True:
        choice = input(f"\nElige una opcion [1-{len(options)}] (default: {default}): ").strip()
        if not choice:
            return options[default - 1]
        try:
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except ValueError:
            pass
        print("  Opcion no valida. Intenta de nuevo.")


def confirm(prompt: str, default: bool = True) -> bool:
    """Confirmar si/no"""
    default_str = "S/n" if default else "s/N"
    while True:
        response = input(f"{prompt} [{default_str}]: ").strip().lower()
        if not response:
            return default
        if response in ('s', 'si', 'y', 'yes'):
            return True
        if response in ('n', 'no'):
            return False
        print("  Responde 's' o 'n'.")


def validate_creator_id(creator_id: str, config_manager: CreatorConfigManager) -> bool:
    """Validar que el creator_id es valido y no existe"""
    if not creator_id:
        print("  El ID no puede estar vacio.")
        return False

    if not re.match(r'^[a-z0-9_-]+$', creator_id):
        print("  El ID solo puede contener letras minusculas, numeros, guiones y guiones bajos.")
        return False

    if len(creator_id) < 3:
        print("  El ID debe tener al menos 3 caracteres.")
        return False

    if config_manager.get_config(creator_id):
        print(f"  Ya existe un creador con ID '{creator_id}'. Elige otro.")
        return False

    return True


def create_directories(creator_id: str, data_path: str = "./data"):
    """Crear estructura de directorios para el creador"""
    directories = [
        f"{data_path}/memory/{creator_id}",
        f"{data_path}/products",
        f"{data_path}/creators",
        f"{data_path}/analytics",
        f"{data_path}/followers/{creator_id}",
    ]

    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    print(f"\n  Directorios creados correctamente.")


def main():
    """Wizard de onboarding"""
    clear_screen()
    print_header()

    # Inicializar managers
    config_manager = CreatorConfigManager()
    product_manager = ProductManager()
    auth_manager = get_auth_manager()

    print("Vamos a configurar tu clon de IA paso a paso.\n")

    # PASO 1: Creator ID
    print("\n" + "-" * 40)
    print("PASO 1: Identificador del Creador")
    print("-" * 40)
    print("Este sera tu identificador unico en el sistema.")
    print("Ejemplo: 'manel', 'fitnessguru', 'coach-maria'\n")

    while True:
        creator_id = get_input("ID del creador (sin espacios, minusculas)")
        creator_id = creator_id.lower().replace(" ", "-")
        if validate_creator_id(creator_id, config_manager):
            break

    # PASO 2: Nombre
    print("\n" + "-" * 40)
    print("PASO 2: Nombre del Creador")
    print("-" * 40)

    name = get_input("Tu nombre (como te llaman tus seguidores)", creator_id.title())
    instagram_handle = get_input("Tu @ de Instagram (sin @)", creator_id)

    # PASO 3: Descripcion del negocio
    print("\n" + "-" * 40)
    print("PASO 3: Tu Negocio")
    print("-" * 40)

    business_description = get_input(
        "Describe brevemente tu negocio/nicho",
        "Creador de contenido"
    )

    # PASO 4: Tono de comunicacion
    print("\n" + "-" * 40)
    print("PASO 4: Estilo de Comunicacion")
    print("-" * 40)

    tone_options = [
        "cercano - Como hablando con un amigo",
        "profesional - Experto y accesible",
        "divertido - Con humor y energia",
        "inspirador - Motivador y positivo"
    ]
    tone_choice = get_choice("Como te comunicas con tus seguidores?", tone_options, 1)
    tone = tone_choice.split(" - ")[0]

    formality_options = [
        "informal - Tuteo, lenguaje coloquial",
        "formal - Usted, lenguaje profesional",
        "mixto - Adapto segun la persona"
    ]
    formality_choice = get_choice("Nivel de formalidad?", formality_options, 1)
    formality = formality_choice.split(" - ")[0]

    emoji_options = [
        "moderate - 1-2 emojis por mensaje",
        "heavy - Muchos emojis, mucha energia",
        "minimal - Pocos emojis, mas serio",
        "none - Sin emojis"
    ]
    emoji_choice = get_choice("Uso de emojis?", emoji_options, 1)
    emoji_style = emoji_choice.split(" - ")[0]

    # PASO 5: Idioma
    print("\n" + "-" * 40)
    print("PASO 5: Idioma Principal")
    print("-" * 40)

    language_options = [
        "es - Espanol",
        "en - English",
        "pt - Portugues",
        "ca - Catala"
    ]
    language_choice = get_choice("Idioma principal de tus seguidores?", language_options, 1)
    language = language_choice.split(" - ")[0]

    # PASO 6: Producto de ejemplo
    print("\n" + "-" * 40)
    print("PASO 6: Producto/Servicio Principal")
    print("-" * 40)
    print("Vamos a crear tu primer producto para que el bot pueda recomendarlo.\n")

    if confirm("Quieres crear un producto ahora?", True):
        product_name = get_input("Nombre del producto/servicio", "Mi Curso Principal")
        product_price = get_input("Precio (solo numero)", "97")
        try:
            price = float(product_price)
        except ValueError:
            price = 97.0

        product_currency = get_input("Moneda (EUR, USD, etc.)", "EUR")
        product_description = get_input(
            "Descripcion breve",
            f"Aprende con {name} en este curso completo"
        )
        product_link = get_input("Link de pago (opcional)", "", required=False)

        product = Product(
            id=f"{creator_id}-producto-1",
            name=product_name,
            description=product_description,
            price=price,
            currency=product_currency,
            payment_link=product_link,
            category="cursos",
            is_active=True,
            is_featured=True
        )
        has_product = True
    else:
        product = None
        has_product = False

    # PASO 7: Estilo de ventas
    print("\n" + "-" * 40)
    print("PASO 7: Estilo de Ventas")
    print("-" * 40)

    sales_options = [
        "soft - Solo menciono productos si hay interes claro",
        "moderate - Menciono productos cuando es relevante",
        "direct - Soy directo sobre beneficios cuando hay oportunidad"
    ]
    sales_choice = get_choice("Como prefieres vender?", sales_options, 1)
    sales_style = sales_choice.split(" - ")[0]

    # Crear configuracion
    print("\n" + "-" * 40)
    print("CREANDO CONFIGURACION...")
    print("-" * 40)

    # Crear directorios
    create_directories(creator_id)

    # Crear config del creador
    config = CreatorConfig(
        id=creator_id,
        name=name,
        instagram_handle=instagram_handle,
        personality={
            "tone": tone,
            "formality": formality,
            "energy": "alta" if tone in ["divertido", "inspirador"] else "media",
            "humor": tone == "divertido",
            "empathy": True,
            "language": language
        },
        emoji_style=emoji_style,
        sales_style=sales_style,
        is_active=True
    )

    config_manager.create_config(config)
    print(f"  Configuracion creada: data/creators/{creator_id}_config.json")

    # Guardar producto si existe
    if has_product and product:
        product_manager.add_product(creator_id, product)
        print(f"  Producto creado: {product.name}")

    # Generar API key
    print("\n" + "-" * 40)
    print("GENERANDO API KEY...")
    print("-" * 40)

    api_key = auth_manager.generate_api_key(
        creator_id=creator_id,
        name="Onboarding Key"
    )

    # Resumen final
    clear_screen()
    print("\n" + "=" * 60)
    print("    ONBOARDING COMPLETADO!")
    print("=" * 60)

    print(f"""
RESUMEN DE TU CONFIGURACION:
-----------------------------
ID del Creador:     {creator_id}
Nombre:             {name}
Instagram:          @{instagram_handle}
Tono:               {tone}
Formalidad:         {formality}
Emojis:             {emoji_style}
Estilo de ventas:   {sales_style}
Idioma:             {language}
""")

    if has_product:
        print(f"""PRODUCTO CREADO:
----------------
Nombre:             {product.name}
Precio:             {product.price} {product.currency}
""")

    print(f"""
TU API KEY (GUÁRDALA EN UN LUGAR SEGURO):
-----------------------------------------
{api_key}

Esta key no se mostrara de nuevo. Guardala ahora.
""")

    print("""
PROXIMOS PASOS:
---------------
1. Copia tu API key y guardala de forma segura
2. Configura tu .env con las credenciales de Instagram
3. Inicia el servidor: uvicorn api.main:app --reload
4. Prueba enviando un DM de prueba

Para probar el bot manualmente:
  curl -X POST http://localhost:8000/dm/process \\
    -H "X-API-Key: """ + api_key[:20] + """..." \\
    -H "Content-Type: application/json" \\
    -d '{"creator_id": \"""" + creator_id + """\", "sender_id": "test", "message": "Hola!"}'
""")

    print("=" * 60)
    print("    Bienvenido a Clonnect Creators!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOnboarding cancelado.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError durante el onboarding: {e}")
        sys.exit(1)
