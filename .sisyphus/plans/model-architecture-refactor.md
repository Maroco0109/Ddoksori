# DDOKSORI Model Architecture Refactor

## Context

### Original Request
사용자가 DDOKSORI Multi-Agent System의 모델 아키텍처를 재구성하고자 함:
- Query Rewriter 제거 (코드는 _archive로 이동)
- 각 에이전트별 새로운 모델 할당
- RunPod vLLM 인프라 구축
- RDS 연결 및 Docker 레거시 정리
- E2E 테스트 환경 구축

### Interview Summary
**Key Discussions**:
- Query Rewriter: 완전 제거, `_archive/` 디렉토리로 이동
- Supervisor: GPT-5.1 (확인됨: OpenAI 모델 존재)
- Draft/Review Agent: gpt-4o
- Retrieval Agents: EXAONE-4.0-1.2B (확인됨: HuggingFace 모델 존재, vLLM 0.10.0+ 지원)
- HF Fallback: gpt-4.1-nano (확인됨: OpenAI 모델 존재)
- Embedding: text-embedding-3-large (1536d, 마트료시카)
- Docker: 볼륨 포함 전체 삭제 (RDS 사용)

**Research Findings**:
- GPT-5.1: OpenAI API에서 확인됨 - "The best model for coding and agentic tasks with configurable reasoning effort"
- gpt-4.1-nano: OpenAI API에서 확인됨 - "Fastest, most cost-efficient version of GPT-4.1"
- EXAONE-4.0-1.2B: HuggingFace에서 확인됨 - vLLM 0.10.0+ 공식 지원
- RDS 연결 정보: `dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com`
- 현재 Docker 상태: 레거시 컨테이너들 존재 (ddoksori_db, ddoksori_embedding 등)

### Metis Review
**Identified Gaps** (addressed):
- Query Rewriter 제거 시 `rewritten_query` 흐름: 각 Retrieval Agent 내부에서 Pre-retrieval LLM으로 대체
- 모델명 확인: GPT-5.1, gpt-4.1-nano, EXAONE-4.0-1.2B 모두 존재 확인됨
- Rollback 전략: Feature flag 기반 구현 (환경변수로 제어)

---

## Work Objectives

### Core Objective
DDOKSORI MAS 아키텍처를 새로운 모델 구성으로 전환하고, RDS 기반 운영 환경을 구축하여 E2E 테스트까지 완료한다.

### Concrete Deliverables
1. Query Rewriter 모듈 아카이브 및 제거
2. 새로운 모델 설정 (config.py + .env)
3. Retrieval Agent Pre-retrieval LLM 통합
4. Supervisor GPT-5.1 통합
5. Draft/Review Agent gpt-4o 업그레이드
6. RunPod vLLM 인프라 설정 가이드
7. Docker 레거시 정리 및 RDS 전환
8. E2E 테스트 통과

### Definition of Done
- [ ] `conda run -n dsr pytest backend/scripts/testing/ -m "not slow"` → 모든 테스트 통과
- [ ] `/chat` API 호출 시 응답 생성 성공
- [ ] RDS 연결 상태 확인: `curl localhost:8000/health` → `{"status": "ok"}`

### Must Have
- Query Rewriter 코드 `_archive/` 보존
- Fallback 체인 구현 (EXAONE → gpt-4.1-nano)
- 환경변수 기반 모델 전환 가능
- RDS 1536d 임베딩 호환

### Must NOT Have (Guardrails)
- 새 모델이 없을 때 silent failure 금지 (명시적 에러)
- .env 파일에 실제 API 키 노출 (예제 키만)
- Docker 볼륨 데이터 무단 삭제 (확인 프롬프트 필수)
- Query Rewriter 코드 영구 삭제

---

## Verification Strategy (MANDATORY)

### Test Decision
- **Infrastructure exists**: YES (pytest 구성됨)
- **User wants tests**: TDD / Tests-after (기존 테스트 유지 + 신규 추가)
- **Framework**: pytest (conda run -n dsr)

### Manual QA Verification
각 Phase 완료 후:
- Backend API: `curl` 요청으로 응답 확인
- LLM 연결: health check 엔드포인트
- 로그 확인: `DEBUG=True` 환경에서 모델 호출 로그

