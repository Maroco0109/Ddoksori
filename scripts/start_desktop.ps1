$ErrorActionPreference = "Stop"

Write-Host "🖥️  Starting Desktop Environment (Local GPU)"
Write-Host "=============================================="

# Get the script's directory and project root
$ScriptDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $ScriptDir
$LogFile = Join-Path $env:TEMP "embedding_server.log"

# Change to project root
Set-Location $ProjectRoot

# Check if conda environment exists
$CondaEnvs = conda env list
if (!($CondaEnvs -match "^dsr ")) {
    Write-Host "❌ Error: Conda environment 'dsr' not found"
    Write-Host "Please create the environment first: conda create -n dsr python=3.11"
    exit 1
}

# Check if GPU is available
try {
    nvidia-smi | Out-Null
} catch {
    Write-Host "⚠️  Warning: nvidia-smi not found or GPU not available"
    Write-Host "Embedding server will run on CPU (slower performance)"
}

# Check if embedding server is already running
$PortActive = $false
try {
    $Connection = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
    if ($Connection -and $Connection.State -eq 'Listen') {
        $PortActive = $true
    }
} catch {
    # Port not active
}

if ($PortActive) {
    Write-Host "⚠️  Port 8001 already in use (embedding server may be running)"
    Write-Host "Skipping embedding server startup..."
} else {
    # Start embedding server in background
    Write-Host "🚀 Starting embedding server on host with GPU..."
    
    # We use Start-Process to run in background. 
    # Note: 'conda' might need to be in PATH. If using Anaconda Prompt, it works.
    $Process = Start-Process -FilePath "conda" `
        -ArgumentList "run", "-n", "dsr", "python", "backend/embedding_server.py" `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError $LogFile `
        -WindowStyle Hidden `
        -PassThru
    
    $EmbedPid = $Process.Id
    Write-Host "   PID: $EmbedPid"
    Write-Host "   Logs: $LogFile"

    # Wait for embedding server to be ready
    Write-Host "⏳ Waiting for embedding server to initialize (max 60s)..."
    for ($i = 1; $i -le 60; $i++) {
        try {
            Invoke-RestMethod -Uri "http://localhost:8001/health" -Method Get -ErrorAction Stop | Out-Null
            Write-Host "✅ Embedding server ready!"
            break
        } catch {
            Start-Sleep -Seconds 1
        }
        
        if ($i -eq 60) {
            Write-Host "❌ Embedding server failed to start. Check logs: $LogFile"
            exit 1
        }
    }

    # Show GPU status
    try {
        $Health = Invoke-RestMethod -Uri "http://localhost:8001/health" -Method Get
        Write-Host "   Device: $($Health.device)"
    } catch {}
}

# Copy desktop environment config if .env doesn't exist or is different
if (!(Test-Path "backend/.env") -or !(Select-String -Path "backend/.env" -Pattern "# Desktop configuration" -Quiet)) {
    if (Test-Path ".env.desktop") {
        Write-Host "📝 Using desktop environment configuration..."
        Copy-Item ".env.desktop" "backend/.env" -Force
    } else {
        Write-Host "⚠️  Warning: .env.desktop not found, using existing backend/.env"
    }
}

# Start Docker services
Write-Host "🐳 Starting Docker services (db, backend, frontend)..."
docker-compose -f docker-compose.windows.yml up -d db backend frontend

# Wait for backend to be ready
Write-Host "⏳ Waiting for backend to be ready..."
for ($i = 1; $i -le 30; $i++) {
    try {
        Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -ErrorAction Stop | Out-Null
        Write-Host "✅ Backend ready!"
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}

Write-Host ""
Write-Host "=============================================="
Write-Host "✅ Desktop environment ready!"
Write-Host "=============================================="
Write-Host "Services:"
Write-Host "  - Embedding Server: http://localhost:8001/health"
Write-Host "  - Backend API:      http://localhost:8000"
Write-Host "  - Frontend:         http://localhost:5173"
Write-Host "  - Database:         localhost:5432"
Write-Host ""
Write-Host "Logs:"
Write-Host "  - Embedding: Get-Content -Wait $LogFile"
Write-Host "  - Backend:   docker logs -f ddoksori_backend"
Write-Host ""
Write-Host "To stop:"
Write-Host "  - Docker:    docker-compose down"
Write-Host "  - Embedding: Stop-Process -Id $EmbedPid (if captured) or taskkill /F /IM python.exe"
Write-Host "=============================================="
