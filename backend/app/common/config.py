"""
똑소리 프로젝트 - 통합 설정 모듈

작성일: 2026-01-24
최종 수정: 2026-01-24

[역할 및 책임]
애플리케이션 전역에서 사용되는 설정을 중앙 관리합니다.
Pydantic Settings를 활용하여 환경변수 기반 설정을 타입 안전하게 관리합니다.

[사용 예시]
    from app.common.config import get_config

    config = get_config()
    print(config.database.host)
    print(config.llm.model)
    print(config.agent.similarity_threshold)

[설정 그룹]
- DatabaseConfig: 데이터베이스 연결 설정
- EmbeddingConfig: 임베딩 서버 설정
- LLMConfig: LLM 모델 설정
- AgentConfig: 에이전트 관련 설정
- RedisConfig: Redis 캐시 설정
- AppConfig: 애플리케이션 전역 설정
"""

from functools import lru_cache
from typing import Dict, List, Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ============================================================
# 데이터베이스 설정
# ============================================================


class DatabaseConfig(BaseSettings):
    """
    데이터베이스 연결 설정.

    PostgreSQL (pgvector) 연결에 필요한 설정을 관리합니다.

    환경변수:
        DB_HOST: 데이터베이스 호스트 (기본값: localhost)
        DB_PORT: 데이터베이스 포트 (기본값: 5432)
        DB_NAME: 데이터베이스 이름 (기본값: ddoksori)
        DB_USER: 데이터베이스 사용자 (기본값: postgres)
        DB_PASSWORD: 데이터베이스 비밀번호 (기본값: postgres)
    """

    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = Field(default="localhost", description="데이터베이스 호스트")
    port: int = Field(default=5432, description="데이터베이스 포트")
    name: str = Field(default="ddoksori", description="데이터베이스 이름")
    user: str = Field(default="postgres", description="데이터베이스 사용자")
    password: str = Field(default="postgres", description="데이터베이스 비밀번호")

    def get_connection_dict(self) -> Dict[str, str]:
        """
        psycopg2 연결에 사용할 딕셔너리를 반환합니다.

        Returns:
            연결 파라미터 딕셔너리
        """
        return {
            "host": self.host,
            "port": str(self.port),
            "database": self.name,
            "user": self.user,
            "password": self.password,
        }

    def get_dsn(self) -> str:
        """
        데이터베이스 DSN 문자열을 반환합니다.

        Returns:
            PostgreSQL DSN 문자열
        """
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


# ============================================================
# 임베딩 서버 설정
# ============================================================


class EmbeddingConfig(BaseSettings):
    """
    임베딩 서버 설정.

    KURE-v1 또는 OpenAI 임베딩 서버 연결 설정을 관리합니다.

    환경변수:
        EMBED_API_URL: 임베딩 API URL (기본값: http://localhost:8001/embed)
        EMBEDDING_MODEL_NAME: 임베딩 모델명 (기본값: nlpai-lab/KURE-v1)
        USE_OPENAI_EMBEDDING: OpenAI 임베딩 사용 여부 (기본값: false)
    """

    model_config = SettingsConfigDict(env_prefix="EMBED_")

    api_url: str = Field(
        default="http://localhost:8001/embed",
        alias="EMBED_API_URL",
        description="임베딩 API URL",
    )
    model_name: str = Field(
        default="nlpai-lab/KURE-v1",
        alias="EMBEDDING_MODEL_NAME",
        description="임베딩 모델명",
    )
    use_openai: bool = Field(
        default=False,
        alias="USE_OPENAI_EMBEDDING",
        description="OpenAI 임베딩 사용 여부",
    )


# ============================================================
# LLM 설정
# ============================================================


