#!/bin/bash
set -e

echo "💻 Starting Laptop Environment (RunPod GPU)"
echo "=============================================="

# Get the script's directory (to handle being called from anywhere)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Check if RunPod SSH tunnel is active
echo "🔍 Checking for RunPod SSH tunnel on port 18001..."
if ! curl -s http://127.0.0.1:18001/health > /dev/null 2>&1; then
    echo "❌ RunPod SSH tunnel not detected on port 18001"
    echo ""
    echo "Please establish SSH tunnel to RunPod first:"
    echo "  ssh -N -L 18001:127.0.0.1:8001 root@<runpod-pod-id>.pods.runpod.io"
    echo ""
    echo "In a separate terminal, keep the SSH tunnel running."
    echo "Then run this script again."
    exit 1
fi

# Verify RunPod embedding server is working
RUNPOD_HEALTH=$(curl -s http://127.0.0.1:18001/health)
RUNPOD_DEVICE=$(echo "$RUNPOD_HEALTH" | grep -o '"device":"[^"]*"' | cut -d'"' -f4)
echo "✅ RunPod embedding server detected!"
echo "   Device: $RUNPOD_DEVICE"
echo "   Health: $RUNPOD_HEALTH"

# Copy laptop environment config if .env doesn't exist or is different
if [ ! -f "backend/.env" ] || ! grep -q "# Laptop configuration" "backend/.env" 2>/dev/null; then
    if [ -f ".env.laptop" ]; then
        echo "📝 Using laptop environment configuration..."
        cp .env.laptop backend/.env
    else
        echo "❌ Error: .env.laptop not found"
        echo "Please create .env.laptop with REMOTE_EMBED_URL=http://127.0.0.1:18001"
        exit 1
    fi
fi

# Verify REMOTE_EMBED_URL is set
if ! grep -q "REMOTE_EMBED_URL=http://127.0.0.1:18001" "backend/.env"; then
    echo "⚠️  Warning: REMOTE_EMBED_URL not set to RunPod tunnel in backend/.env"
    echo "Backend may not connect to RunPod correctly."
fi

# Start Docker services (no local embedding server)
echo "🐳 Starting Docker services (db, backend, frontend)..."
docker-compose up -d db backend frontend

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend ready!"
        break
    fi
    sleep 1
done

echo ""
echo "=============================================="
echo "✅ Laptop environment ready!"
echo "=============================================="
echo "Services:"
echo "  - RunPod Embedding: http://127.0.0.1:18001/health (SSH tunnel)"
echo "  - Backend API:      http://localhost:8000"
echo "  - Frontend:         http://localhost:5173"
echo "  - Database:         localhost:5432"
echo ""
echo "Logs:"
echo "  - Backend: docker logs -f ddoksori_backend"
echo ""
echo "To stop:"
echo "  - Docker:     docker-compose down"
echo "  - SSH tunnel: Ctrl+C in the terminal running SSH"
echo "=============================================="
echo ""
echo "⚠️  Remember: Keep SSH tunnel running in a separate terminal!"
