"""
똑소리 프로젝트 - FastAPI 메인 애플리케이션

한국 소비자 분쟁 조정 RAG 챗봇 API 서버입니다.

API 라우터:
    - /: 서버 정보
    - /health: 헬스체크
    - /search: 벡터 검색
    - /chat: 챗봇 응답 (일반)
    - /chat/stream: 챗봇 응답 (SSE 스트리밍)
    - /case/{uid}: 사례 조회
    - /metrics/*: 에이전트 메트릭스
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Langsmith 트레이싱 로그
if os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true":
    logger.info(
        f"[Langsmith] Tracing enabled - Project: {os.getenv('LANGCHAIN_PROJECT', 'default')}"
    )

# 임베딩 API URL 설정
from utils.embedding_connection import get_embedding_api_url

embed_api_url = get_embedding_api_url()
os.environ["EMBED_API_URL"] = embed_api_url

# API 라우터 import
from app.api import (
    admin_router,
    auth_router,
    case_router,
    chat_router,
    health_router,
    metrics_router,
    search_router,
    users_router,
)

# FastAPI 앱 생성
app = FastAPI(
    title="똑소리 API",
    version="0.4.2",  # Refactored with modular routers
    description="한국 소비자 분쟁 조정 RAG 챗봇 API",
)

# Prometheus 모니터링
Instrumentator().instrument(app).expose(app)

# CORS 설정
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(search_router)
app.include_router(case_router)
app.include_router(metrics_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(users_router)


# 시작 로그
@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 로그 및 서비스 시작"""
    retrieval_mode = os.getenv("RETRIEVAL_MODE", "dense")
    logger.info(f"[Startup] 똑소리 API 서버 시작")
    logger.info(f"[Startup] Retrieval Mode: {retrieval_mode}")
    logger.info(f"[Startup] Embedding API: {embed_api_url}")

    # ConversationCleanupService 시작
    try:
        from app.supervisor.persistence.cleanup import get_cleanup_service

        cleanup_service = get_cleanup_service()
        await cleanup_service.start()
        logger.info("[Startup] ConversationCleanupService 시작 완료")
    except Exception as e:
        logger.warning(f"[Startup] ConversationCleanupService 시작 실패: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """애플리케이션 종료 시 정리"""
    logger.info("[Shutdown] 똑소리 API 서버 종료 중...")

    # ConversationCleanupService 종료
    try:
        from app.supervisor.persistence.cleanup import get_cleanup_service

        cleanup_service = get_cleanup_service()
        await cleanup_service.stop()
        logger.info("[Shutdown] ConversationCleanupService 종료 완료")
    except Exception as e:
        logger.warning(f"[Shutdown] ConversationCleanupService 종료 실패: {e}")


from app.api.dependencies import (
    get_db_config,
    get_retrieval_mode,
    get_retriever,
)

# 하위 호환성을 위한 export
# 기존에 main.py에서 직접 import하던 코드가 있을 수 있음
from app.api.models import (
    AgencyRecommendation,
    CaseReference,
    ChatRequest,
    ChatResponse,
    CriteriaReference,
    LawReference,
    NodeTiming,
    SearchRequest,
    SimilarCases,
)

__all__ = [
    "app",
    # 모델
    "ChatRequest",
    "ChatResponse",
    "SearchRequest",
    "AgencyRecommendation",
    "CaseReference",
    "LawReference",
    "CriteriaReference",
    "SimilarCases",
    "NodeTiming",
    # 의존성
    "get_retriever",
    "get_db_config",
    "get_retrieval_mode",
]
