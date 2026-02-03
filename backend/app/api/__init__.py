"""
똑소리 프로젝트 - API 라우터 모듈

FastAPI APIRouter를 모아서 main.py에서 include할 수 있도록 제공합니다.

모듈 구조:
    - health.py: 헬스체크 (/, /health)
    - search.py: 검색 (/search)
    - chat.py: 채팅 (/chat, /chat/stream)
    - case.py: 사례 조회 (/case/{uid})
    - metrics.py: 메트릭스 (/metrics/*)

사용법:
    from app.api import health_router, chat_router, search_router, case_router, metrics_router

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(search_router)
    app.include_router(case_router)
    app.include_router(metrics_router)
"""

from .admin import router as admin_router
from .auth import router as auth_router
from .case import router as case_router
from .chat import router as chat_router

# 의존성도 export
from .dependencies import (
    get_db_config,
    get_retrieval_mode,
    get_retriever,
)
from .health import router as health_router
from .metrics import router as metrics_router

# 모델도 함께 export
from .models import (
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
from .search import router as search_router
from .users import router as users_router

__all__ = [
    # 라우터
    "health_router",
    "chat_router",
    "search_router",
    "case_router",
    "metrics_router",
    "auth_router",
    "admin_router",
    "users_router",
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