class LLMConfig(BaseSettings):
    """
    LLM 모델 설정.

    OpenAI, EXAONE 등 LLM 모델 호출에 필요한 설정을 관리합니다.

    환경변수:
        LLM_MODEL: 기본 LLM 모델명 (기본값: gpt-4o-mini)
        OPENAI_API_KEY: OpenAI API 키
        LLM_TEMPERATURE: 생성 온도 (기본값: 0.7)
        LLM_MAX_TOKENS: 최대 토큰 수 (기본값: 2048)
        LLM_TOOL_TIMEOUT_MS: 도구 호출 타임아웃 (기본값: 5000ms)
    """

    model_config = SettingsConfigDict(env_prefix="LLM_")

    model: str = Field(default="gpt-4o-mini", description="기본 LLM 모델명")
    openai_api_key: Optional[str] = Field(
        default=None, alias="OPENAI_API_KEY", description="OpenAI API 키"
    )
    temperature: float = Field(default=0.7, description="생성 온도")
    max_tokens: int = Field(default=2048, description="최대 토큰 수")
    tool_timeout_ms: int = Field(
        default=5000, description="도구 호출 타임아웃 (밀리초)"
    )


class ExaoneConfig(BaseSettings):
    """
    EXAONE 모델 설정.

    RunPod에서 호스팅되는 EXAONE 모델 호출 설정을 관리합니다.

    환경변수:
        EXAONE_RUNPOD_URL: RunPod API URL
        EXAONE_RUNPOD_API_KEY: RunPod API 키
        EXAONE_MODEL: 모델명 (기본값: LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct)
        EXAONE_MODEL_SIZE: 모델 크기 (기본값: 7.8B)
        EXAONE_TIMEOUT: 타임아웃 (기본값: 10초)
        EXAONE_TEMPERATURE: 생성 온도 (기본값: 0.3)
        EXAONE_MAX_TOKENS: 최대 토큰 수 (기본값: 1024)
    """

    model_config = SettingsConfigDict(env_prefix="EXAONE_")

    runpod_url: Optional[str] = Field(default=None, description="RunPod API URL")
    runpod_api_key: str = Field(default="dummy", description="RunPod API 키")
    model: str = Field(
        default="LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct", description="EXAONE 모델명"
    )
    model_size: str = Field(default="7.8B", description="모델 크기")
    timeout: int = Field(default=10, description="타임아웃 (초)")
    temperature: float = Field(default=0.3, description="생성 온도")
    max_tokens: int = Field(default=1024, description="최대 토큰 수")


# ============================================================
# 모델 아키텍처 설정
# ============================================================


class ModelConfig(BaseSettings):
    """
    모델 아키텍처 설정.

    MAS(Multi-Agent System) 각 에이전트에서 사용할 LLM 모델을 중앙 관리합니다.
    환경변수로 오버라이드 가능하며, 기본값은 최적화된 모델 조합입니다.

    환경변수:
        MODEL_SUPERVISOR: Supervisor 에이전트 모델 (기본값: gpt-4o)
        MODEL_DRAFT_AGENT: Draft 에이전트 모델 (기본값: gpt-4o)
        MODEL_REVIEW_AGENT: Review 에이전트 모델 (기본값: gpt-4o)
        MODEL_QUERY_CLASSIFIER: Query Classifier 에이전트 모델 (기본값: gpt-4o-mini)
        MODEL_QUERY_EXPANDER: Query Expander 에이전트 모델 (기본값: gpt-4o-mini)
    """

    model_config = SettingsConfigDict(env_prefix="MODEL_")

    supervisor: str = Field(default="gpt-4o", description="Supervisor 에이전트 모델")
    draft_agent: str = Field(default="gpt-4o", description="Draft 에이전트 모델")
    review_agent: str = Field(default="gpt-4o", description="Review 에이전트 모델")
    query_classifier: str = Field(
        default="gpt-4o-mini", description="Query Classifier 에이전트 모델"
    )
    query_expander: str = Field(
        default="gpt-4o-mini", description="Query Expander 에이전트 모델"
    )


class PortConfig(BaseSettings):
    """
    서비스 포트 설정.

    vLLM, 임베딩 서버 등 외부 서비스 포트를 중앙 관리합니다.

    환경변수:
        PORT_EXAONE_VLLM: EXAONE vLLM 서버 포트 (기본값: 19010)
    """

    model_config = SettingsConfigDict(env_prefix="PORT_")

    exaone_vllm: int = Field(default=19010, description="EXAONE vLLM 서버 포트")


