#!/bin/bash
# =============================================================================
# CLONNECT Database Backup Script
# Backs up PostgreSQL database to S3 (or local if S3 not configured)
# =============================================================================

set -e

# Configuration
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/clonnect_backups"
BACKUP_FILE="clonnect_backup_${DATE}.sql"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== CLONNECT Database Backup ===${NC}"
echo "Date: $(date)"

# Check DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}ERROR: DATABASE_URL not set${NC}"
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Perform backup
echo -e "${YELLOW}Creating database backup...${NC}"
pg_dump "$DATABASE_URL" > "$BACKUP_PATH"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Backup created: ${BACKUP_FILE}${NC}"
    BACKUP_SIZE=$(ls -lh "$BACKUP_PATH" | awk '{print $5}')
    echo "Backup size: ${BACKUP_SIZE}"
else
    echo -e "${RED}Backup failed!${NC}"
    exit 1
fi

# Compress backup
echo -e "${YELLOW}Compressing backup...${NC}"
gzip "$BACKUP_PATH"
BACKUP_PATH="${BACKUP_PATH}.gz"

# Upload to S3 if configured
if [ -n "$S3_BUCKET" ] && [ -n "$AWS_ACCESS_KEY_ID" ]; then
    echo -e "${YELLOW}Uploading to S3...${NC}"
    aws s3 cp "$BACKUP_PATH" "s3://${S3_BUCKET}/backups/${BACKUP_FILE}.gz"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Uploaded to S3: s3://${S3_BUCKET}/backups/${BACKUP_FILE}.gz${NC}"

        # Clean up local file after successful upload
        rm "$BACKUP_PATH"
        echo "Local backup file removed"
    else
        echo -e "${RED}S3 upload failed! Backup saved locally: ${BACKUP_PATH}${NC}"
    fi
else
    echo -e "${YELLOW}S3 not configured. Backup saved locally: ${BACKUP_PATH}${NC}"
fi

# Clean up old local backups (keep last 5)
echo -e "${YELLOW}Cleaning up old local backups...${NC}"
cd "$BACKUP_DIR"
ls -t *.gz 2>/dev/null | tail -n +6 | xargs -r rm --
echo "Cleanup complete"

echo -e "${GREEN}=== Backup Complete ===${NC}"
