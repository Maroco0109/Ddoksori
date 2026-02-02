#!/bin/bash
# DDOKSORI Database Backup Script
# Backs up PostgreSQL database to S3
#
# Required environment variables:
#   DB_HOST, DB_USER, DB_NAME, PGPASSWORD (or DB_PASSWORD)
#   AWS credentials (via env or AWS CLI config)
#
# Usage:
#   ./backup_to_s3.sh              # Weekly backup (default)
#   ./backup_to_s3.sh monthly      # Monthly backup
#   ./backup_to_s3.sh manual       # Manual backup

set -euo pipefail

# Configuration
S3_BUCKET="${S3_BUCKET:-ddoksori-backups}"
BACKUP_TYPE="${1:-weekly}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="ddoksori_${TIMESTAMP}.sql.gz"
TMP_DIR="/tmp"

# Use DB_PASSWORD if PGPASSWORD not set
export PGPASSWORD="${PGPASSWORD:-$DB_PASSWORD}"

# Validate required variables
for var in DB_HOST DB_USER DB_NAME PGPASSWORD; do
    if [[ -z "${!var:-}" ]]; then
        echo "Error: $var is not set" >&2
        exit 1
    fi
done

echo "Starting backup: ${BACKUP_FILE}"
echo "Target: s3://${S3_BUCKET}/${BACKUP_TYPE}/"

# 1. Create backup with pg_dump
echo "Step 1/4: Running pg_dump..."
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
    --no-owner --no-privileges \
    | gzip > "${TMP_DIR}/${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${TMP_DIR}/${BACKUP_FILE}" | cut -f1)
echo "Backup size: ${BACKUP_SIZE}"

# 2. Upload to S3
echo "Step 2/4: Uploading to S3..."
aws s3 cp "${TMP_DIR}/${BACKUP_FILE}" "s3://${S3_BUCKET}/${BACKUP_TYPE}/${BACKUP_FILE}"

# 3. Update latest pointer
echo "Step 3/4: Updating latest pointer..."
aws s3 cp "s3://${S3_BUCKET}/${BACKUP_TYPE}/${BACKUP_FILE}" \
    "s3://${S3_BUCKET}/${BACKUP_TYPE}/latest.sql.gz"

# 4. Cleanup local file
echo "Step 4/4: Cleaning up..."
rm -f "${TMP_DIR}/${BACKUP_FILE}"

# 5. Cleanup old backups (retention policy)
echo "Applying retention policy..."
case "$BACKUP_TYPE" in
    weekly)
        # Keep last 4 weeks
        RETENTION_DAYS=28
        ;;
    monthly)
        # Keep last 12 months
        RETENTION_DAYS=365
        ;;
    manual)
        # No auto-cleanup for manual backups
        RETENTION_DAYS=0
        ;;
esac

if [[ $RETENTION_DAYS -gt 0 ]]; then
    CUTOFF_DATE=$(date -d "-${RETENTION_DAYS} days" +%Y%m%d 2>/dev/null || date -v-${RETENTION_DAYS}d +%Y%m%d)
    echo "Removing backups older than: ${CUTOFF_DATE}"

    aws s3 ls "s3://${S3_BUCKET}/${BACKUP_TYPE}/" | while read -r line; do
        FILE_NAME=$(echo "$line" | awk '{print $4}')
        if [[ "$FILE_NAME" =~ ddoksori_([0-9]{8})_ ]]; then
            FILE_DATE="${BASH_REMATCH[1]}"
            if [[ "$FILE_DATE" < "$CUTOFF_DATE" && "$FILE_NAME" != "latest.sql.gz" ]]; then
                echo "Deleting old backup: ${FILE_NAME}"
                aws s3 rm "s3://${S3_BUCKET}/${BACKUP_TYPE}/${FILE_NAME}"
            fi
        fi
    done
fi

echo ""
echo "=== Backup completed successfully ==="
echo "File: ${BACKUP_FILE}"
echo "Size: ${BACKUP_SIZE}"
echo "Location: s3://${S3_BUCKET}/${BACKUP_TYPE}/${BACKUP_FILE}"
echo "Latest: s3://${S3_BUCKET}/${BACKUP_TYPE}/latest.sql.gz"