# ============================================================
# 에이전트 설정
# ============================================================


class AgentSettings(BaseSettings):
    """
    에이전트 공통 설정 (Pydantic Settings).

    ReAct, Legal Review 등 에이전트 동작에 필요한 설정을 관리합니다.
    새 코드에서는 get_config().agent로 접근하세요.

    환경변수:
        SIMILARITY_THRESHOLD: 기본 유사도 임계값 (기본값: 0.55)
        MAX_REACT_ITERATIONS: ReAct 최대 반복 횟수 (기본값: 2)
        PROHIBITED_VIOLATION_THRESHOLD: 금지 표현 위반 임계값 (기본값: 3)
        MAX_REVIEW_RETRIES: 최대 재검토 횟수 (기본값: 2)
    """

    model_config = SettingsConfigDict(env_prefix="")

    # 유사도 설정
    similarity_threshold: float = Field(
        default=0.55, alias="SIMILARITY_THRESHOLD", description="기본 유사도 임계값"
    )
    similarity_threshold_dispute: float = Field(
        default=0.55,
        alias="SIMILARITY_THRESHOLD_DISPUTE",
        description="분쟁 쿼리 유사도 임계값",
    )
    similarity_threshold_law: float = Field(
        default=0.60,
        alias="SIMILARITY_THRESHOLD_LAW",
        description="법령 쿼리 유사도 임계값",
    )
    similarity_threshold_criteria: float = Field(
        default=0.50,
        alias="SIMILARITY_THRESHOLD_CRITERIA",
        description="기준 쿼리 유사도 임계값",
    )
    similarity_threshold_general: float = Field(
        default=0.45,
        alias="SIMILARITY_THRESHOLD_GENERAL",
        description="일반 쿼리 유사도 임계값",
    )

    # ReAct 설정
    max_react_iterations: int = Field(
        default=2, alias="MAX_REACT_ITERATIONS", description="ReAct 최대 반복 횟수"
    )
    react_llm_max_retries: int = Field(
        default=2,
        alias="REACT_LLM_MAX_RETRIES",
        description="ReAct LLM 최대 재시도 횟수",
    )
    react_llm_retry_delay_ms: int = Field(
        default=100,
        alias="REACT_LLM_RETRY_DELAY_MS",
        description="ReAct LLM 재시도 지연 (밀리초)",
    )
    react_think_mode: str = Field(
        default="rule",
        alias="REACT_THINK_MODE",
        description="ReAct 사고 모드 (rule | llm)",
    )
    use_llm_tools: bool = Field(
        default=False, alias="USE_LLM_TOOLS", description="LLM 도구 사용 여부"
    )

    # Legal Review 설정
    prohibited_violation_threshold: int = Field(
        default=3,
        alias="PROHIBITED_VIOLATION_THRESHOLD",
        description="금지 표현 위반 임계값",
    )
    max_review_retries: int = Field(
        default=2, alias="MAX_REVIEW_RETRIES", description="최대 재검토 횟수"
    )
    enable_llm_review: bool = Field(
        default=False, alias="ENABLE_LLM_REVIEW", description="LLM 검토 활성화 여부"
    )

    # Query Analysis 설정
    enable_fast_path_promotion: bool = Field(
        default=True,
        alias="ENABLE_FAST_PATH_PROMOTION",
        description="빠른 경로 프로모션 활성화",
    )
    enable_ambiguous_detection: bool = Field(
        default=True,
        alias="ENABLE_AMBIGUOUS_DETECTION",
        description="모호한 쿼리 감지 활성화",
    )

    # Retrieval 설정
    enable_dispute_metadata_extraction: bool = Field(
        default=True,
        alias="ENABLE_DISPUTE_METADATA_EXTRACTION",
        description="분쟁 메타데이터 추출 활성화",
    )
    enable_document_level_similarity: bool = Field(
        default=True,
        alias="ENABLE_DOCUMENT_LEVEL_SIMILARITY",
        description="문서 레벨 유사도 활성화",
    )
    document_similarity_candidate_multiplier: int = Field(
        default=5,
        alias="DOCUMENT_SIMILARITY_CANDIDATE_MULTIPLIER",
        description="문서 유사도 후보 배수",
    )
    enable_retrieval_trace: bool = Field(
        default=False, alias="ENABLE_RETRIEVAL_TRACE", description="검색 추적 활성화"
    )

    def get_similarity_threshold(self, query_type: Optional[str] = None) -> float:
        """
        쿼리 타입별 유사도 임계값을 반환합니다.

        Args:
            query_type: 쿼리 타입 (dispute, law, criteria, general)
                       None이면 기본 임계값 반환

        Returns:
            해당 쿼리 타입의 유사도 임계값
        """
        thresholds = {
            "dispute": self.similarity_threshold_dispute,
            "law": self.similarity_threshold_law,
            "criteria": self.similarity_threshold_criteria,
            "general": self.similarity_threshold_general,
            "case": self.similarity_threshold_dispute,  # 분쟁 조정 사례는 dispute 임계값 사용
        }
        if query_type and query_type in thresholds:
            return thresholds[query_type]
        return self.similarity_threshold


