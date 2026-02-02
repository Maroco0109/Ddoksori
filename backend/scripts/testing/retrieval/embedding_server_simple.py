"""
Simple Embedding Server using OpenAI API
임베딩 테스트를 위한 간단한 서버
"""

import os
from typing import List

from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

app = FastAPI()

# OpenAI 클라이언트
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class EmbedRequest(BaseModel):
    texts: List[str]


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]


@app.post("/embed")
async def embed(request: EmbedRequest) -> EmbedResponse:
    """임베딩 생성"""
    try:
        response = client.embeddings.create(
            model="text-embedding-3-large",
            input=request.texts,
            dimensions=1024,  # KURE-v1과 호환을 위해 1024 차원 사용
        )

        embeddings = [data.embedding for data in response.data]
        return EmbedResponse(embeddings=embeddings)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
