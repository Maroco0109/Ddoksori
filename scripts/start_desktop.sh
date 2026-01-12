#!/bin/bash
set -e

echo "🖥️  Starting Desktop Environment (Local GPU)"
echo "=============================================="

# Get the script's directory (to handle being called from anywhere)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Check if conda environment exists
if ! conda env list | grep -q "^dsr "; then
    echo "❌ Error: Conda environment 'dsr' not found"
    echo "Please create the environment first: conda create -n dsr python=3.11"
    exit 1
fi

# Check if GPU is available
if ! nvidia-smi &> /dev/null; then
    echo "⚠️  Warning: nvidia-smi not found or GPU not available"
    echo "Embedding server will run on CPU (slower performance)"
fi

# Check if embedding server is already running
if lsof -Pi :8001 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Port 8001 already in use (embedding server may be running)"
    echo "Skipping embedding server startup..."
else
    # Start embedding server in background
    echo "🚀 Starting embedding server on host with GPU..."
    nohup conda run -n dsr python backend/embedding_server.py > /tmp/embedding_server.log 2>&1 &
    EMBED_PID=$!
    echo "   PID: $EMBED_PID"
    echo "   Logs: /tmp/embedding_server.log"

    # Wait for embedding server to be ready
    echo "⏳ Waiting for embedding server to initialize (max 60s)..."
    for i in {1..60}; do
        if curl -s http://localhost:8001/health > /dev/null 2>&1; then
            echo "✅ Embedding server ready!"
            break
        fi
        sleep 1
        if [ $i -eq 60 ]; then
            echo "❌ Embedding server failed to start. Check logs: /tmp/embedding_server.log"
            exit 1
        fi
    done

    # Show GPU status
    if nvidia-smi &> /dev/null; then
        DEVICE=$(curl -s http://localhost:8001/health | grep -o '"device":"[^"]*"' | cut -d'"' -f4)
        echo "   Device: $DEVICE"
    fi
fi

# Copy desktop environment config if .env doesn't exist or is different
if [ ! -f "backend/.env" ] || ! grep -q "# Desktop configuration" "backend/.env" 2>/dev/null; then
    if [ -f ".env.desktop" ]; then
        echo "📝 Using desktop environment configuration..."
        cp .env.desktop backend/.env
    else
        echo "⚠️  Warning: .env.desktop not found, using existing backend/.env"
    fi
fi

# Start Docker services
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
echo "✅ Desktop environment ready!"
echo "=============================================="
echo "Services:"
echo "  - Embedding Server: http://localhost:8001/health"
echo "  - Backend API:      http://localhost:8000"
echo "  - Frontend:         http://localhost:5173"
echo "  - Database:         localhost:5432"
echo ""
echo "Logs:"
echo "  - Embedding: tail -f /tmp/embedding_server.log"
echo "  - Backend:   docker logs -f ddoksori_backend"
echo ""
echo "To stop:"
echo "  - Docker:    docker-compose down"
echo "  - Embedding: pkill -f embedding_server.py"
echo "=============================================="
