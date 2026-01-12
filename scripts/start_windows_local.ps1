$ErrorActionPreference = "Stop"

# UTF-8 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
chcp 65001 > $null

Write-Host "=== Windows Local Development Environment ===" -ForegroundColor Cyan
Write-Host ""

# 프로젝트 루트로 이동
$ScriptDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# 1. Docker Desktop 실행 확인
Write-Host "[1/3] Checking Docker Desktop..." -ForegroundColor Yellow
try {
    docker info > $null 2>&1
    Write-Host "  OK: Docker is running" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Docker Desktop is not running" -ForegroundColor Red
    Write-Host "  Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# 2. Docker DB 시작
Write-Host "[2/3] Starting PostgreSQL container..." -ForegroundColor Yellow
docker-compose up -d db

# 3. DB 준비 대기
Write-Host "[3/3] Waiting for database to be ready..." -ForegroundColor Yellow
for ($i = 1; $i -le 30; $i++) {
    try {
        docker exec ddoksori_db pg_isready -U postgres > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK: Database is ready" -ForegroundColor Green
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
    if ($i -eq 30) {
        Write-Host "  WARNING: Database may not be ready yet" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Restore database (if first time):" -ForegroundColor Gray
Write-Host "     .\scripts\restore_db_windows.ps1" -ForegroundColor White
Write-Host ""
Write-Host "  2. Start backend (new terminal):" -ForegroundColor Gray
Write-Host "     `$env:PYTHONIOENCODING = 'utf-8'" -ForegroundColor White
Write-Host "     cd backend" -ForegroundColor White
Write-Host "     uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" -ForegroundColor White
Write-Host ""
Write-Host "  3. Start frontend (new terminal):" -ForegroundColor Gray
Write-Host "     cd frontend" -ForegroundColor White
Write-Host "     npm run dev" -ForegroundColor White
Write-Host ""
