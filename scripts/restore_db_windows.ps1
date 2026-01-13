$ErrorActionPreference = "Stop"

# UTF-8 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > $null

Write-Host "=== Database Restore (Windows) ===" -ForegroundColor Cyan
Write-Host ""

# 프로젝트 루트로 이동
$ScriptDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# 1. backup.sql 존재 확인
$BackupFile = Join-Path $ProjectRoot "backup.sql"
if (!(Test-Path $BackupFile)) {
    Write-Host "ERROR: backup.sql not found at $BackupFile" -ForegroundColor Red
    Write-Host "Please place backup.sql in the project root directory." -ForegroundColor Yellow
    exit 1
}
Write-Host "[1/4] Found backup.sql" -ForegroundColor Green

# 2. 컨테이너 실행 확인
Write-Host "[2/4] Checking database container..." -ForegroundColor Yellow
try {
    docker exec ddoksori_db pg_isready -U postgres > $null 2>&1
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Host "  OK: Container is running" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: ddoksori_db container is not running" -ForegroundColor Red
    Write-Host "  Run '.\scripts\start_windows_local.ps1' first." -ForegroundColor Yellow
    exit 1
}

# 3. backup.sql을 컨테이너로 복사
Write-Host "[3/4] Copying backup.sql to container..." -ForegroundColor Yellow
docker cp $BackupFile ddoksori_db:/tmp/backup.sql
Write-Host "  OK: File copied" -ForegroundColor Green

# 4. psql로 복원 실행
Write-Host "[4/4] Restoring database (this may take a while)..." -ForegroundColor Yellow
# Use ON_ERROR_STOP=off to continue despite non-fatal DROP errors (e.g., DROP INDEX for non-existent indexes on fresh DB)
docker exec ddoksori_db psql -U postgres -d ddoksori -v ON_ERROR_STOP=off -f /tmp/backup.sql 2>&1 | Out-Null

# 5. 결과 검증
Write-Host ""
Write-Host "=== Verifying restoration ===" -ForegroundColor Cyan
$docCount = docker exec ddoksori_db psql -U postgres -d ddoksori -t -c "SELECT COUNT(*) FROM documents;"
$chunkCount = docker exec ddoksori_db psql -U postgres -d ddoksori -t -c "SELECT COUNT(*) FROM chunks;"

Write-Host "  Documents: $($docCount.Trim())" -ForegroundColor White
Write-Host "  Chunks: $($chunkCount.Trim())" -ForegroundColor White

# 6. 임시 파일 정리
docker exec ddoksori_db rm /tmp/backup.sql

Write-Host ""
Write-Host "=== Restore Complete ===" -ForegroundColor Green
