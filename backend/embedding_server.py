import os
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from contextlib import asynccontextmanager

from typing import List, Optional, Union

# Global model variable
model = None

class EmbeddingRequest(BaseModel):
    text: Optional[str] = None
    texts: Optional[List[str]] = None

class EmbeddingResponse(BaseModel):
    embedding: Optional[List[float]] = None
    embeddings: Optional[List[List[float]]] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    device = "cuda" if torch.cuda.is_available() else "cpu"

    print("=" * 60)
    print("🚀 Initializing Embedding Server")
    print("=" * 60)

    # GPU Diagnostics
    print(f"📊 Device: {device.upper()}")

    if device == "cuda":
        print(f"   CUDA Available: True")
        print(f"   CUDA Version: {torch.version.cuda}")
        print(f"   PyTorch Version: {torch.__version__}")
        print(f"   GPU Count: {torch.cuda.device_count()}")

        for i in range(torch.cuda.device_count()):
            gpu_name = torch.cuda.get_device_name(i)
            gpu_memory = torch.cuda.get_device_properties(i).total_memory / 1024**3  # GB
            print(f"   GPU {i}: {gpu_name}")
            print(f"   Total VRAM: {gpu_memory:.2f} GB")
    else:
        print(f"   CUDA Available: False")
        print(f"   ⚠️  Running on CPU - Performance will be slower")
        if not torch.cuda.is_available():
            print(f"   Reason: CUDA not available in PyTorch")
            print(f"   To enable GPU: pip install torch --index-url https://download.pytorch.org/whl/cu121")

    # Model configuration
    model_name = os.getenv("EMBEDDING_MODEL_NAME", "nlpai-lab/KURE-v1")
    print(f"\n📦 Loading model: {model_name}")

    try:
        import time
        start_time = time.time()
        model = SentenceTransformer(model_name, device=device)
        load_time = time.time() - start_time

        print(f"✅ Model {model_name} loaded successfully!")
        print(f"   Load time: {load_time:.2f}s")
        print(f"   Device: {device}")

        # Show embedding dimension
        test_embedding = model.encode("test", convert_to_numpy=True)
        print(f"   Embedding dimension: {len(test_embedding)}")

    except Exception as e:
        print(f"⚠️  Failed to load {model_name}: {e}")
        fallback_model = "jhgan/ko-sroberta-multitask"
        print(f"🔄 Falling back to {fallback_model}...")
        try:
            model = SentenceTransformer(fallback_model, device=device)
            print(f"✅ Fallback model {fallback_model} loaded successfully on {device}")
        except Exception as e2:
            print(f"❌ Failed to load fallback model: {e2}")
            # Do not raise here, allow server to start but fail requests
            pass

    print("=" * 60)
    print("✅ Embedding Server Ready")
    print("=" * 60)
    print(f"   Health endpoint: http://localhost:8001/health")
    print(f"   Embed endpoint:  http://localhost:8001/embed")
    print("=" * 60)

    yield
    print("\n🛑 Shutting down model...")

app = FastAPI(title="Ddoksori Embedding API", lifespan=lifespan)

@app.post("/embed", response_model=EmbeddingResponse)
async def create_embedding(request: EmbeddingRequest):
    global model
    if model is None:
        raise HTTPException(status_code=503, detail="Model not initialized")

    try:
        import time
        start_time = time.time()

        if request.texts:
            # Batch mode
            batch_size = len(request.texts)
            embeddings = model.encode(request.texts, convert_to_numpy=True).tolist()
            elapsed = time.time() - start_time
            print(f"📊 Batch embedding: {batch_size} texts in {elapsed:.3f}s ({elapsed/batch_size*1000:.1f}ms per text)")
            return {"embeddings": embeddings}
        elif request.text:
            # Single mode
            embedding = model.encode(request.text, convert_to_numpy=True).tolist()
            elapsed = time.time() - start_time
            print(f"📊 Single embedding: {elapsed*1000:.1f}ms")
            return {"embedding": embedding}
        else:
            raise HTTPException(status_code=422, detail="Either 'text' or 'texts' field is required")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")

@app.get("/health")
async def health():
    if model is None:
        raise HTTPException(status_code=503, detail="Model not initialized")
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    # model.modules() is a generator
    model_name_or_path = "unknown"
    try:
        if hasattr(model, 'modules'):
            modules = list(model.modules())
            if modules and hasattr(modules[0], 'auto_model'):
                 model_name_or_path = modules[0].auto_model.config.name_or_path
    except:
        pass
        
    return {
        "status": "healthy", 
        "device": device,
        "model": model_name_or_path
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
