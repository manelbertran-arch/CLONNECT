#!/usr/bin/env python3
"""
Clonnect Creators - Backup Script
Crea backups comprimidos del directorio data/
"""

import os
import sys
import shutil
import tarfile
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Configuracion por defecto
DEFAULT_DATA_PATH = "./data"
DEFAULT_BACKUP_PATH = "./backups"
DEFAULT_RETENTION_DAYS = 7


def create_backup(
    data_path: str = DEFAULT_DATA_PATH,
    backup_path: str = DEFAULT_BACKUP_PATH,
    prefix: str = "backup"
) -> str:
    """
    Crear backup comprimido del directorio data.

    Args:
        data_path: Directorio a respaldar
        backup_path: Directorio destino para backups
        prefix: Prefijo del archivo de backup

    Returns:
        Ruta al archivo de backup creado
    """
    data_dir = Path(data_path)
    backup_dir = Path(backup_path)

    # Verificar que existe el directorio de datos
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_path}")
        sys.exit(1)

    # Crear directorio de backups si no existe
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generar nombre del archivo con timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"{prefix}_{timestamp}.tar.gz"
    backup_filepath = backup_dir / backup_filename

    logger.info(f"Creating backup: {backup_filepath}")

    # Calcular tamaño aproximado
    total_size = sum(
        f.stat().st_size for f in data_dir.rglob('*') if f.is_file()
    )
    logger.info(f"Data size: {total_size / (1024*1024):.2f} MB")

    # Crear archivo tar.gz
    try:
        with tarfile.open(backup_filepath, "w:gz") as tar:
            tar.add(data_dir, arcname="data")

        backup_size = backup_filepath.stat().st_size
        compression_ratio = (1 - backup_size / total_size) * 100 if total_size > 0 else 0

        logger.info(f"Backup created: {backup_filepath}")
        logger.info(f"Backup size: {backup_size / (1024*1024):.2f} MB")
        logger.info(f"Compression: {compression_ratio:.1f}%")

        return str(backup_filepath)

    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        sys.exit(1)