---

## Task Flow

```
Phase 1 (Query Rewriter 제거)
    ↓
Phase 2 (Config 구조 확장)
    ↓
Phase 3 (Retrieval Agent Pre-retrieval)
    ↓
Phase 4 (Supervisor GPT-5.1)
    ↓
Phase 5 (Draft/Review gpt-4o)
    ↓
Phase 6 (Embedding 전환)
    ↓
Phase 7 (Infrastructure Setup)
    ↓
Phase 8 (E2E Testing)
```

## Parallelization

| Group | Tasks | Reason |
|-------|-------|--------|
| A | 3, 4, 5 | 독립적인 에이전트 수정 |
| B | 7 | 인프라 설정 (코드 변경과 독립) |

| Task | Depends On | Reason |
|------|------------|--------|
| 3 | 1, 2 | Query Rewriter 제거 후 대체 로직 필요, Config 구조 필요 |
| 4, 5 | 2 | Config 구조 필요 |
| 6 | 2 | Embedding 설정 Config에 의존 |
| 8 | 1-7 | 모든 변경 완료 후 E2E 테스트 |

---

## TODOs

- [ ] 1. Query Rewriter 아카이브 및 제거

  **What to do**:
  - `backend/app/llm/query_rewriter.py` → `backend/_archive/llm/query_rewriter.py` 이동
  - `backend/app/llm/__init__.py`에서 `get_query_rewriter` export 제거
  - `backend/app/agents/query_analysis/agent.py`에서 Query Rewriter 호출 코드 제거
  - `QUERY_REWRITE_ENABLED` 환경변수 관련 코드 정리
  - 관련 테스트 파일 아카이브: `test_query_rewriter.py` → `_archive/`

  **Must NOT do**:
  - 파일 영구 삭제 금지 (반드시 _archive로 이동)
  - `rewritten_query` 필드 자체 제거 금지 (Retrieval Agent에서 사용 예정)

  **Parallelizable**: NO (다른 작업의 기반)

  **References**:
  - `backend/app/llm/query_rewriter.py` - 아카이브 대상 파일 (전체)
  - `backend/app/llm/__init__.py:15-20` - export 제거 위치
  - `backend/app/agents/query_analysis/agent.py:46-54` - import 제거
  - `backend/app/agents/query_analysis/agent.py:944-963` - LLM rewrite 호출 코드 제거
  - `backend/scripts/testing/orchestrator/test_query_rewriter.py` - 테스트 아카이브

  **Acceptance Criteria**:
  - [ ] `backend/_archive/llm/query_rewriter.py` 파일 존재
  - [ ] `from app.llm import get_query_rewriter` 시 ImportError 발생
  - [ ] `conda run -n dsr pytest backend/scripts/testing/query_analysis/ -v` → PASS
  - [ ] Query Analysis 노드가 LLM 없이 규칙 기반으로만 동작 확인

  **Commit**: YES
  - Message: `refactor(llm): archive query_rewriter module for MAS transition`
  - Files: `backend/app/llm/`, `backend/app/agents/query_analysis/`, `backend/_archive/`

---