# ============================================================
# 검색 전략 설정 (Retrieval Strategy)
# ============================================================


class RetrievalSettings(BaseSettings):
    """
    검색 전략 설정.

    RRF 파라미터, HyDE, Adaptive RAG, 도메인별 노출 제한 등을 관리합니다.

    환경변수:
        RETRIEVAL_RRF_K: SQL 레벨 RRF k 파라미터 (기본값: 10)
        RETRIEVAL_RRF_K_PYTHON: Python 2차 RRF fusion k값 (기본값: 60)
        RETRIEVAL_DEFAULT_TOP_K: 에이전트별 검색 수 (기본값: 10)
        RETRIEVAL_HYDE_ENABLED: HyDE 활성화 (기본값: true)
        RETRIEVAL_HYDE_MODEL: HyDE 가상 답변 생성 모델 (기본값: gpt-4o-mini)
        RETRIEVAL_HYDE_MAX_TOKENS: HyDE 최대 토큰 수 (기본값: 200)
        RETRIEVAL_ADAPTIVE_ENABLED: Adaptive RAG 활성화 (기본값: true)
        RETRIEVAL_SIMPLE_SKIP_HYDE: SIMPLE 쿼리 HyDE 생략 (기본값: true)
        RETRIEVAL_DISPLAY_LAW: 법률 노출 수 (기본값: 1)
        RETRIEVAL_DISPLAY_CRITERIA: 기준 노출 수 (기본값: 2)
        RETRIEVAL_DISPLAY_CASE: 사례 노출 수 (기본값: 3)
        RETRIEVAL_DISPLAY_COUNSEL: 상담 노출 수 (기본값: 2)
        RETRIEVAL_CACHE_OVERFLOW: 오버플로 캐시 활성화 (기본값: true)
        RETRIEVAL_CACHE_TTL: 오버플로 캐시 TTL 초 (기본값: 1800)
    """

    model_config = SettingsConfigDict(env_prefix="RETRIEVAL_")

    # RRF 파라미터
    rrf_k: int = Field(
        default=10, description="SQL 레벨 RRF k 파라미터 (낮을수록 상위 결과 차별화)"
    )
    rrf_k_python: int = Field(
        default=60, description="Python 2차 RRF fusion k값 (expanded_queries 병합용)"
    )
    default_top_k: int = Field(default=10, description="에이전트별 기본 검색 수")

    # HyDE 설정
    hyde_enabled: bool = Field(default=True, description="HyDE 활성화 여부")
    hyde_model: str = Field(
        default="gpt-4o-mini", description="HyDE 가상 답변 생성 모델"
    )
    hyde_max_tokens: int = Field(default=200, description="HyDE 최대 토큰 수")

    # Adaptive RAG 설정
    adaptive_enabled: bool = Field(default=True, description="Adaptive RAG 활성화 여부")
    simple_skip_hyde: bool = Field(default=True, description="SIMPLE 쿼리는 HyDE 생략")

    # 도메인별 노출 제한
    display_law: int = Field(default=1, description="법률 노출 수")
    display_criteria: int = Field(default=2, description="기준 노출 수")
    display_case: int = Field(default=3, description="사례 노출 수")
    display_counsel: int = Field(default=2, description="상담 노출 수")

    # 오버플로 캐시
    cache_overflow: bool = Field(default=True, description="오버플로 캐시 활성화")
    cache_ttl: int = Field(default=1800, description="오버플로 캐시 TTL (초)")

    # 충분성 최소 품질 점수
    sufficiency_min_score: float = Field(
        default=0.01, description="RRF 최소 품질 점수. 이하면 marginal 경고"
    )


