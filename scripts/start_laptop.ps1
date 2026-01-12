$ErrorActionPreference = "Stop"

Write-Host "💻 Starting Laptop Environment (RunPod GPU)"
Write-Host "=============================================="

# Get the script's directory and project root
$ScriptDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $ScriptDir

# Change to project root
Set-Location $ProjectRoot

# Check if RunPod SSH tunnel is active
Write-Host "🔍 Checking for RunPod SSH tunnel on port 18001..."
try {
    $Response = Invoke-RestMethod -Uri "http://127.0.0.1:18001/health" -Method Get -ErrorAction Stop
} catch {
    Write-Host "❌ RunPod SSH tunnel not detected on port 18001"
    Write-Host ""
    Write-Host "Please establish SSH tunnel to RunPod first:"
    Write-Host "  ssh -N -L 18001:127.0.0.1:8001 root@<runpod-pod-id>.pods.runpod.io"
    Write-Host ""
    Write-Host "In a separate terminal, keep the SSH tunnel running."
    Write-Host "Then run this script again."
    exit 1
}

# Verify RunPod embedding server is working
$RunPodDevice = $Response.device
Write-Host "✅ RunPod embedding server detected!"
Write-Host "   Device: $RunPodDevice"

# Copy laptop environment config if .env doesn't exist or is different
if (!(Test-Path "backend/.env") -or !(Select-String -Path "backend/.env" -Pattern "# Laptop configuration" -Quiet)) {
    if (Test-Path ".env.laptop") {
        Write-Host "📝 Using laptop environment configuration..."
        Copy-Item ".env.laptop" "backend/.env" -Force
    } else {
        Write-Host "❌ Error: .env.laptop not found"
        Write-Host "Please create .env.laptop with REMOTE_EMBED_URL=http://127.0.0.1:18001"
        exit 1
    }
}

# Verify REMOTE_EMBED_URL is set
if (!(Select-String -Path "backend/.env" -Pattern "REMOTE_EMBED_URL=http://127.0.0.1:18001" -Quiet)) {
    Write-Host "⚠️  Warning: REMOTE_EMBED_URL not set to RunPod tunnel in backend/.env"
    Write-Host "Backend may not connect to RunPod correctly."
}

# Start Docker services (no local embedding server)
Write-Host "🐳 Starting Docker services (db, backend, frontend)..."
docker-compose -f docker-compose.windows.yml up -d db backend frontend

# Wait for backend to be ready
Write-Host "⏳ Waiting for backend to be ready..."
for ($i = 1; $i -le 30; $i++) {
    try {
        $BackendResponse = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -ErrorAction Stop
        Write-Host "✅ Backend ready!"
        break
    } catch {
        Start-Sleep -Seconds 1
    }
    
    if ($i -eq 30) {
        Write-Host "⚠️  Backend start timed out or is still starting..."
    }
}

Write-Host ""
Write-Host "=============================================="
Write-Host "✅ Laptop environment ready!"
Write-Host "=============================================="
Write-Host "Services:"
Write-Host "  - RunPod Embedding: http://127.0.0.1:18001/health (SSH tunnel)"
Write-Host "  - Backend API:      http://localhost:8000"
Write-Host "  - Frontend:         http://localhost:5173"
Write-Host "  - Database:         localhost:5432"
Write-Host ""
Write-Host "Logs:"
Write-Host "  - Backend: docker logs -f ddoksori_backend"
Write-Host ""
Write-Host "To stop:"
Write-Host "  - Docker:     docker-compose down"
Write-Host "  - SSH tunnel: Ctrl+C in the terminal running SSH"
Write-Host "=============================================="
Write-Host ""
Write-Host "⚠️  Remember: Keep SSH tunnel running in a separate terminal!"