- [ ] 2. Config 구조 확장 (모델별 설정 + RDS READ_ONLY 계정)

  **What to do**:
  - `backend/app/common/config.py`에 새로운 설정 클래스 추가:
    ```python
    class ModelConfig(BaseSettings):
        """에이전트별 모델 중앙 관리"""
        model_config = SettingsConfigDict(env_prefix="MODEL_")
        
        supervisor: str = Field(default="gpt-5.1")
        draft_agent: str = Field(default="gpt-4o")
        review_agent: str = Field(default="gpt-4o")
        retrieval_llm: str = Field(default="LGAI-EXAONE/EXAONE-4.0-1.2B")
        retrieval_fallback: str = Field(default="gpt-4.1-nano")
    
    class PortConfig(BaseSettings):
        """서비스별 포트 중앙 관리"""
        model_config = SettingsConfigDict(env_prefix="PORT_")
        
        exaone_vllm: int = Field(default=19010)
    ```
  - `AppConfig`에 `models: ModelConfig` 및 `ports: PortConfig` 추가
  - `.env.example` 업데이트:
    - ModelConfig/PortConfig 환경변수 추가
    - **RDS READ_ONLY 계정 설정 섹션 추가**:
      ```bash
      # =============================================================================
      # RDS 테스트 환경 설정 (READ_ONLY 계정)
      # =============================================================================
      # 테스트 환경에서 RDS 접근 시 READ_ONLY 계정 사용
      # - 프로덕션 데이터 보호
      # - Integration 테스트에 사용
      #
      # READ_ONLY 계정 사용법:
      #   1. 기본 DB_USER/DB_PASSWORD 대신 아래 변수 설정
      #   2. pytest -m "integration" 실행 시 자동 사용
      #
      DB_TEST_HOST=dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com
      DB_TEST_USER=readonly_user
      DB_TEST_PASSWORD=your_readonly_password
      DB_TEST_NAME=ddoksori
      
      # 테스트 시 RDS 사용 여부 (true | false)
      # - true: RDS READ_ONLY 계정으로 integration 테스트
      # - false: 로컬 Docker DB 또는 mock 사용 (기본값)
      USE_RDS_FOR_TESTS=false
      ```
  - `backend/scripts/testing/conftest.py`에 RDS 테스트 연결 fixture 추가

  **Must NOT do**:
  - 기존 `LLMConfig`, `ExaoneConfig` 삭제 금지 (하위 호환성)
  - READ_ONLY 계정에 WRITE 권한 부여 금지

  **Parallelizable**: NO (Phase 3-6의 기반)

  **References**:
  - `backend/app/common/config.py:124-177` - 기존 LLMConfig, ExaoneConfig 구조 참고
  - `backend/app/common/config.py:426-482` - AppConfig 구조
  - `backend/.env.example` - 환경변수 템플릿
  - `backend/scripts/testing/conftest.py:265` - 기존 integration marker

  **Acceptance Criteria**:
  - [ ] `from app.common.config import get_config; config = get_config(); print(config.models.supervisor)` → `gpt-5.1`
  - [ ] `.env.example`에 `MODEL_SUPERVISOR`, `MODEL_DRAFT_AGENT` 등 문서화
  - [ ] `.env.example`에 `DB_TEST_*` 변수 및 `USE_RDS_FOR_TESTS` 문서화
  - [ ] `conda run -n dsr python -c "from app.common.config import get_config; print(get_config().models)"` → 정상 출력
  - [ ] `USE_RDS_FOR_TESTS=true` 설정 시 `pytest -m integration` 실행 가능

  **Commit**: YES
  - Message: `feat(config): add ModelConfig, PortConfig, and RDS test credentials support`
  - Files: `backend/app/common/config.py`, `backend/.env.example`, `backend/scripts/testing/conftest.py`

---

- [ ] 3. Retrieval Agent Pre-retrieval LLM 통합

  **What to do**:
  - `backend/app/agents/retrieval/base_retrieval_agent.py`에 Pre-retrieval LLM 로직 추가:
    - EXAONE 클라이언트 초기화 (config.models.retrieval_llm)
    - `_rewrite_query_for_domain()` 메서드 추가 (도메인 특화 쿼리 변환)
    - Fallback: EXAONE 실패 시 gpt-4.1-nano 호출
    - Fallback 2: 둘 다 실패 시 원본 쿼리 사용
  - 4개 Retrieval Agent 각각에 도메인 특화 프롬프트 설정:
    - `law_agent.py`: 법률 용어 → 법령 검색 쿼리
    - `criteria_agent.py`: 일상어 → 분쟁해결기준 쿼리
    - `case_agent.py`: 문제 상황 → 유사 사례 쿼리
    - `counsel_agent.py`: 구어체 → 상담 사례 쿼리

  **Must NOT do**:
  - 동기(sync) 호출로 전체 파이프라인 블로킹 금지 (async 유지)
  - 타임아웃 없는 LLM 호출 금지 (3초 타임아웃)

  **Parallelizable**: YES (4, 5와 병렬 가능 - 단, 2 완료 후)

  **References**:
  - `backend/app/agents/retrieval/base_retrieval_agent.py:84` - `rewritten_query` 소비 위치
  - `backend/app/agents/retrieval/law_agent.py` - 법령 에이전트 구조
  - `backend/app/llm/exaone_client.py` - 기존 EXAONE 클라이언트 패턴
  - `backend/app/agents/answer_generation/fallback.py:32-33` - Fallback 체인 패턴 참고

  **Acceptance Criteria**:
  - [ ] `LawRetrievalAgent`가 EXAONE으로 쿼리 변환 수행 (로그 확인)
  - [ ] EXAONE 타임아웃 시 gpt-4.1-nano fallback 동작
  - [ ] 모든 LLM 실패 시 원본 쿼리로 검색 진행
  - [ ] `conda run -n dsr pytest backend/scripts/testing/retrieval/ -v` → PASS

  **Commit**: YES
  - Message: `feat(retrieval): add pre-retrieval LLM query rewriting with EXAONE`
  - Files: `backend/app/agents/retrieval/`

