# API 라우터 모듈

> **위치**: `backend/app/api/`
> **목적**: FastAPI 엔드포인트를 기능별로 분리한 모듈. 인증, 관리자, 채팅, 검색 등 39개 엔드포인트 제공.

---

## 모듈 구조

```
backend/app/api/
├── __init__.py          # 라우터·모델·의존성 통합 export
├── models.py            # Pydantic 요청/응답 모델
├── dependencies.py      # FastAPI 의존성 (get_retriever 등)
├── response_builder.py  # 응답 직렬화 유틸리티
├── health.py            # 헬스체크 라우터 (5개)
├── chat.py              # 채팅 라우터 (2개)
├── search.py            # 검색 라우터 (1개)
├── case.py              # 사례 조회 라우터 (1개)
├── metrics.py           # 메트릭스 라우터 (3개)
├── auth.py              # 인증 라우터 (7개)
├── admin.py             # 관리자 라우터 (18개)
├── users.py             # 사용자/마이페이지 라우터 (2개)
└── README.md            # 이 문서
```

## 라우터 등록

```python
# main.py
from app.api import (
    health_router,
    chat_router,
    search_router,
    case_router,
    metrics_router,
    auth_router,
    admin_router,
    users_router,
)
```

## 엔드포인트 목록 (39개)

### health.py — 헬스체크 (5개)

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/` | `root()` | API 서버 정보 (버전 포함) |
| GET | `/health` | `health_check()` | DB 연결 상태 확인 |
| GET | `/health/llm/supervisor` | `check_supervisor_llm()` | OpenAI Supervisor LLM 상태 |
| GET | `/health/llm/exaone` | `check_exaone_llm()` | EXAONE LLM 상태 |
| GET | `/health/embedding` | `check_embedding()` | 임베딩 API 상태 |

### chat.py — 채팅 (2개)

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| POST | `/chat` | `chat()` | LangGraph MAS 챗봇 응답 (JSON) |
| POST | `/chat/stream` | `chat_stream_sse()` | SSE 스트리밍 응답 |

다중 턴 대화, 세션 메모리, L1 캐시, 온보딩 지속, 질의분석→검색→생성→검토 파이프라인.

### search.py — 검색 (1개)

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| POST | `/search` | `search()` | 벡터 DB 하이브리드 검색 (LLM 미사용) |

RRF 퓨전 (dense + lexical), chunk_type 필터링 지원.

### case.py — 사례 조회 (1개)

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/case/{case_uid}` | `get_case()` | 특정 사례의 전체 청크 조회 |

### metrics.py — 메트릭스 (3개)

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/metrics/agents` | `get_agent_metrics()` | 에이전트 성능 통계 |
| GET | `/metrics/agents/summary` | `get_agent_metrics_summary()` | 전체 성능 요약 |
| GET | `/metrics/agents/recent` | `get_recent_metrics()` | 최근 메트릭 조회 |

### auth.py — 인증 (7개)

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/auth/google` | `google_login()` | Google OAuth 로그인 시작 |
| GET | `/auth/google/callback` | `google_callback()` | Google OAuth 콜백 처리 |
| GET | `/auth/naver` | `naver_login()` | Naver OAuth 로그인 시작 |
| GET | `/auth/naver/callback` | `naver_callback()` | Naver OAuth 콜백 처리 |
| GET | `/auth/me` | `get_me()` | 현재 인증 사용자 정보 조회 |
| GET | `/auth/verify` | `verify_token()` | JWT 토큰 검증 |
| DELETE | `/auth/delete-account` | `delete_account()` | 계정 삭제 |

OAuth 2.0 (Google, Naver), JWT 토큰 기반 인증, Redis/메모리 상태 저장, CSRF 보호.

### admin.py — 관리자 (18개)

#### 인증

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| POST | `/api/admin/login` | `admin_login()` | 관리자 로그인 |
| GET | `/api/admin/verify` | `verify_admin_token()` | 관리자 토큰 검증 |

