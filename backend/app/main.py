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
# [SEC-07] 보안: 허용 메서드와 헤더를 명시적으로 제한
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],  # DELETE는 회원탈퇴용
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)

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
app.include_router(users_router)


# 시작 로그
def _validate_security_config():
    """
    [SEC-01, SEC-40] 프로덕션 보안 설정 검증

    프로덕션 환경에서 필수 보안 환경변수가 올바르게 설정되었는지 확인합니다.
    개발 환경에서는 경고만 출력합니다.

    ENVIRONMENT 환경변수:
        - 'production' 또는 'prod': 프로덕션 모드 (필수 검증 활성화)
        - 그 외: 개발 모드 (경고만 출력)
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    is_production = env in ("production", "prod")
    warnings_list = []

    # JWT_SECRET_KEY 검증
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    default_jwt_secret = "dev_secret_key_change_in_production"
    if not jwt_secret or jwt_secret == default_jwt_secret:
        msg = (
            "[SEC-01] JWT_SECRET_KEY가 기본값이거나 미설정됨 - 프로덕션에서 변경 필수!"
        )
        if is_production:
            logger.critical(msg)
            raise RuntimeError(msg)
        else:
            warnings_list.append(msg)

    # REDIS_PASSWORD 검증 (Redis 사용 시, 프로덕션에서만 필수)
    redis_host = os.getenv("REDIS_HOST", "")
    redis_password = os.getenv("REDIS_PASSWORD", "")
    if redis_host and not redis_password:
        msg = "[SEC-40] REDIS_PASSWORD 미설정 - Redis 인증 없이 실행됨"
        if is_production:
            logger.critical(msg)
            raise RuntimeError(msg)
        else:
            warnings_list.append(msg)

    # OAuth 설정 검증 (프로덕션에서만 경고)
    if is_production:
        oauth_vars = [
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "NAVER_CLIENT_ID",
            "NAVER_CLIENT_SECRET",
        ]
        missing = [v for v in oauth_vars if not os.getenv(v)]
        if missing:
            logger.warning(
                f"[Auth] OAuth 환경변수 미설정: {missing} - 소셜 로그인 불가"
            )

    # 개발 환경 경고 출력
    for warning in warnings_list:
        logger.warning(warning)


@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 로그 및 서비스 시작"""
    # [SEC-01, SEC-40] 보안 설정 검증
    _validate_security_config()

    retrieval_mode = os.getenv("RETRIEVAL_MODE", "dense")
    logger.info("[Startup] 똑소리 API 서버 시작")
    logger.info(f"[Startup] Retrieval Mode: {retrieval_mode}")
    logger.info("[Startup] Embedding: OpenAI text-embedding-3-large")

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
