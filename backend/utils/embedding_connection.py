import os
import subprocess
import sys
import tempfile
import time
from typing import Optional

import requests

# Configuration - KURE-v1 (Default Dense Embedding)
# RunPod uses 9000-range ports to avoid conflicts with Jupyter/other services
REMOTE_EMBED_URL = os.getenv("REMOTE_EMBED_URL")
LOCAL_PORT = int(os.getenv("KURE_LOCAL_PORT", 9001))
LOCAL_EMBED_URL = f"http://localhost:{LOCAL_PORT}"

# Embedding Model Selection
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "kure-v1")

# Docker/CI safety: avoid blocking startup by auto-starting a local embedding server.
DISABLE_LOCAL_EMBED_AUTO_START = (
    os.getenv("DISABLE_LOCAL_EMBED_AUTO_START", "false").lower() == "true"
)

# RRF Weight Parameters (for A/B testing)
RRF_WEIGHT_DENSE = float(os.getenv("RRF_WEIGHT_DENSE", "1.0"))
RRF_WEIGHT_LEXICAL = float(os.getenv("RRF_WEIGHT_LEXICAL", "1.0"))


def check_url(url: str, timeout: int = 2) -> bool:
    """Checks if the health endpoint of the given URL returns 200 OK."""
    try:
        response = requests.get(f"{url}/health", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def start_local_server():
    """Starts the local embedding server as a background process."""
    print(f"🚀 Starting local embedding server on port {LOCAL_PORT}...")

    # Path to python interpreter in current conda env
    python_executable = sys.executable
    # Script is at backend/app/agents/retrieval/services/embedding_server.py
    # This file is backend/utils/embedding_connection.py
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(
        base_dir, "app", "agents", "retrieval", "services", "embedding_server.py"
    )

    if not os.path.exists(script_path):
        print(f"❌ Error: Embedding server script not found at {script_path}")
        return False

    # Use cross-platform temp directory (Windows: %TEMP%, Linux/Mac: /tmp)
    log_path = os.path.join(tempfile.gettempdir(), "embedding_server.log")
    log_file = open(log_path, "w")

    # Run uvicorn server
    subprocess.Popen(
        [python_executable, script_path],
        stdout=log_file,
        stderr=log_file,
        env={**os.environ, "PORT": str(LOCAL_PORT)},
    )

    # Wait for startup (up to 60 seconds - model loading takes time)
    print("⏳ Waiting for model to load...", end="", flush=True)
    for _ in range(60):
        if check_url(LOCAL_EMBED_URL, timeout=1):
            print("\n✅ Local embedding server started successfully!")
            return True
        time.sleep(1)
        print(".", end="", flush=True)

    print(f"\n❌ Failed to start local embedding server. Check {log_path}")
    return False


def get_embedding_api_url() -> str:
    """
    Determines the best available embedding API URL using Adaptive Strategy.
    Order: Remote -> Local Running -> Start Local
    """
    # 1. Check Remote
    if REMOTE_EMBED_URL:
        # Strip trailing slash if present
        base_remote = REMOTE_EMBED_URL.rstrip("/")
        if check_url(base_remote):
            print(f"🔗 Using REMOTE embedding server at {base_remote}")
            return f"{base_remote}/embed"
        else:
            print(f"⚠️ Remote server at {base_remote} is not reachable.")
            if DISABLE_LOCAL_EMBED_AUTO_START:
                # In containerized environments, remote may still be warming up.
                # Return remote URL without blocking startup.
                return f"{base_remote}/embed"

    # 2. Check if Local is already running
    if check_url(LOCAL_EMBED_URL):
        print(f"🔗 Using existing LOCAL embedding server at {LOCAL_EMBED_URL}")
        return f"{LOCAL_EMBED_URL}/embed"

    # 3. Start Local Server
    if DISABLE_LOCAL_EMBED_AUTO_START:
        print(
            "🛑 DISABLE_LOCAL_EMBED_AUTO_START=true: skipping local embedding server auto-start"
        )
        return f"{LOCAL_EMBED_URL}/embed"
    if start_local_server():
        return f"{LOCAL_EMBED_URL}/embed"

    # 4. Fallback (Fail)
    print(
        "Could not connect to any embedding server. Dense search will be unavailable."
    )
    return f"{LOCAL_EMBED_URL}/embed"  # Return default, will fail connection later


def get_embedding_config() -> dict:
    """
    Returns the current embedding configuration.
    Useful for debugging and status reporting.
    """
    return {
        "embedding_model": EMBEDDING_MODEL,
        "kure_url": get_embedding_api_url() if EMBEDDING_MODEL == "kure-v1" else None,
        "rrf_weights": {
            "dense": RRF_WEIGHT_DENSE,
            "lexical": RRF_WEIGHT_LEXICAL,
        },
    }


def get_active_embedding_url() -> str:
    """
    Returns the embedding URL based on the active embedding model.
    """
    return get_embedding_api_url()
