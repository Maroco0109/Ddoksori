import os
import requests
import subprocess
import time
import sys

# Configuration
REMOTE_EMBED_URL = os.getenv("REMOTE_EMBED_URL")
LOCAL_PORT = 8001
LOCAL_EMBED_URL = f"http://localhost:{LOCAL_PORT}"

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
    # Assume script is at backend/embedding_server.py
    # This file is backend/utils/embedding_connection.py
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(base_dir, "embedding_server.py")
    
    if not os.path.exists(script_path):
        print(f"❌ Error: Embedding server script not found at {script_path}")
        return False

    log_file = open("/tmp/embedding_server.log", "w")
    
    # Run uvicorn server
    subprocess.Popen(
        [python_executable, script_path],
        stdout=log_file,
        stderr=log_file,
        env={**os.environ, "PORT": str(LOCAL_PORT)}
    )
    
    # Wait for startup (up to 60 seconds - model loading takes time)
    print("⏳ Waiting for model to load...", end="", flush=True)
    for _ in range(60):
        if check_url(LOCAL_EMBED_URL, timeout=1):
            print("\n✅ Local embedding server started successfully!")
            return True
        time.sleep(1)
        print(".", end="", flush=True)
        
    print("\n❌ Failed to start local embedding server. Check /tmp/embedding_server.log")
    return False

def get_embedding_api_url() -> str:
    """
    Determines the best available embedding API URL using Adaptive Strategy.
    Order: Remote -> Local Running -> Start Local
    """
    # 1. Check Remote
    if REMOTE_EMBED_URL:
        # Strip trailing slash if present
        base_remote = REMOTE_EMBED_URL.rstrip('/')
        if check_url(base_remote):
            print(f"🔗 Using REMOTE embedding server at {base_remote}")
            return f"{base_remote}/embed"
        else:
            print(f"⚠️ Remote server at {base_remote} is not reachable.")
    
    # 2. Check if Local is already running
    if check_url(LOCAL_EMBED_URL):
        print(f"🔗 Using existing LOCAL embedding server at {LOCAL_EMBED_URL}")
        return f"{LOCAL_EMBED_URL}/embed"
        
    # 3. Start Local Server
    if start_local_server():
        return f"{LOCAL_EMBED_URL}/embed"
        
    # 4. Fallback (Fail)
    print("⚠️ Could not connect to any embedding server. Dense search will be unavailable.")
    return f"{LOCAL_EMBED_URL}/embed" # Return default, will fail connection later