---

- [ ] 4. Supervisor GPT-5.1 통합

  **What to do**:
  - `backend/app/orchestrator/nodes/supervisor.py` 수정:
    - `SupervisorNode.__init__()`: config.models.supervisor 모델 사용
    - OpenAI API 호출 클라이언트 추가 (langchain-openai)
    - Fallback 체인: GPT-5.1 → Claude 3.5 Sonnet → Rule-based
  - 새로운 `SupervisorLLMClient` 클래스 생성 (backend/app/llm/supervisor_client.py)

  **Must NOT do**:
  - 기존 Rule-based fallback 로직 제거 금지
  - 타임아웃 5초 초과 금지

  **Parallelizable**: YES (3, 5와 병렬 가능)

  **References**:
  - `backend/app/orchestrator/nodes/supervisor.py:92-110` - 현재 LLM 초기화 위치
  - `backend/app/orchestrator/nodes/supervisor.py:176-230` - 프롬프트 구조
  - `backend/app/orchestrator/nodes/supervisor.py:335-391` - Rule-based fallback

  **Acceptance Criteria**:
  - [ ] Supervisor가 GPT-5.1로 의사결정 수행 (로그 확인: "LLM 결정:")
  - [ ] GPT-5.1 실패 시 Sonnet fallback 동작
  - [ ] 모든 LLM 실패 시 Rule-based fallback 동작
  - [ ] `conda run -n dsr pytest backend/scripts/testing/orchestrator/test_supervisor.py -v` → PASS

  **Commit**: YES
  - Message: `feat(supervisor): integrate GPT-5.1 with Sonnet fallback`
  - Files: `backend/app/orchestrator/nodes/supervisor.py`, `backend/app/llm/supervisor_client.py`

---

- [ ] 5. Draft/Review Agent gpt-4o 업그레이드

  **What to do**:
  - `backend/app/agents/answer_generation/tools/generator.py` 수정:
    - 기본 모델을 `gpt-4o`로 변경 (config.models.draft_agent 사용)
    - Fallback 체인 업데이트: gpt-4o → gpt-4o-mini → rule_based
  - `backend/app/agents/legal_review/llm_reviewer.py` 수정:
    - 기본 모델을 `gpt-4o`로 변경 (config.models.review_agent 사용)
  - `backend/app/agents/answer_generation/fallback.py` Fallback 체인 업데이트

  **Must NOT do**:
  - rule_based fallback 제거 금지
  - 기존 테스트 케이스 삭제 금지

  **Parallelizable**: YES (3, 4와 병렬 가능)

  **References**:
  - `backend/app/agents/answer_generation/tools/generator.py:83-89` - 모델 초기화
  - `backend/app/agents/answer_generation/fallback.py:32-33` - Fallback 체인 정의
  - `backend/app/agents/legal_review/llm_reviewer.py:269-273` - Review 모델 설정

  **Acceptance Criteria**:
  - [ ] 답변 생성 시 `gpt-4o` 사용 확인 (로그: "model: gpt-4o")
  - [ ] 법률 검토 시 `gpt-4o` 사용 확인
  - [ ] Fallback 체인 동작: gpt-4o → gpt-4o-mini → rule_based
  - [ ] `conda run -n dsr pytest backend/scripts/testing/generation/ -v` → PASS
  - [ ] `conda run -n dsr pytest backend/scripts/testing/legal_review/ -v` → PASS

  **Commit**: YES
  - Message: `feat(agents): upgrade draft and review agents to gpt-4o`
  - Files: `backend/app/agents/answer_generation/`, `backend/app/agents/legal_review/`

