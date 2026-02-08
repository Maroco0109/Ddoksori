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
from slowapi.errors import RateLimitExceeded

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# PII 필터를 모든 로그 핸들러에 연결 (SEC-04)
from app.common.logging.pii_redactor import PIIRedactingFilter

for handler in logging.root.handlers:
    handler.addFilter(PIIRedactingFilter())

logger = logging.getLogger(__name__)

# Langsmith 트레이싱 로그
if os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true":
    logger.info(
        f"[Langsmith] Tracing enabled - Project: {os.getenv('LANGCHAIN_PROJECT', 'default')}"
    )

# API 라우터 import
from app.api import (
    admin_router,
    auth_router,
    board_router,
    case_router,
    chat_router,
    health_router,
    metrics_router,
    search_router,
    users_router,
)

# FastAPI 앱 생성 (SEC-20: 프로덕션에서 Swagger 비활성화)
_is_debug = os.getenv("DEBUG", "false").lower() == "true"
app = FastAPI(
    title="똑소리 API",
    version="0.4.2",  # Refactored with modular routers
    description="한국 소비자 분쟁 조정 RAG 챗봇 API",
    docs_url="/docs" if _is_debug else None,
    redoc_url="/redoc" if _is_debug else None,
    openapi_url="/openapi.json" if _is_debug else None,
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)

# 보안 헤더 미들웨어 (SEC-07)
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)

# Rate Limiting 설정 (SEC-04)
from app.middleware.rate_limiter import limiter, rate_limit_exceeded_handler

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# 라우터 등록
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(search_router)
app.include_router(case_router)
app.include_router(metrics_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(board_router)
app.include_router(users_router)


# 시작 로그
@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 로그 및 서비스 시작"""
    retrieval_mode = os.getenv("RETRIEVAL_MODE", "dense")
    memory_backend = os.getenv("CONVERSATION_MEMORY_BACKEND", "memory")
    logger.info("[Startup] 똑소리 API 서버 시작")
    logger.info(f"[Startup] Retrieval Mode: {retrieval_mode}")
    logger.info(f"[Startup] Conversation Memory Backend: {memory_backend}")
    logger.info("[Startup] Embedding: OpenAI text-embedding-3-large")

    # 템플릿 캐시 초기화 (개발 중 템플릿 변경 반영)
    try:
        from app.agents.answer_generation.template_loader import TemplateLoader

        TemplateLoader.reload_templates()
        logger.info("[Startup] Template cache cleared - will reload fresh templates")
    except Exception as e:
        logger.warning(f"[Startup] Template cache clear failed: {e}")

    # ConversationCleanupService 시작
    try:
        from app.supervisor.persistence.cleanup import get_cleanup_service

        cleanup_service = get_cleanup_service()
        await cleanup_service.start()
        logger.info("[Startup] ConversationCleanupService 시작 완료")
    except Exception as e:
        logger.warning(f"[Startup] ConversationCleanupService 시작 실패: {e}")

    # SEC-14: 기본 시크릿 사용 경고
    from app.common.config import get_config

    config = get_config()
    if config.auth.jwt_secret_key == "dev_secret_key_change_in_production":
        logger.warning(
            "[Security] JWT_SECRET_KEY가 기본값입니다. 프로덕션에서 반드시 변경하세요!"
        )
    if config.db.password == "postgres":
        logger.warning(
            "[Security] DB_PASSWORD가 기본값입니다. 프로덕션에서 반드시 변경하세요!"
        )


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
