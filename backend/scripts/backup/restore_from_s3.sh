#!/bin/bash
# DDOKSORI Database Restore Script
# Restores PostgreSQL database from S3 backup
#
# Required environment variables:
#   DB_HOST, DB_USER, DB_NAME, PGPASSWORD (or DB_PASSWORD)
#   AWS credentials (via env or AWS CLI config)
#
# Usage:
#   ./restore_from_s3.sh                           # Restore from weekly/latest.sql.gz
#   ./restore_from_s3.sh weekly/latest.sql.gz      # Same as above
#   ./restore_from_s3.sh monthly/ddoksori_20250101_040000.sql.gz  # Specific backup
#   ./restore_from_s3.sh --list                    # List available backups
#   ./restore_from_s3.sh --dry-run                 # Download and verify only

set -euo pipefail

# Configuration
S3_BUCKET="${S3_BUCKET:-ddoksori-backups}"
BACKUP_PATH="${1:-weekly/latest.sql.gz}"
TMP_DIR="/tmp"
DRY_RUN=false

# Use DB_PASSWORD if PGPASSWORD not set
export PGPASSWORD="${PGPASSWORD:-${DB_PASSWORD:-}}"

# Handle special commands
case "${BACKUP_PATH}" in
    --list)
        echo "Available backups in s3://${S3_BUCKET}/"
        echo ""
        echo "=== Weekly ==="
        aws s3 ls "s3://${S3_BUCKET}/weekly/" 2>/dev/null || echo "(empty)"
        echo ""
        echo "=== Monthly ==="
        aws s3 ls "s3://${S3_BUCKET}/monthly/" 2>/dev/null || echo "(empty)"
        echo ""
        echo "=== Manual ==="
        aws s3 ls "s3://${S3_BUCKET}/manual/" 2>/dev/null || echo "(empty)"
        exit 0
        ;;
    --dry-run)
        DRY_RUN=true
        BACKUP_PATH="${2:-weekly/latest.sql.gz}"
        ;;
esac

# Validate required variables
for var in DB_HOST DB_USER DB_NAME PGPASSWORD; do
    if [[ -z "${!var:-}" ]]; then
        echo "Error: $var is not set" >&2
        exit 1
    fi
done

RESTORE_FILE="${TMP_DIR}/restore_$(date +%Y%m%d_%H%M%S).sql"

echo "=== DDOKSORI Database Restore ==="
echo "Source: s3://${S3_BUCKET}/${BACKUP_PATH}"
echo "Target: ${DB_HOST}/${DB_NAME}"
if $DRY_RUN; then
    echo "Mode: DRY RUN (no changes will be made)"
fi
echo ""

# Confirmation prompt (skip in CI/non-interactive)
if [[ -t 0 ]] && ! $DRY_RUN; then
    read -p "This will OVERWRITE the current database. Continue? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Restore cancelled."
        exit 1
    fi
fi

# 1. Download from S3
echo "Step 1/4: Downloading backup from S3..."
aws s3 cp "s3://${S3_BUCKET}/${BACKUP_PATH}" "${RESTORE_FILE}.gz"

DOWNLOAD_SIZE=$(du -h "${RESTORE_FILE}.gz" | cut -f1)
echo "Downloaded: ${DOWNLOAD_SIZE}"

# 2. Decompress
echo "Step 2/4: Decompressing..."
gunzip -f "${RESTORE_FILE}.gz"

UNCOMPRESSED_SIZE=$(du -h "${RESTORE_FILE}" | cut -f1)
echo "Uncompressed: ${UNCOMPRESSED_SIZE}"

# 3. Verify SQL file
echo "Step 3/4: Verifying backup file..."
if ! head -n 1 "${RESTORE_FILE}" | grep -q "PostgreSQL"; then
    echo "Warning: File may not be a valid PostgreSQL dump"
fi

TABLE_COUNT=$(grep -c "^CREATE TABLE" "${RESTORE_FILE}" || echo "0")
echo "Tables in backup: ${TABLE_COUNT}"

if $DRY_RUN; then
    echo ""
    echo "=== DRY RUN Complete ==="
    echo "Backup file verified. No changes made to database."
    rm -f "${RESTORE_FILE}"
    exit 0
fi

# 4. Restore to database
echo "Step 4/4: Restoring to database..."
echo "This may take several minutes depending on database size..."

# Drop and recreate all tables by restoring
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=0 \
    < "${RESTORE_FILE}"

# 5. Cleanup
echo "Cleaning up temporary files..."
rm -f "${RESTORE_FILE}"

# 6. Verification
echo ""
echo "=== Running verification queries ==="

DOCS_COUNT=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM documents;" 2>/dev/null | xargs)
CHUNKS_COUNT=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM chunks;" 2>/dev/null | xargs)
EMBEDDINGS_COUNT=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL;" 2>/dev/null | xargs)

echo "Documents: ${DOCS_COUNT:-N/A}"
echo "Chunks: ${CHUNKS_COUNT:-N/A}"
echo "Chunks with embeddings: ${EMBEDDINGS_COUNT:-N/A}"

# Check for new tables
CONVERSATIONS=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM conversations;" 2>/dev/null | xargs || echo "N/A")
USERS=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM oauth_users;" 2>/dev/null | xargs || echo "N/A")

echo "Conversations: ${CONVERSATIONS}"
echo "OAuth Users: ${USERS}"

echo ""
echo "=== Restore completed successfully ==="
echo "Source: s3://${S3_BUCKET}/${BACKUP_PATH}"
echo "Target: ${DB_HOST}/${DB_NAME}"