# ============================================================
# Redis 설정
# ============================================================


class RedisConfig(BaseSettings):
    """
    Redis 캐시 설정.

    답변 캐싱에 사용되는 Redis 연결 설정을 관리합니다.

    환경변수:
        REDIS_HOST: Redis 호스트 (기본값: localhost)
        REDIS_PORT: Redis 포트 (기본값: 6379)
        REDIS_DB: Redis 데이터베이스 번호 (기본값: 0)
        ENABLE_ANSWER_CACHE: 답변 캐시 활성화 (기본값: false)
        ANSWER_CACHE_TTL_HOURS: 캐시 TTL (기본값: 24시간)
    """

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = Field(default="localhost", description="Redis 호스트")
    port: int = Field(default=6379, description="Redis 포트")
    db: int = Field(default=0, description="Redis 데이터베이스 번호")
    enable_answer_cache: bool = Field(
        default=False, alias="ENABLE_ANSWER_CACHE", description="답변 캐시 활성화"
    )
    answer_cache_ttl_hours: int = Field(
        default=24, alias="ANSWER_CACHE_TTL_HOURS", description="답변 캐시 TTL (시간)"
    )


# ============================================================
# Moderation 설정
# ============================================================


class ModerationConfig(BaseSettings):
    """
    콘텐츠 모더레이션 설정.

    입출력 가드레일 설정을 관리합니다.
    """

    model_config = SettingsConfigDict(env_prefix="MODERATION_")

    enabled: bool = Field(
        default=True, alias="MODERATION_ENABLED", description="모더레이션 활성화"
    )
    model: str = Field(
        default="omni-moderation-latest",
        alias="MODERATION_MODEL",
        description="모더레이션 모델",
    )


# ============================================================
# 인증 설정 (JWT & OAuth)
# ============================================================


class AuthConfig(BaseSettings):
    """
    인증 시스템 설정.

    JWT 토큰 인증 및 OAuth 2.0 소셜 로그인 설정을 관리합니다.

    환경변수:
        JWT_SECRET_KEY: JWT 서명에 사용할 비밀 키
        JWT_ALGORITHM: JWT 알고리즘 (기본값: HS256)
        JWT_TOKEN_EXPIRE_DAYS: JWT 토큰 만료 기간 (기본값: 30일)
        GOOGLE_CLIENT_ID: Google OAuth Client ID
        GOOGLE_CLIENT_SECRET: Google OAuth Client Secret
        NAVER_CLIENT_ID: Naver Client ID
        NAVER_CLIENT_SECRET: Naver Client Secret
        BACKEND_URL: Backend API URL (기본값: http://localhost:8000)
        FRONTEND_URL: Frontend URL (기본값: http://localhost:5173)
    """

    model_config = SettingsConfigDict(env_prefix="")

    # JWT 설정
    jwt_secret_key: str = Field(
        default="dev_secret_key_change_in_production",
        alias="JWT_SECRET_KEY",
        description="JWT 서명 비밀 키",
    )
    jwt_algorithm: str = Field(
        default="HS256", alias="JWT_ALGORITHM", description="JWT 알고리즘"
    )
    jwt_token_expire_days: int = Field(
        default=30, alias="JWT_TOKEN_EXPIRE_DAYS", description="JWT 토큰 만료 기간 (일)"
    )

    # Google OAuth
    google_client_id: Optional[str] = Field(
        default=None, alias="GOOGLE_CLIENT_ID", description="Google OAuth Client ID"
    )
    google_client_secret: Optional[str] = Field(
        default=None,
        alias="GOOGLE_CLIENT_SECRET",
        description="Google OAuth Client Secret",
    )

    # Naver OAuth
    naver_client_id: Optional[str] = Field(
        default=None, alias="NAVER_CLIENT_ID", description="Naver Client ID"
    )
    naver_client_secret: Optional[str] = Field(
        default=None, alias="NAVER_CLIENT_SECRET", description="Naver Client Secret"
    )

    # URL 설정
    backend_url: str = Field(
        default="http://localhost:8000",
        alias="BACKEND_URL",
        description="Backend API URL",
    )
    frontend_url: str = Field(
        default="http://localhost:5173",
        alias="FRONTEND_URL",
        description="Frontend URL",
    )