def cleanup_old_backups(
    backup_path: str = DEFAULT_BACKUP_PATH,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    dry_run: bool = False
) -> int:
    """
    Eliminar backups antiguos.

    Args:
        backup_path: Directorio de backups
        retention_days: Dias de retención
        dry_run: Si True, solo muestra qué se eliminaría

    Returns:
        Número de backups eliminados
    """
    backup_dir = Path(backup_path)

    if not backup_dir.exists():
        logger.info("No backups directory found")
        return 0

    cutoff_date = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0

    logger.info(f"Cleaning up backups older than {retention_days} days")
    logger.info(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")

    for backup_file in backup_dir.glob("backup_*.tar.gz"):
        try:
            # Extraer fecha del nombre del archivo
            # Formato: backup_YYYY-MM-DD_HH-MM-SS.tar.gz
            date_str = backup_file.stem.replace("backup_", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")

            if file_date < cutoff_date:
                if dry_run:
                    logger.info(f"Would delete: {backup_file.name}")
                else:
                    backup_file.unlink()
                    logger.info(f"Deleted: {backup_file.name}")
                deleted_count += 1

        except ValueError:
            # No es un archivo de backup con formato correcto
            continue
        except Exception as e:
            logger.error(f"Error processing {backup_file}: {e}")

    if deleted_count == 0:
        logger.info("No old backups to delete")
    else:
        action = "Would delete" if dry_run else "Deleted"
        logger.info(f"{action} {deleted_count} old backup(s)")

    return deleted_count


def list_backups(backup_path: str = DEFAULT_BACKUP_PATH):
    """
    Listar backups existentes.

    Args:
        backup_path: Directorio de backups
    """
    backup_dir = Path(backup_path)

    if not backup_dir.exists():
        logger.info("No backups directory found")
        return

    backups = sorted(backup_dir.glob("backup_*.tar.gz"), reverse=True)

    if not backups:
        logger.info("No backups found")
        return

    print("\n" + "=" * 60)
    print("EXISTING BACKUPS")
    print("=" * 60)

    total_size = 0
    for backup_file in backups:
        size = backup_file.stat().st_size
        total_size += size
        size_mb = size / (1024 * 1024)

        # Extraer fecha del nombre
        try:
            date_str = backup_file.stem.replace("backup_", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S")
            age = datetime.now() - file_date
            age_str = f"{age.days}d" if age.days > 0 else f"{age.seconds // 3600}h"
        except ValueError:
            age_str = "?"

        print(f"  {backup_file.name} - {size_mb:.2f} MB - {age_str} ago")

    print("-" * 60)
    print(f"Total: {len(backups)} backups, {total_size / (1024*1024):.2f} MB")
    print("=" * 60 + "\n")


def restore_backup(backup_file: str, data_path: str = DEFAULT_DATA_PATH):
    """
    Restaurar un backup.

    Args:
        backup_file: Ruta al archivo de backup
        data_path: Directorio destino
    """
    backup_path = Path(backup_file)
    data_dir = Path(data_path)

    if not backup_path.exists():
        logger.error(f"Backup file not found: {backup_file}")
        sys.exit(1)

    logger.info(f"Restoring backup: {backup_file}")

    # Crear backup del estado actual antes de restaurar
    if data_dir.exists():
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        pre_restore_backup = data_dir.parent / f"data_pre_restore_{timestamp}"
        logger.info(f"Creating pre-restore backup: {pre_restore_backup}")
        shutil.move(str(data_dir), str(pre_restore_backup))

    try:
        with tarfile.open(backup_path, "r:gz") as tar:
            tar.extractall(data_dir.parent)

        logger.info(f"Backup restored successfully to: {data_path}")

    except Exception as e:
        logger.error(f"Error restoring backup: {e}")
        # Intentar restaurar el estado anterior
        if pre_restore_backup.exists():
            logger.info("Attempting to restore previous state...")
            shutil.move(str(pre_restore_backup), str(data_dir))
        sys.exit(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Clonnect Creators - Backup Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/backup.py                     # Create backup
  python scripts/backup.py --cleanup           # Cleanup old backups
  python scripts/backup.py --cleanup --dry-run # Preview cleanup
  python scripts/backup.py --list              # List backups
  python scripts/backup.py --restore <file>    # Restore backup
        """
    )

    parser.add_argument(
        "--data-path",
        default=DEFAULT_DATA_PATH,
        help=f"Data directory to backup (default: {DEFAULT_DATA_PATH})"
    )

    parser.add_argument(
        "--backup-path",
        default=DEFAULT_BACKUP_PATH,
        help=f"Backup destination (default: {DEFAULT_BACKUP_PATH})"
    )

    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up old backups"
    )

    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f"Days to retain backups (default: {DEFAULT_RETENTION_DAYS})"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without doing it"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List existing backups"
    )

    parser.add_argument(
        "--restore",
        metavar="FILE",
        help="Restore from backup file"
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("    CLONNECT CREATORS - BACKUP TOOL")
    print("=" * 60 + "\n")

    if args.list:
        list_backups(args.backup_path)
        return

    if args.restore:
        response = input(f"Restore from {args.restore}? This will overwrite current data. (y/N): ")
        if response.lower() == 'y':
            restore_backup(args.restore, args.data_path)
        else:
            logger.info("Restore cancelled")
        return

    if args.cleanup:
        cleanup_old_backups(
            args.backup_path,
            args.retention_days,
            args.dry_run
        )
        return

    # Default: create backup
    backup_file = create_backup(args.data_path, args.backup_path)

    print(f"\nBackup complete: {backup_file}")
    print("Run with --list to see all backups")
    print("Run with --cleanup to remove old backups\n")


if __name__ == "__main__":
    main()
