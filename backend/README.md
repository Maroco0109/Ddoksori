# Backend — DDOKSORI MAS 아키텍처

> **똑소리 프로젝트** — 한국 소비자 분쟁 해결 Multi-Agent System 백엔드
> **스택**: FastAPI · LangGraph · PostgreSQL + pgvector · Redis · OpenAI

---

## 목차

1. [아키텍처 개요](#아키텍처-개요)
2. [모듈 구조](#모듈-구조)
3. [MAS 파이프라인](#mas-파이프라인)
4. [주요 모듈 상세](#주요-모듈-상세)
5. [캐시 계층](#캐시-계층)
6. [인증 체계](#인증-체계)
7. [안전장치](#안전장치)
8. [기술 스택](#기술-스택)
9. [실행 방법](#실행-방법)
10. [테스트](#테스트)
11. [데이터베이스](#데이터베이스)

---

## 아키텍처 개요

Hub-Spoke 패턴의 Multi-Agent System(MAS)으로, LangGraph가 에이전트 실행 흐름을 오케스트레이션합니다.

```
사용자 질문 → API (chat.py)
                ↓
        Supervisor Graph (graph_mas.py)
                ↓
    1. Input Guardrail (moderation)
                ↓
    2. QueryAnalyst (의도 분류 + 쿼리 확장)
                ↓
    3. Selective Retrieval (병렬 Fan-out)
       ├─ LawAgent (법령)
       ├─ CriteriaAgent (분쟁조정기준)
       ├─ CaseAgent (분쟁/상담 사례)
       └─ ProductAgent (제품 관련성)
                ↓
    4. RetrievalMerge (결과 병합 + 필터링)
                ↓
    5. AnswerDrafter (gpt-4o 답변 생성)
                ↓
    6. LegalReviewer (법적 검증) [조건부]
                ↓
    7. FollowupGenerator (후속 질문)
                ↓
    8. Output Guardrail
                ↓
        API 응답 → 프론트엔드
```

**Fast Path**: `general`/`system_meta` 쿼리는 검색·법률검토 생략
**Fallback Chain**: gpt-4o → gpt-4o-mini → claude-3-haiku → rule_based → safe_fallback

---

## 모듈 구조

```
backend/
├── app/
│   ├── main.py                  # FastAPI 진입점
│   ├── supervisor/              # MAS 오케스트레이션 (LangGraph)
│   │   ├── graph_mas.py         # Hub-Spoke 그래프 정의
│   │   ├── state/               # ChatState 스키마 (7개 서브모듈)
│   │   ├── nodes/               # 그래프 노드 (supervisor, retrieval_merge, clarify, memory_save)
│   │   ├── persistence/         # 체크포인터 & 정리
│   │   ├── cache.py             # L1 응답 캐시
│   │   ├── memory.py            # 대화 메모리
│   │   └── conversation_manager.py
│   │
│   ├── agents/                  # 전문 에이전트 구현
│   │   ├── query_analysis/      # 의도 분류, 키워드 추출, 쿼리 확장
│   │   ├── retrieval/           # 4개 검색 에이전트 (law, criteria, case, product)
│   │   ├── answer_generation/   # LLM 답변 생성 + Fallback 체인
│   │   ├── legal_review/        # 법적 정확성 검증
│   │   ├── followup/            # 후속 질문 생성
│   │   ├── registry/            # 에이전트 레지스트리 (동적 발견)
│   │   ├── protocols.py         # 에이전트 인터페이스 참조 문서
│   │   └── base.py              # 베이스 에이전트 클래스
│   │
│   ├── api/                     # FastAPI 라우터 (39개 엔드포인트)
│   │   ├── chat.py              # 채팅 (2개)
│   │   ├── search.py            # 검색 (1개)
│   │   ├── auth.py              # OAuth 인증 (7개)
│   │   ├── admin.py             # 관리자 (18개)
│   │   ├── users.py             # 마이페이지 (2개)
│   │   ├── health.py            # 헬스체크 (5개)
│   │   ├── metrics.py           # 메트릭스 (3개)
│   │   ├── case.py              # 사례 조회 (1개)
│   │   ├── models.py            # Pydantic 모델
│   │   ├── dependencies.py      # 의존성 주입
│   │   └── response_builder.py  # 응답 직렬화
│   │
│   ├── common/                  # 공유 인프라
│   │   ├── config.py            # Pydantic Settings 설정
│   │   ├── logging/             # 구조화 로깅 (PII 마스킹)
│   │   ├── cache/               # Redis 캐시 (base, embedding_cache)
│   │   ├── embedding/           # 임베딩 추상화 (OpenAI provider)
│   │   ├── sanitization.py      # 입력 정제
│   │   └── secrets.py           # AWS Secrets Manager
│   │
│   ├── auth/                    # 인증/인가
│   │   ├── oauth.py             # Google/Naver OAuth 2.0
│   │   ├── service.py           # 인증 서비스 로직
│   │   ├── models.py            # 사용자 모델
│   │   ├── user_db.py           # 사용자 DB 연산
│   │   └── dependencies.py      # JWT 의존성
│   │
│   ├── board/                   # 커뮤니티 게시판
│   │   └── board_db.py          # 게시판 DB 연산
│   │
│   ├── admin/                   # 관리자 백엔드
│   │   ├── admin_db.py          # 관리자 DB 연산
│   │   ├── models.py            # 관리자 모델
│   │   └── dependencies.py      # 관리자 의존성
│   │
│   ├── guardrail/               # 안전장치
│   │   ├── moderation.py        # OpenAI Moderation API
│   │   ├── policies.py          # 정책 정의
│   │   └── nodes.py             # 입출력 가드레일 노드
│   │
│   ├── llm/                     # LLM 클라이언트
│   │   ├── tool_calling_client.py  # 도구 호출 래퍼
│   │   ├── query_cache.py       # 쿼리 응답 캐시 (L2)
│   │   ├── exaone_client.py     # EXAONE 모델 클라이언트
│   │   └── providers/           # LLM 프로바이더 추상화
│   │
│   ├── domain/                  # 도메인 로직
│   │   ├── classifier.py        # 쿼리 분류기
│   │   └── config.py            # 도메인 설정
│   │
│   ├── middleware/               # 미들웨어
│   │   └── rate_limiter.py      # 속도 제한 (SlowAPI)
│   │
│   └── database/                # DB 스키마 & 마이그레이션
│       └── migrations/
│
├── scripts/
│   ├── testing/                 # 테스트 스위트
│   ├── data_loading/            # ETL 스크립트
│   └── evaluation/              # 평가 벤치마크
│
├── _archive/                    # 레거시 코드 (구 RAG 패턴)
├── Dockerfile                   # 개발용 Docker
├── Dockerfile.prod              # 프로덕션 Docker
├── requirements.txt             # Python 의존성
├── pyproject.toml               # Ruff 설정
└── pytest.ini                   # 테스트 설정
```

---

## MAS 파이프라인

### Supervisor Graph

`supervisor/graph_mas.py`의 `create_mas_supervisor_graph()`가 LangGraph 그래프를 생성합니다.

| 노드 | 모듈 | 역할 |
|------|------|------|
| `input_guardrail` | `guardrail/nodes.py` | 입력 안전성 검사 |
| `query_analyst` | `agents/query_analysis/` | 의도 분류, 쿼리 확장 |
| `retrieval_team` | `agents/retrieval/` | 4개 에이전트 병렬 검색 |
| `retrieval_merge` | `supervisor/nodes/` | 검색 결과 병합·필터링 |
| `answer_drafter` | `agents/answer_generation/` | LLM 답변 생성 |
| `legal_reviewer` | `agents/legal_review/` | 법적 검증 (조건부) |
| `followup` | `agents/followup/` | 후속 질문 생성 |
| `output_guardrail` | `guardrail/nodes.py` | 출력 안전성 검사 |
| `memory_save` | `supervisor/nodes/` | 대화 메모리 저장 |

### ChatState

`supervisor/state/`에 7개 서브모듈로 분리:

| 모듈 | 관리 영역 |
|------|----------|
| `session` | 세션 ID, 채팅 타입, 온보딩 정보 |
| `control` | 라우팅 모드, 실행 제어 |
| `agent_results` | 각 에이전트 출력 결과 |
| `memory` | 대화 이력, 컨텍스트 |
| `output` | 최종 응답, 인용, 후속 질문 |
| `supervisor` | Supervisor 의사결정 로그 |

---

## 주요 모듈 상세

### agents/ — 에이전트 시스템

Registry 패턴으로 Supervisor와 느슨하게 결합. 상세 문서는 각 에이전트 README 참조.

| 에이전트 | 디렉토리 | README |
|----------|---------|--------|
| QueryAnalyst | `agents/query_analysis/` | [README](app/agents/query_analysis/README.md) |
| LawAgent, CriteriaAgent, CaseAgent | `agents/retrieval/` | [README](app/agents/retrieval/README.md) |
| AnswerDrafter | `agents/answer_generation/` | [README](app/agents/answer_generation/README.md) |
| LegalReviewer | `agents/legal_review/` | [README](app/agents/legal_review/README.md) |
| FollowupGenerator | `agents/followup/` | [README](app/agents/followup/README.md) |
| AgentRegistry | `agents/registry/` | [README](app/agents/registry/README.md) |

### api/ — REST API

39개 엔드포인트, 8개 라우터. 상세는 [API README](app/api/README.md) 참조.

### common/ — 공유 인프라

| 모듈 | 설명 |
|------|------|
| `config.py` | `get_config()`로 접근하는 Pydantic Settings |
| `logging/` | JSON 구조화 로깅, PII 자동 마스킹 |
| `cache/` | Redis 기반 캐시 (`BaseRedisCache` 추상) |
| `embedding/` | 임베딩 팩토리 (OpenAI text-embedding-3-large, 1536d) |
| `secrets.py` | AWS Secrets Manager 통합 |

---

## 캐시 계층

| 레이어 | 위치 | 대상 | TTL |
|--------|------|------|-----|
| L1 | `supervisor/cache.py` | Supervisor 응답 | 설정 기반 |
| L2 | `llm/query_cache.py` | LLM 쿼리 응답 | 설정 기반 |
| L3 | `common/cache/embedding_cache.py` | 임베딩 벡터 | 설정 기반 |
| L4 | Redis | 검색 결과 | 설정 기반 |

`ENABLE_ANSWER_CACHE` 환경변수로 캐시 활성화/비활성화.

---

## 인증 체계

### OAuth 2.0

```
사용자 → /auth/google 또는 /auth/naver → OAuth Provider
                                              ↓
사용자 ← JWT 토큰 ← /auth/{provider}/callback
                         ↓
        이후 요청: Authorization: Bearer <JWT>
```

- **일반 사용자**: Google/Naver OAuth → JWT 발급
- **관리자**: `/api/admin/login` → 관리자 JWT → Admin API 접근

### 주요 환경변수

| 변수 | 설명 |
|------|------|
| `JWT_SECRET_KEY` | JWT 서명 키 |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | Naver OAuth |

---

## 안전장치

### 입출력 가드레일

| 단계 | 구현 | 설명 |
|------|------|------|
| 입력 | `guardrail/moderation.py` | OpenAI Moderation API로 유해 입력 차단 |
| 정책 | `guardrail/policies.py` | 도메인 특화 정책 규칙 |
| 출력 | `guardrail/nodes.py` | 응답 안전성 최종 검증 |

### 추가 보호

- **속도 제한**: `middleware/rate_limiter.py` (SlowAPI)
- **입력 정제**: `common/sanitization.py`
- **PII 마스킹**: `common/logging/` (로그 내 개인정보 자동 제거)
- **법률 검토**: `agents/legal_review/` (금지 표현, 인용 검증)

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| 웹 프레임워크 | FastAPI 0.115.6, Uvicorn |
| 그래프 오케스트레이션 | LangGraph 1.0.1 |
| LLM 프레임워크 | LangChain 0.3.27 |
| LLM | OpenAI GPT-4o (Supervisor/Draft/Review), EXAONE (실험적) |
| 임베딩 | OpenAI text-embedding-3-large (1536d) |
| 데이터베이스 | PostgreSQL 16 + pgvector (AWS RDS) |
| 캐시 | Redis 5.2.1 |
| 인증 | OAuth 2.0 (Google, Naver) + JWT |
| 테스트 | pytest, pytest-asyncio, httpx |
| 린팅 | Ruff (Black 호환, line-length 88) |
| 컨테이너 | Docker |

---

## 실행 방법

### 로컬 개발

```bash
# 1. 환경변수 설정
cp .env.example .env
# DB_HOST, OPENAI_API_KEY, JWT_SECRET_KEY 등 설정

# 2. 의존성 설치 (Conda 환경 필수)
conda run -n dsr pip install -r backend/requirements.txt

# 3. 서버 실행
conda run -n dsr uvicorn app.main:app --reload --port 8000
```

### Docker

```bash
# 개발
docker build -t ddoksori-backend -f backend/Dockerfile backend/
docker run -p 8000:8000 --env-file backend/.env ddoksori-backend

# 프로덕션
docker build -t ddoksori-backend:prod -f backend/Dockerfile.prod backend/
```

### Docker Compose (루트에서)

```bash
docker compose up -d          # 전체 스택
docker compose up redis -d    # Redis만
```

---

## 테스트

```bash
# 전체 테스트
conda run -n dsr pytest -c backend/pytest.ini backend/scripts/testing/

# 마커별 실행
conda run -n dsr pytest -m unit              # 단위 테스트 (DB 불필요)
conda run -n dsr pytest -m integration       # 통합 테스트 (PostgreSQL 필요)
conda run -n dsr pytest -m "not slow"        # 느린 테스트 제외
conda run -n dsr pytest -m llm              # LLM 테스트 (OPENAI_API_KEY 필요)

# 특정 모듈
conda run -n dsr pytest backend/scripts/testing/supervisor/
conda run -n dsr pytest backend/scripts/testing/query_analysis/
conda run -n dsr pytest backend/scripts/testing/retrieval/
```

**주요 마커**: `unit`, `integration`, `slow`, `llm`, `docker`, `needs_db`, `e2e`

---

## 데이터베이스

PostgreSQL 16 + pgvector (AWS RDS). 로컬 PostgreSQL이 아닌 원격 RDS 사용.

### 핵심 테이블

| 테이블 | 설명 |
|--------|------|
| `documents` | 문서 메타데이터 (상담사례, 분쟁조정사례, 법령) |
| `chunks` | 텍스트 청크 + 1536d 임베딩 벡터 |
| `mv_searchable_chunks` | 하이브리드 검색용 Materialized View |
| `laws` | 법령 메타데이터 |
| `law_units` | 법령 조/항/호/목 계층 구조 |
| `criteria` | 분쟁조정기준 원천 분류 |

### 검색 방식

- **Dense**: pgvector 코사인 유사도
- **Lexical**: PostgreSQL Full-Text Search (FTS)
- **Hybrid**: RRF (Reciprocal Rank Fusion) 알고리즘으로 융합

---

## 참조

- 에이전트 인터페이스: [agents/README.md](app/agents/README.md)
- API 엔드포인트: [api/README.md](app/api/README.md)
- 레거시 코드: `_archive/` (구 RAG 패턴, 참고용)