# ============================================================
# 대화 메모리 설정
# ============================================================


class MemoryConfig(BaseSettings):
    """
    대화 메모리 시스템 설정.

    PostgreSQL 기반 장기 메모리 및 게스트 세션 관리 설정을 관리합니다.

    환경변수:
        CONVERSATION_MEMORY_BACKEND: 메모리 백엔드 (memory | db, 기본값: memory)
        MAX_CONVERSATION_TURNS: 최대 대화 턴 수 (기본값: 30)
        SLIDING_WINDOW_SIZE: 슬라이딩 윈도우 크기 (기본값: 10)
        GUEST_SESSION_TTL_HOURS: 게스트 세션 만료 시간 (기본값: 24시간)
        CLEANUP_INTERVAL_HOURS: Cleanup 서비스 실행 주기 (기본값: 1시간)
    """

    model_config = SettingsConfigDict(env_prefix="")

    backend: str = Field(
        default="memory",
        alias="CONVERSATION_MEMORY_BACKEND",
        description="메모리 백엔드 (memory | db)",
    )
    max_turns: int = Field(
        default=30, alias="MAX_CONVERSATION_TURNS", description="최대 대화 턴 수"
    )
    sliding_window_size: int = Field(
        default=10, alias="SLIDING_WINDOW_SIZE", description="슬라이딩 윈도우 크기"
    )
    guest_session_ttl_hours: int = Field(
        default=24,
        alias="GUEST_SESSION_TTL_HOURS",
        description="게스트 세션 만료 시간 (시간)",
    )
    cleanup_interval_hours: int = Field(
        default=1,
        alias="CLEANUP_INTERVAL_HOURS",
        description="Cleanup 서비스 실행 주기 (시간)",
    )


# ============================================================
# 대화형 챗봇 기능 플래그
# ============================================================


class ChatbotFeaturesConfig(BaseSettings):
    """
    대화형 챗봇 기능 플래그 설정.

    유연한 답변 형식, 후속 질문 등 대화형 챗봇 기능의 활성화 여부를 관리합니다.

    환경변수:
        ANSWER_FORMAT_MODE: 답변 형식 모드 (fixed | flexible, 기본값: fixed)
        ENABLE_FOLLOWUP_QUESTIONS: 후속 질문 생성 활성화 (기본값: false)
    """

    model_config = SettingsConfigDict(env_prefix="")

    answer_format_mode: str = Field(
        default="fixed",
        alias="ANSWER_FORMAT_MODE",
        description="답변 형식 모드 (fixed | flexible)",
    )
    enable_followup_questions: bool = Field(
        default=False,
        alias="ENABLE_FOLLOWUP_QUESTIONS",
        description="후속 질문 생성 활성화",
    )


# ============================================================
# 응답 처리 방식 설정 (Progressive Disclosure)
# ============================================================