---

- [ ] 6. Embedding text-embedding-3-large 전환

  **What to do**:
  - `backend/.env` 수정:
    ```
    USE_OPENAI_EMBEDDING=true
    EMBEDDING_MODEL=text-embedding-3-large
    EMBEDDING_DIMENSION=1536
    ```
  - `backend/app/agents/retrieval/tools/embedding_client.py` 검증:
    - 이미 1536d 지원 확인 (코드 리뷰로 확인됨)
  - RDS 스키마 호환성 확인 (이미 1536d)

  **Must NOT do**:
  - KURE-v1 관련 코드 삭제 금지 (Feature flag로 전환 가능 유지)

  **Parallelizable**: YES (다른 Phase와 독립)

  **References**:
  - `backend/app/agents/retrieval/tools/embedding_client.py:45` - 모델 설정
  - `backend/.env:22-24` - 현재 임베딩 설정
  - `backend/.env:152-162` - OpenAI 임베딩 설정 문서

  **Acceptance Criteria**:
  - [ ] `USE_OPENAI_EMBEDDING=true` 설정 확인
  - [ ] 임베딩 API 호출 시 `text-embedding-3-large` 사용 (로그 확인)
  - [ ] 검색 결과 정상 반환 (1536d 벡터 호환)
  - [ ] `curl localhost:8000/search -d '{"query": "환불"}' | jq '.results | length'` → 0보다 큼

  **Commit**: YES
  - Message: `feat(embedding): switch to text-embedding-3-large (1536d)`
  - Files: `backend/.env`

---

- [ ] 7. Infrastructure Setup (RunPod, API Keys, Health Checks)

  **What to do**:

  ### 7.1 RunPod vLLM 설정 가이드 작성
  - `docs/infrastructure/runpod-vllm-setup.md` 생성:
    ```markdown
    # RunPod vLLM Setup for EXAONE-4.0-1.2B
    
    ## Prerequisites
    - RunPod 계정
    - GPU Pod: RTX 4090 (24GB) 이상 권장
    
    ## vLLM Server 시작
    ```bash
    # RunPod Pod 내에서 실행
    pip install vllm>=0.10.0
    
    vllm serve LGAI-EXAONE/EXAONE-4.0-1.2B \
      --port 9010 \
      --enable-auto-tool-choice \
      --tool-call-parser hermes \
      --reasoning-parser deepseek_r1
    ```
    
    ## SSH 터널링 (로컬 개발용)
    ```bash
    ssh -L 19010:localhost:9010 root@<pod-ip> -p <pod-port>
    ```
    
    ## Health Check
    ```bash
    curl http://localhost:19010/health
    # Expected: {"status": "ok"}
    ```
    ```

  ### 7.2 .env 업데이트
  ```bash
  # === NEW MODEL CONFIGURATION ===
  # Supervisor
  MODEL_SUPERVISOR=gpt-5.1
  MODEL_SUPERVISOR_FALLBACK=claude-3-5-sonnet-20241022
  
  # Draft & Review Agents
  MODEL_DRAFT_AGENT=gpt-4o
  MODEL_REVIEW_AGENT=gpt-4o
  
  # Retrieval Agents (EXAONE via RunPod vLLM)
  MODEL_RETRIEVAL_LLM=LGAI-EXAONE/EXAONE-4.0-1.2B
  MODEL_RETRIEVAL_FALLBACK=gpt-4.1-nano
  EXAONE_RUNPOD_URL=http://localhost:19010/v1
  
  # Embedding
  USE_OPENAI_EMBEDDING=true
  EMBEDDING_MODEL=text-embedding-3-large
  EMBEDDING_DIMENSION=1536
  
  # Port Configuration
  PORT_EXAONE_VLLM=19010
  ```

  ### 7.3 API Keys 확인
  필요한 API Keys (이미 .env에 존재 확인):
  - `OPENAI_API_KEY`: GPT-5.1, gpt-4o, gpt-4.1-nano, text-embedding-3-large
  - `ANTHROPIC_API_KEY`: Claude 3.5 Sonnet (Supervisor fallback)
  - `HF_TOKEN`: EXAONE 모델 다운로드 (vLLM)

  ### 7.4 Health Check 엔드포인트 추가
  - `backend/app/api/health.py`에 LLM health check 추가:
    - `/health/llm/supervisor` - GPT-5.1 연결 확인
    - `/health/llm/exaone` - EXAONE vLLM 연결 확인
    - `/health/embedding` - OpenAI Embedding 연결 확인

  **Must NOT do**:
  - 실제 API 키를 .env.example에 노출 금지
  - RunPod Pod 자동 시작 스크립트 포함 금지 (수동 설정)

  **Parallelizable**: YES (코드 변경과 독립적으로 문서/설정 가능)

  **References**:
  - `backend/.env` - 현재 환경 설정
  - `backend/app/api/health.py` - 기존 health check
  - HuggingFace EXAONE-4.0-1.2B 페이지의 vLLM 섹션

  **Acceptance Criteria**:
  - [ ] `docs/infrastructure/runpod-vllm-setup.md` 파일 존재
  - [ ] `.env`에 새로운 MODEL_* 환경변수 설정됨
  - [ ] `curl localhost:8000/health` → `{"status": "ok", "database": "connected"}`
  - [ ] `curl localhost:8000/health/llm/supervisor` → `{"status": "ok", "model": "gpt-5.1"}`
  - [ ] (RunPod 연결 시) `curl localhost:8000/health/llm/exaone` → `{"status": "ok"}`

  **Commit**: YES
  - Message: `docs(infra): add RunPod vLLM setup guide and health checks`
  - Files: `docs/infrastructure/`, `backend/app/api/health.py`, `backend/.env`