#### 대시보드

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/api/admin/stats` | `get_stats()` | 대시보드 통계 |

#### 게시글 관리

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/api/admin/posts` | `get_posts()` | 게시글 목록 (검색/필터) |
| GET | `/api/admin/posts/{post_id}` | `get_post()` | 게시글 상세 |
| PUT | `/api/admin/posts/{post_id}/visibility` | `update_post_visibility()` | 공개/비공개 전환 |
| DELETE | `/api/admin/posts/{post_id}` | `delete_post()` | 게시글 소프트 삭제 |
| POST | `/api/admin/posts/notice` | `create_notice()` | 공지사항 작성 |

#### 댓글 관리

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/api/admin/comments` | `get_comments()` | 댓글 목록 |
| PUT | `/api/admin/comments/{comment_id}/visibility` | `update_comment_visibility()` | 공개/비공개 전환 |
| DELETE | `/api/admin/comments/{comment_id}` | `delete_comment()` | 댓글 소프트 삭제 |

#### 사용자 관리

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/api/admin/users` | `get_users()` | 사용자 목록 (검색/필터) |
| GET | `/api/admin/users/{user_id}` | `get_user()` | 사용자 상세 |
| PUT | `/api/admin/users/{user_id}/status` | `update_user_status()` | 상태 변경 (active/suspended/banned) |

#### 신고 관리

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/api/admin/reports` | `get_reports()` | 신고 목록 (필터) |
| GET | `/api/admin/reports/{report_id}` | `get_report()` | 신고 상세 |
| PUT | `/api/admin/reports/{report_id}/status` | `update_report_status()` | 상태 변경 (reviewed/resolved/rejected) |

### users.py — 마이페이지 (2개)

| 메서드 | 경로 | 함수 | 설명 |
|--------|------|------|------|
| GET | `/api/users/me/posts` | `get_my_posts()` | 내 게시글 조회 (페이지네이션) |
| GET | `/api/users/me/commented-posts` | `get_my_commented_posts()` | 댓글 단 게시글 조회 |

JWT 인증 필수, 페이지네이션 지원.

## 모델 정의

### 요청 모델

| 모델 | 설명 |
|------|------|
| `ChatRequest` | 채팅 요청 (message, session_id, chat_type 등) |
| `SearchRequest` | 검색 요청 (query, top_k 등) |

### 응답 모델

| 모델 | 설명 |
|------|------|
| `ChatResponse` | 채팅 응답 (answer, sources, similar_cases 등) |
| `AgencyRecommendation` | 추천 기관 정보 |
| `CaseReference` | 사례 참조 정보 |
| `LawReference` | 법령 참조 정보 |
| `CriteriaReference` | 분쟁해결기준 참조 정보 |
| `SimilarCases` | 유사 사례 모음 |
| `NodeTiming` | 노드 실행 시간 (debug 모드) |

## 의존성

| 함수 | 설명 |
|------|------|
| `get_retriever()` | Retriever 인스턴스 (요청별 DB 연결 관리) |
| `get_db_config()` | DB 연결 설정 |
| `get_embed_api_url()` | 임베딩 API URL |
| `get_retrieval_mode()` | 검색 모드 ('hybrid' 또는 'dense') |

## 유틸리티

### response_builder.py

`ChatResponse` 직렬화 헬퍼. 검색 결과, 인용, 유사 사례 등을 표준 응답 포맷으로 변환.

## 인증 체계

```
사용자 → /auth/google 또는 /auth/naver → OAuth Provider
                                              ↓
사용자 ← JWT 토큰 ← /auth/{provider}/callback
                         ↓
        이후 요청: Authorization: Bearer <JWT>
                         ↓
        /auth/me, /auth/verify → 토큰 검증
```

- **일반 사용자**: OAuth 로그인 → JWT 발급 → API 호출
- **관리자**: `/api/admin/login` → 관리자 JWT → Admin 엔드포인트 접근