class ResponseConfig(BaseSettings):
    """
    응답 처리 방식 설정.

    Progressive Disclosure, A/B 테스트 등 응답 생성 전략을 관리합니다.

    환경변수:
        RESPONSE_MODE: 응답 모드 (legacy | minimal | adaptive, 기본값: legacy)
        SUMMARY_MAX_LENGTH: 요약 최대 길이 (기본값: 200)
        FOLLOWUP_SIMILARITY_THRESHOLD: 후속 질문 매칭 임계값 (기본값: 0.8)
        META_QUERY_USE_LLM: 메타 쿼리 LLM 사용 여부 (기본값: false)
    """

    model_config = SettingsConfigDict(env_prefix="")

    response_mode: Literal["legacy", "minimal", "adaptive"] = Field(
        default="legacy",
        alias="RESPONSE_MODE",
        description="응답 모드 (legacy | minimal | adaptive)",
    )
    summary_max_length: int = Field(
        default=200, alias="SUMMARY_MAX_LENGTH", description="요약 최대 길이 (자)"
    )
    followup_similarity_threshold: float = Field(
        default=0.8,
        alias="FOLLOWUP_SIMILARITY_THRESHOLD",
        description="후속 질문 매칭 임계값",
    )
    meta_query_use_llm: bool = Field(
        default=False,
        alias="META_QUERY_USE_LLM",
        description="메타 쿼리 응답에 LLM 사용 여부 (adaptive 모드)",
    )


# ============================================================
# 애플리케이션 전역 설정
# ============================================================


