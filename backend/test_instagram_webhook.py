#!/usr/bin/env python3
"""
Test local del webhook de Instagram.
Simula un payload real de Meta y verifica que se procesa correctamente.
"""
import asyncio
import logging
import os
import sys

# Configurar logging para ver TODO
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Asegurar que los módulos del proyecto estén en el path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configurar variables de entorno para el test
os.environ.setdefault("INSTAGRAM_USER_ID", "17841478144668455")
os.environ.setdefault("INSTAGRAM_PAGE_ID", "123456789012345")
os.environ.setdefault("INSTAGRAM_ACCESS_TOKEN", "test_token_for_local_testing")
os.environ.setdefault("OPENAI_API_KEY", "test_key")  # Para que no falle el agente

print("=" * 60)
print("TEST: Instagram Webhook Local")
print("=" * 60)

# Payload simulado de Meta (formato real)
TEST_PAYLOAD = {
    "object": "instagram",
    "entry": [
        {
            "id": "17841478144668455",
            "time": 1702656000000,
            "messaging": [
                {
                    "sender": {
                        "id": "123456789"  # Un seguidor (NO el bot)
                    },
                    "recipient": {
                        "id": "17841478144668455"  # El bot (IG_USER_ID)
                    },
                    "timestamp": 1702656000000,
                    "message": {
                        "mid": "m_test_message_id_12345",
                        "text": "Hola, quiero información"
                    }
                }
            ]
        }
    ]
}

print(f"\nPayload de prueba:")
print(f"  sender_id: 123456789 (seguidor)")
print(f"  recipient_id: 17841478144668455 (bot)")
print(f"  text: 'Hola, quiero información'")
print(f"\nVariables de entorno:")
print(f"  INSTAGRAM_USER_ID: {os.environ.get('INSTAGRAM_USER_ID')}")
print(f"  INSTAGRAM_PAGE_ID: {os.environ.get('INSTAGRAM_PAGE_ID')}")
print()

async def test_webhook():
    """Test del webhook de Instagram"""
    print("=" * 60)
    print("Importando InstagramHandler...")
    print("=" * 60)

    try:
        from core.instagram_handler import InstagramHandler
        print("✓ InstagramHandler importado correctamente")
    except Exception as e:
        print(f"✗ Error importando InstagramHandler: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("Creando handler...")
    print("=" * 60)

    try:
        handler = InstagramHandler(
            access_token="test_token",
            page_id="123456789012345",
            ig_user_id="17841478144668455",
            creator_id="manel"
        )
        print(f"✓ Handler creado")
        print(f"  page_id: {handler.page_id}")
        print(f"  ig_user_id: {handler.ig_user_id}")
    except Exception as e:
        print(f"✗ Error creando handler: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("Procesando webhook...")
    print("=" * 60)

    try:
        # Llamar al método handle_webhook
        result = await handler.handle_webhook(TEST_PAYLOAD, signature="")

        print(f"\n✓ Webhook procesado")
        print(f"  Result: {result}")

        # Verificar resultado
        messages_processed = result.get("messages_processed", 0)
        print(f"\n  messages_processed: {messages_processed}")

        if messages_processed > 0:
            print("\n" + "=" * 60)
            print("✅ TEST PASSED: Mensaje procesado correctamente")
            print("=" * 60)
            return True
        else:
            print("\n" + "=" * 60)
            print("❌ TEST FAILED: Mensaje NO fue procesado (filtrado incorrectamente)")
            print("=" * 60)

            # Debug: mostrar qué pasó
            print("\nDebug - Verificando filtros:")
            print(f"  sender_id del mensaje: 123456789")
            print(f"  handler.page_id: {handler.page_id}")
            print(f"  handler.ig_user_id: {handler.ig_user_id}")
            print(f"  sender == page_id? {str(123456789) == handler.page_id}")
            print(f"  sender == ig_user_id? {str(123456789) == handler.ig_user_id}")
            return False

    except Exception as e:
        print(f"\n✗ Error procesando webhook: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_webhook())
    sys.exit(0 if success else 1)