---

- [ ] 8. Docker Cleanup & E2E Testing

  **What to do**:

  ### 8.1 Docker 레거시 정리
  ```bash
  # 1. 현재 Docker 상태 확인
  docker ps -a
  docker volume ls
  
  # 2. 레거시 컨테이너 및 볼륨 삭제 (확인 후)
  docker compose down -v
  
  # 3. 삭제 확인
  docker ps -a  # 컨테이너 없음
  docker volume ls  # ddoksori 관련 볼륨 없음
  ```

  ### 8.2 RDS 연결 확인 (READ_ONLY 계정 사용)
  ```bash
  # .env에 READ_ONLY 계정 설정:
  # DB_TEST_HOST=dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com
  # DB_TEST_USER=readonly_user  
  # DB_TEST_PASSWORD=your_readonly_password
  # USE_RDS_FOR_TESTS=true
  
  # READ_ONLY 연결 테스트
  conda run -n dsr python -c "
  import os
  import psycopg2
  
  # READ_ONLY 계정으로 연결
  conn = psycopg2.connect(
      host=os.getenv('DB_TEST_HOST'),
      user=os.getenv('DB_TEST_USER'),
      password=os.getenv('DB_TEST_PASSWORD'),
      dbname=os.getenv('DB_TEST_NAME', 'ddoksori'),
      port=5432
  )
  print('RDS READ_ONLY Connected:', conn.status)
  
  # SELECT 가능 확인
  cur = conn.cursor()
  cur.execute('SELECT COUNT(*) FROM dispute_cases')
  print('Dispute cases count:', cur.fetchone()[0])
  
  conn.close()
  "
  ```

  ### 8.3 Backend 실행
  ```bash
  cd backend
  conda run -n dsr uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  ```

  ### 8.4 Frontend 실행
  ```bash
  cd frontend
  npm install
  npm run dev  # http://localhost:5173
  ```

  ### 8.5 E2E 테스트 실행 (RDS READ_ONLY 계정 활용)
  ```bash
  # Unit 테스트 (DB 불필요)
  conda run -n dsr pytest backend/scripts/testing/ -m "unit" -v
  
  # Integration 테스트 (RDS READ_ONLY 계정 사용)
  # .env에 USE_RDS_FOR_TESTS=true 설정 필요
  USE_RDS_FOR_TESTS=true conda run -n dsr pytest backend/scripts/testing/ -m "integration" -v
  
  # E2E 테스트 (RDS 연결)
  USE_RDS_FOR_TESTS=true conda run -n dsr pytest backend/scripts/testing/orchestrator/test_e2e_queries.py -v
  
  # API 테스트 (Backend가 RDS에 연결된 상태에서)
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "노트북 환불 가능한가요?", "session_id": "test-123"}'
  ```
  
  **RDS READ_ONLY 계정 테스트 확인 사항**:
  - SELECT 쿼리만 허용되는지 확인
  - INSERT/UPDATE/DELETE 시도 시 Permission denied 발생 확인
  - 프로덕션 데이터 무결성 보장

  ### 8.6 수동 E2E 검증
  1. 브라우저에서 `http://localhost:5173` 접속
  2. 채팅 인터페이스에서 테스트 쿼리 입력:
     - "안녕하세요" → 일반 대화 응답
     - "노트북 환불 받고 싶어요" → 분쟁 상담 응답 (출처 포함)
     - "전자상거래법 17조가 뭐예요?" → 법령 정보 응답
  3. 각 응답에서 확인:
     - 응답 시간 < 5초
     - 출처 표시 존재
     - 금지 표현 없음

  **Must NOT do**:
  - 사용자 확인 없이 Docker 볼륨 삭제 금지
  - RDS에 테스트 데이터 오염 금지

  **Parallelizable**: NO (모든 Phase 완료 후 진행)

  **References**:
  - `docker-compose.yml` - Docker 구성
  - `backend/scripts/testing/orchestrator/test_e2e_queries.py` - E2E 테스트
  - `frontend/` - Frontend 코드

  **Acceptance Criteria**:
  - [ ] `docker ps -a | grep ddoksori` → 결과 없음
  - [ ] `docker volume ls | grep ddoksori` → 결과 없음 (postgres_data, cloudbeaver_data 삭제됨)
  - [ ] Backend 서버 실행: `curl localhost:8000/health` → `{"status": "ok"}`
  - [ ] Frontend 서버 실행: 브라우저에서 `localhost:5173` 접속 가능
  - [ ] `conda run -n dsr pytest backend/scripts/testing/ -m "not slow" -v` → PASS
  - [ ] 수동 E2E: 분쟁 질의 시 출처 포함된 응답 생성

  **Commit**: YES
  - Message: `test(e2e): verify full stack with RDS and new model configuration`
  - Files: 없음 (테스트 실행만)