class AppConfig(BaseSettings):
    """
    애플리케이션 전역 설정.

    모든 설정 그룹을 통합하여 관리합니다.

    환경변수:
        DEBUG: 디버그 모드 (기본값: false)
        CORS_ORIGINS: CORS 허용 오리진 (기본값: http://localhost:5173)
        RETRIEVAL_MODE: 검색 모드 (기본값: dense)
    """

    model_config = SettingsConfigDict(
        env_prefix="", env_nested_delimiter="__", extra="ignore"
    )

    # 전역 설정
    debug: bool = Field(default=False, alias="DEBUG", description="디버그 모드")
    cors_origins: str = Field(
        default="http://localhost:5173",
        alias="CORS_ORIGINS",
        description="CORS 허용 오리진 (쉼표 구분)",
    )
    retrieval_mode: str = Field(
        default="dense",
        alias="RETRIEVAL_MODE",
        description="검색 모드 (dense | hybrid)",
    )

    # LangSmith 추적
    langchain_tracing_v2: bool = Field(
        default=False, alias="LANGCHAIN_TRACING_V2", description="LangSmith 추적 활성화"
    )
    langchain_project: str = Field(
        default="default", alias="LANGCHAIN_PROJECT", description="LangSmith 프로젝트명"
    )

    # 하위 설정 그룹
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    exaone: ExaoneConfig = Field(default_factory=ExaoneConfig)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    moderation: ModerationConfig = Field(default_factory=ModerationConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    ports: PortConfig = Field(default_factory=PortConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    chatbot_features: ChatbotFeaturesConfig = Field(
        default_factory=ChatbotFeaturesConfig
    )
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    response: ResponseConfig = Field(default_factory=ResponseConfig)

    def get_cors_origins_list(self) -> List[str]:
        """
        CORS 허용 오리진 목록을 반환합니다.

        Returns:
            오리진 문자열 리스트
        """
        return [origin.strip() for origin in self.cors_origins.split(",")]


# ============================================================
# 싱글톤 인스턴스 관리
# ============================================================


@lru_cache()
def get_config() -> AppConfig:
    """
    애플리케이션 설정 싱글톤 인스턴스를 반환합니다.

    프로덕션 환경(USE_AWS_SECRETS=true)에서는 AWS Secrets Manager에서
    시크릿을 로드하여 os.environ에 주입한 후 설정을 생성합니다.

    Returns:
        AppConfig 인스턴스

    Example:
        from app.common.config import get_config

        config = get_config()
        db_host = config.database.host
        similarity = config.agent.similarity_threshold
    """
    from app.common.secrets import inject_aws_secrets

    inject_aws_secrets()
    return AppConfig()


def reload_config() -> AppConfig:
    """
    설정을 다시 로드합니다.

    환경변수가 변경된 후 호출하여 설정을 갱신합니다.
    주로 테스트에서 사용됩니다.

    Returns:
        새로 로드된 AppConfig 인스턴스
    """
    get_config.cache_clear()
    return get_config()


# ============================================================
# 하위 호환성을 위한 레거시 클래스
# ============================================================


class _LegacyAgentConfigMeta(type):
    """
    LegacyAgentConfig 클래스의 메타클래스.
    클래스 속성 접근을 동적으로 처리하여 get_config()에서 값을 가져옵니다.
    """

    @property
    def SIMILARITY_THRESHOLD(cls) -> float:
        return get_config().agent.similarity_threshold

    @property
    def MAX_REACT_ITERATIONS(cls) -> int:
        return get_config().agent.max_react_iterations

    @property
    def PROHIBITED_VIOLATION_THRESHOLD(cls) -> int:
        return get_config().agent.prohibited_violation_threshold

    @property
    def MAX_REVIEW_RETRIES(cls) -> int:
        return get_config().agent.max_review_retries

    @property
    def SIMILARITY_THRESHOLDS(cls) -> Dict[str, float]:
        config = get_config().agent
        return {
            "dispute": config.similarity_threshold_dispute,
            "law": config.similarity_threshold_law,
            "criteria": config.similarity_threshold_criteria,
            "general": config.similarity_threshold_general,
        }


class LegacyAgentConfig(metaclass=_LegacyAgentConfigMeta):
    """
    기존 AgentConfig 클래스와의 하위 호환성을 위한 래퍼.

    [주의]
    이 클래스는 하위 호환성을 위해 유지됩니다.
    새 코드에서는 get_config().agent를 직접 사용하세요.

    기존 사용법:
        from app.common.config import AgentConfig
        threshold = AgentConfig.get_similarity_threshold('dispute')
        max_iter = AgentConfig.MAX_REACT_ITERATIONS

    새 사용법:
        from app.common.config import get_config
        config = get_config()
        threshold = config.agent.get_similarity_threshold('dispute')
        max_iter = config.agent.max_react_iterations
    """

    @classmethod
    def get_similarity_threshold(cls, query_type: Optional[str] = None) -> float:
        """쿼리 타입별 유사도 임계값 반환 (레거시 호환)"""
        return get_config().agent.get_similarity_threshold(query_type)

    @classmethod
    def reload(cls) -> None:
        """환경 변수에서 설정 다시 로드 (레거시 호환)"""
        reload_config()

    @classmethod
    def to_dict(cls) -> Dict:
        """현재 설정을 딕셔너리로 반환 (레거시 호환)"""
        config = get_config().agent
        return {
            "SIMILARITY_THRESHOLD": config.similarity_threshold,
            "MAX_REACT_ITERATIONS": config.max_react_iterations,
            "PROHIBITED_VIOLATION_THRESHOLD": config.prohibited_violation_threshold,
            "MAX_REVIEW_RETRIES": config.max_review_retries,
            "SIMILARITY_THRESHOLDS": cls.SIMILARITY_THRESHOLDS,
        }


# 하위 호환성을 위해 기존 이름으로도 사용 가능
# (주의: 새 코드에서는 get_config()을 사용 권장)

# 레거시 호환: AgentConfig는 LegacyAgentConfig의 별칭
# 기존 코드: AgentConfig.MAX_REACT_ITERATIONS, AgentConfig.get_similarity_threshold()
AgentConfig = LegacyAgentConfig


# ============================================================
# 모듈 공개 API
# ============================================================

__all__ = [
    # 설정 클래스 (Pydantic)
    "AppConfig",
    "DatabaseConfig",
    "EmbeddingConfig",
    "LLMConfig",
    "ExaoneConfig",
    "AgentSettings",  # 새 이름 (get_config().agent 타입)
    "RedisConfig",
    "ModerationConfig",
    "ModelConfig",
    "PortConfig",
    "AuthConfig",  # JWT & OAuth 설정
    "MemoryConfig",  # 대화 메모리 설정
    "ChatbotFeaturesConfig",  # 대화형 챗봇 기능 플래그
    "RetrievalSettings",  # 검색 전략 설정
    "ResponseConfig",  # 응답 처리 방식 설정
    # 설정 접근 함수
    "get_config",
    "reload_config",
    # 하위 호환성
    "AgentConfig",  # LegacyAgentConfig 별칭 (클래스 속성 접근)
    "LegacyAgentConfig",
]
