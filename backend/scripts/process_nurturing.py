#!/usr/bin/env python3
"""
Script para procesar follow-ups de nurturing pendientes.

Este script debe ejecutarse periódicamente (cron, scheduler, etc.) para:
1. Buscar followups pendientes que ya deberían enviarse
2. Enviar los mensajes correspondientes
3. Marcar como enviados

Uso:
    python scripts/process_nurturing.py
    python scripts/process_nurturing.py --creator-id manel
    python scripts/process_nurturing.py --dry-run  # Solo mostrar, no enviar
"""

import asyncio
import argparse
import sys
import os
import logging
from datetime import datetime

# Añadir directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.nurturing import get_nurturing_manager, FollowUp
from core.dm_agent import DMResponderAgent

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("nurturing-processor")


async def send_followup_message(
    creator_id: str,
    follower_id: str,
    message: str,
    dry_run: bool = False
) -> bool:
    """
    Enviar mensaje de followup.

    En producción, esto debería usar el InstagramHandler o TelegramAdapter
    para enviar el mensaje real.

    Args:
        creator_id: ID del creador
        follower_id: ID del seguidor
        message: Mensaje a enviar
        dry_run: Si True, solo simula el envío

    Returns:
        True si se envió correctamente
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would send to {follower_id}: {message[:50]}...")
        return True

    try:
        # Detectar plataforma del follower_id
        if follower_id.startswith("ig_"):
            # Instagram
            from core.instagram_handler import get_instagram_handler
            handler = get_instagram_handler(creator_id=creator_id)
            real_id = follower_id[3:]  # Quitar prefijo "ig_"
            success = await handler.send_response(real_id, message)
            return success

        elif follower_id.startswith("tg_"):
            # Telegram
            from core.telegram_adapter import get_telegram_adapter
            adapter = get_telegram_adapter(creator_id=creator_id)
            chat_id = int(follower_id[3:])  # Quitar prefijo "tg_"
            success = await adapter.send_message(chat_id, message)
            return success

        else:
            # Plataforma desconocida - log para revisión manual
            logger.warning(f"Unknown platform for follower {follower_id}")
            # Guardar en archivo para envío manual
            manual_file = f"data/nurturing/manual_sends.txt"
            os.makedirs(os.path.dirname(manual_file), exist_ok=True)
            with open(manual_file, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()}|{creator_id}|{follower_id}|{message}\n")
            logger.info(f"Saved to manual queue: {follower_id}")
            return True  # Marcar como "enviado" para no reintentar

    except Exception as e:
        logger.error(f"Error sending message to {follower_id}: {e}")
        return False


async def process_pending_followups(
    creator_id: str = None,
    dry_run: bool = False,
    limit: int = 100
) -> dict:
    """
    Procesar todos los followups pendientes.

    Args:
        creator_id: Si se especifica, solo procesa ese creador
        dry_run: Si True, solo muestra qué se enviaría
        limit: Máximo de followups a procesar

    Returns:
        Estadísticas del procesamiento
    """
    nurturing = get_nurturing_manager()
    pending = nurturing.get_pending_followups(creator_id)[:limit]

    stats = {
        "total_pending": len(pending),
        "sent": 0,
        "failed": 0,
        "skipped": 0
    }

    if not pending:
        logger.info("No pending followups found")
        return stats

    logger.info(f"Processing {len(pending)} pending followups...")

    for followup in pending:
        try:
            # Generar mensaje
            message = nurturing.get_followup_message(followup)

            logger.info(f"Processing: {followup.id}")
            logger.info(f"  Follower: {followup.follower_id}")
            logger.info(f"  Sequence: {followup.sequence_type} (step {followup.step})")
            logger.info(f"  Message: {message[:80]}...")

            # Enviar mensaje
            success = await send_followup_message(
                creator_id=followup.creator_id,
                follower_id=followup.follower_id,
                message=message,
                dry_run=dry_run
            )

            if success:
                if not dry_run:
                    nurturing.mark_as_sent(followup)
                stats["sent"] += 1
                logger.info(f"  ✅ Sent successfully")
            else:
                stats["failed"] += 1
                logger.error(f"  ❌ Failed to send")

        except Exception as e:
            logger.error(f"Error processing followup {followup.id}: {e}")
            stats["failed"] += 1

    return stats


async def show_stats(creator_id: str = None):
    """Mostrar estadísticas de nurturing"""
    nurturing = get_nurturing_manager()

    if creator_id:
        creators = [creator_id]
    else:
        # Buscar todos los creadores
        creators = []
        storage_path = nurturing.storage_path
        if os.path.exists(storage_path):
            for file in os.listdir(storage_path):
                if file.endswith("_followups.json"):
                    creators.append(file.replace("_followups.json", ""))

    print("\n" + "="*50)
    print("📊 NURTURING STATISTICS")
    print("="*50)

    for cid in creators:
        stats = nurturing.get_stats(cid)
        print(f"\n👤 Creator: {cid}")
        print(f"   Total followups: {stats['total']}")
        print(f"   Pending: {stats['pending']}")
        print(f"   Sent: {stats['sent']}")
        print(f"   Cancelled: {stats['cancelled']}")

        if stats['by_sequence']:
            print("   By sequence:")
            for seq, seq_stats in stats['by_sequence'].items():
                print(f"     - {seq}: {seq_stats}")

    # Mostrar próximos followups
    print("\n📅 NEXT PENDING FOLLOWUPS:")
    pending = nurturing.get_pending_followups(creator_id)[:10]

    if pending:
        for fu in pending:
            scheduled = datetime.fromisoformat(fu.scheduled_at)
            print(f"   [{fu.creator_id}] {fu.follower_id} - {fu.sequence_type} step {fu.step}")
            print(f"       Scheduled: {scheduled.strftime('%Y-%m-%d %H:%M')}")
    else:
        print("   No pending followups")


async def cleanup(creator_id: str = None, days: int = 30):
    """Limpiar followups antiguos"""
    nurturing = get_nurturing_manager()

    if creator_id:
        creators = [creator_id]
    else:
        creators = []
        storage_path = nurturing.storage_path
        if os.path.exists(storage_path):
            for file in os.listdir(storage_path):
                if file.endswith("_followups.json"):
                    creators.append(file.replace("_followups.json", ""))

    total_removed = 0
    for cid in creators:
        removed = nurturing.cleanup_old_followups(cid, days)
        total_removed += removed
        if removed > 0:
            print(f"Cleaned up {removed} old followups for {cid}")

    print(f"Total cleaned: {total_removed}")


async def main():
    parser = argparse.ArgumentParser(description="Process nurturing followups")
    parser.add_argument("--creator-id", "-c", help="Process only this creator")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Don't send, just show")
    parser.add_argument("--limit", "-l", type=int, default=100, help="Max followups to process")
    parser.add_argument("--stats", "-s", action="store_true", help="Show statistics only")
    parser.add_argument("--cleanup", action="store_true", help="Clean up old followups")
    parser.add_argument("--cleanup-days", type=int, default=30, help="Days to keep (default 30)")

    args = parser.parse_args()

    if args.stats:
        await show_stats(args.creator_id)
        return

    if args.cleanup:
        await cleanup(args.creator_id, args.cleanup_days)
        return

    # Procesar followups pendientes
    print("\n" + "🚀 NURTURING PROCESSOR ".center(50, "="))
    print(f"Creator: {args.creator_id or 'ALL'}")
    print(f"Dry run: {args.dry_run}")
    print(f"Limit: {args.limit}")
    print("="*50 + "\n")

    stats = await process_pending_followups(
        creator_id=args.creator_id,
        dry_run=args.dry_run,
        limit=args.limit
    )

    print("\n" + "="*50)
    print("📋 SUMMARY")
    print("="*50)
    print(f"Total pending: {stats['total_pending']}")
    print(f"Sent: {stats['sent']}")
    print(f"Failed: {stats['failed']}")
    print(f"Skipped: {stats['skipped']}")

    if args.dry_run:
        print("\n⚠️  DRY RUN - No messages were actually sent")


if __name__ == "__main__":
    asyncio.run(main())