---

## Commit Strategy

| After Task | Message | Files | Verification |
|------------|---------|-------|--------------|
| 1 | `refactor(llm): archive query_rewriter module` | `backend/app/llm/`, `backend/_archive/` | `pytest query_analysis/` |
| 2 | `feat(config): add ModelConfig and PortConfig` | `backend/app/common/config.py` | python import test |
| 3 | `feat(retrieval): add pre-retrieval LLM` | `backend/app/agents/retrieval/` | `pytest retrieval/` |
| 4 | `feat(supervisor): integrate GPT-5.1` | `backend/app/orchestrator/nodes/` | `pytest test_supervisor.py` |
| 5 | `feat(agents): upgrade to gpt-4o` | `backend/app/agents/` | `pytest generation/ legal_review/` |
| 6 | `feat(embedding): switch to text-embedding-3-large` | `backend/.env` | search API test |
| 7 | `docs(infra): add RunPod setup guide` | `docs/`, `backend/app/api/health.py` | health check |
| 8 | N/A (테스트만) | N/A | E2E test pass |

---

## Success Criteria

### Verification Commands
```bash
# 전체 테스트
conda run -n dsr pytest backend/scripts/testing/ -m "not slow" -v
# Expected: All tests pass

# Health check
curl localhost:8000/health
# Expected: {"status": "ok", "database": "connected"}

# Chat API
curl -X POST localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "환불", "session_id": "test"}'
# Expected: 응답 생성 (draft_answer, sources 포함)
```

### Final Checklist
- [ ] Query Rewriter 코드가 `_archive/`에 보존됨
- [ ] 모든 에이전트가 새로운 모델 사용 (로그로 확인)
- [ ] Fallback 체인이 정상 동작
- [ ] RDS 연결 정상
- [ ] Docker 레거시 컨테이너/볼륨 삭제됨
- [ ] E2E 테스트 통과
- [ ] Frontend에서 정상 대화 가능
