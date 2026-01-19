"""
BGE-M3 Embedding Server for Ddoksori

Provides Dense (1024D) + Sparse embeddings using BAAI/bge-m3 model.
Port: 8003 (default)

Features:
- Dense embedding: 1024 dimensions
- Sparse embedding: JSONB format {token_id: weight}
- Batch processing support
- GPU acceleration with CPU fallback
"""

import os
import time
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

# Global model variable
model = None


class BGEM3Request(BaseModel):
    """Request model for BGE-M3 embedding generation."""
    text: Optional[str] = None
    texts: Optional[List[str]] = None
    return_dense: bool = True
    return_sparse: bool = True


class BGEM3Response(BaseModel):
    """Response model for BGE-M3 embeddings."""
    # Single text response
    dense_embedding: Optional[List[float]] = None
    sparse_embedding: Optional[Dict[str, float]] = None
    # Batch response
    dense_embeddings: Optional[List[List[float]]] = None
    sparse_embeddings: Optional[List[Dict[str, float]]] = None


def convert_sparse_to_dict(sparse_weights: Dict[int, float]) -> Dict[str, float]:
    """
    Convert sparse weights from {int: float} to {str: float} for JSON serialization.
    Filters out zero or near-zero weights for storage efficiency.
    """
    return {
        str(token_id): float(weight)
        for token_id, weight in sparse_weights.items()
        if abs(weight) > 1e-6
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - loads BGE-M3 model on startup."""
    global model
    device = "cuda" if torch.cuda.is_available() else "cpu"

    print("=" * 60)
    print("BGE-M3 Embedding Server Initializing")
    print("=" * 60)

    # GPU Diagnostics
    print(f"Device: {device.upper()}")

    if device == "cuda":
        print(f"   CUDA Available: True")
        print(f"   CUDA Version: {torch.version.cuda}")
        print(f"   PyTorch Version: {torch.__version__}")
        print(f"   GPU Count: {torch.cuda.device_count()}")

        for i in range(torch.cuda.device_count()):
            gpu_name = torch.cuda.get_device_name(i)
            gpu_memory = torch.cuda.get_device_properties(i).total_memory / 1024**3
            print(f"   GPU {i}: {gpu_name}")
            print(f"   Total VRAM: {gpu_memory:.2f} GB")
    else:
        print(f"   CUDA Available: False")
        print(f"   Running on CPU - Performance will be slower")

    # Load BGE-M3 model
    model_name = "BAAI/bge-m3"
    print(f"\nLoading model: {model_name}")

    try:
        start_time = time.time()

        from FlagEmbedding import BGEM3FlagModel

        # Use FP16 on GPU for memory efficiency
        use_fp16 = device == "cuda"

        model = BGEM3FlagModel(
            model_name,
            use_fp16=use_fp16,
            device=device
        )

        load_time = time.time() - start_time

        print(f"Model {model_name} loaded successfully!")
        print(f"   Load time: {load_time:.2f}s")
        print(f"   Device: {device}")
        print(f"   FP16: {use_fp16}")

        # Test embedding to verify dimensions
        test_result = model.encode(
            ["test"],
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False
        )
        dense_dim = len(test_result['dense_vecs'][0])
        sparse_size = len(test_result['lexical_weights'][0])
        print(f"   Dense dimension: {dense_dim}")
        print(f"   Sparse tokens (test): {sparse_size}")

    except ImportError as e:
        print(f"Failed to import FlagEmbedding: {e}")
        print("Install with: pip install FlagEmbedding")
        raise
    except Exception as e:
        print(f"Failed to load BGE-M3: {e}")
        raise

    print("=" * 60)
    print("BGE-M3 Server Ready")
    print("=" * 60)
    print(f"   Health endpoint: http://localhost:8003/health")
    print(f"   Embed endpoint:  http://localhost:8003/embed")
    print("=" * 60)

    yield
    print("\nShutting down BGE-M3 server...")


app = FastAPI(
    title="Ddoksori BGE-M3 Embedding API",
    description="Dense + Sparse embedding generation using BAAI/bge-m3",
    version="1.0.0",
    lifespan=lifespan
)


@app.post("/embed", response_model=BGEM3Response)
async def create_embedding(request: BGEM3Request):
    """
    Generate BGE-M3 embeddings for text(s).

    - **text**: Single text to embed
    - **texts**: List of texts for batch embedding
    - **return_dense**: Include dense embeddings (default: True)
    - **return_sparse**: Include sparse embeddings (default: True)
    """
    global model
    if model is None:
        raise HTTPException(status_code=503, detail="Model not initialized")

    try:
        start_time = time.time()
        response = {}

        if request.texts:
            # Batch mode
            batch_size = len(request.texts)

            result = model.encode(
                request.texts,
                return_dense=request.return_dense,
                return_sparse=request.return_sparse,
                return_colbert_vecs=False
            )

            if request.return_dense:
                response["dense_embeddings"] = result['dense_vecs'].tolist()

            if request.return_sparse:
                response["sparse_embeddings"] = [
                    convert_sparse_to_dict(sparse)
                    for sparse in result['lexical_weights']
                ]

            elapsed = time.time() - start_time
            print(f"Batch embedding: {batch_size} texts in {elapsed:.3f}s "
                  f"({elapsed/batch_size*1000:.1f}ms per text)")

        elif request.text:
            # Single mode
            result = model.encode(
                [request.text],
                return_dense=request.return_dense,
                return_sparse=request.return_sparse,
                return_colbert_vecs=False
            )

            if request.return_dense:
                response["dense_embedding"] = result['dense_vecs'][0].tolist()

            if request.return_sparse:
                response["sparse_embedding"] = convert_sparse_to_dict(
                    result['lexical_weights'][0]
                )

            elapsed = time.time() - start_time
            print(f"Single embedding: {elapsed*1000:.1f}ms")

        else:
            raise HTTPException(
                status_code=422,
                detail="Either 'text' or 'texts' field is required"
            )

        return response

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Embedding generation failed: {str(e)}"
        )


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not initialized")

    device = "cuda" if torch.cuda.is_available() else "cpu"

    return {
        "status": "healthy",
        "model": "BAAI/bge-m3",
        "device": device,
        "dense_dim": 1024,
        "sparse_vocab_size": 250002,
        "capabilities": ["dense", "sparse"]
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "Ddoksori BGE-M3 Embedding API",
        "version": "1.0.0",
        "endpoints": {
            "POST /embed": "Generate embeddings",
            "GET /health": "Health check"
        }
    }


if __name__ == "__main__":
    port = int(os.getenv("BGE_M3_PORT", 8003))
    uvicorn.run(app, host="0.0.0.0", port=port)
