# M3-2 `workflow_runs` 최소 테이블 설계 (계획서 + migration 초안)

- 작성일: 2026-06-24
- 모듈: `M3-2` workflow run 최소 테이블 설계
- 선행: `M3-1` 인벤토리 결과 `docs/plans/modules/M3-1-observability-inventory-results.md`
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §M3 (L114)
- 성격: **설계 문서 + SQL 초안.** 실제 migration 적용·저장 코드(M3-3)는 범위 밖. A/B 코드 무변경, pod 불필요.

## 0. 한 줄 요약

요청 1건 = row 1개인 **가장 작은 영속화 단위** `workflow_runs` 하나만 설계한다. 컬럼은 M3-1이 source-of-truth로 지목한 **S3 `RAGLogEntry`** 필드에서 가져오고, A/B를 한 테이블에서 비교하기 위해 **`run_id`(=request_id) 표준 키 + `variant(A|B)` 컬럼**을 둔다. 리포의 기존 관례(수동 적용 idempotent raw SQL, `backend/app/database/migrations/NNN_*.sql`)를 그대로 따른다. 다음 migration 번호는 **005**.

## 1. 설계 원칙 (M3-1에서 인계)

1. **최소 단위부터**: 5개 테이블을 한 번에 만들지 않는다. `workflow_runs` 하나만. step/retrieval/llm/guardrail은 M3-4~M3-7에서 이 테이블을 FK로 참조.
2. **Source-of-truth = S3 `RAGLogEntry`** (`backend/app/common/logging/rag_logger.py:270-290`). 컬럼은 추측이 아니라 기존 dataclass 필드를 차용.
3. **A/B 공통 키 = `run_id`** = S3 `request_id`(uuid4, `rag_logger.py:346`). B는 현재 식별자가 없으므로 M3-3에서 동일 키를 부여(아래 §5 선결과제).
4. **`variant` 컬럼 필수**: A(MAS)·B(Agentic) 동일 스키마 흡수. M2-7R류 A/B 비교를 SQL로 재현하기 위한 핵심.
5. **리포 SQL 관례 준수**: `004_conversation_memory.sql`과 동일하게 — `CREATE TABLE IF NOT EXISTS`, `gen_random_uuid()`(pgcrypto), `TIMESTAMP DEFAULT NOW()`, `COMMENT ON`, `DO $$ ... IF NOT EXISTS` 가드 CHECK 제약, idempotent re-run 안전.

## 2. 컬럼 설계 + 출처 매핑 (정당화)

| 컬럼 | 타입 | 출처 (M3-1) | 비고 |
| --- | --- | --- | --- |
| `run_id` | `UUID PRIMARY KEY` | S3 `RAGLogEntry.request_id` (`rag_logger.py:278,346`) | A/B 공통 표준 키. uuid4. DEFAULT `gen_random_uuid()`(B 등 미부여 대비) |
| `variant` | `VARCHAR(8) NOT NULL` | M3-1 §2 (신규 식별 컬럼) | CHECK `IN ('A','B')`. A=MAS, B=variant_b |
| `session_id` | `VARCHAR(255)` (nullable) | S3 `InputLog.session_id` (`rag_logger.py:257`) | **하드 FK 미설정**(아래 §3 결정). 인덱스만 |
| `chat_type` | `VARCHAR(20)` (nullable) | S3 `InputLog.chat_type` (`rag_logger.py:258`) | dispute/general. B는 null 허용 |
| `query` | `TEXT NOT NULL` | S3 `RAGLogEntry.query` (`rag_logger.py:280`) | 사용자 쿼리 원문(분석의 핵심) |
| `status` | `VARCHAR(20) NOT NULL` | S3 `ResponseSummary.status` (`rag_logger.py:116`) | CHECK `IN ('success','no_results','error')`. 기본 'success' |
| `error_message` | `TEXT` (nullable) | S3 `ResponseSummary.error_message` (`rag_logger.py:117`) | 실패 사유 |
| `total_time_ms` | `DOUBLE PRECISION` (nullable) | S3 `RAGLogEntry.total_time_ms` (`rag_logger.py:288`) | 요청 전체 latency. 라이브 비교 지표 |
| `clarified` | `BOOLEAN` (nullable) | B `run_b` 결과 / A `LLMLog.has_sufficient_evidence` (`agent.py:117`, `rag_logger.py:101`) | clarification_rate 집계용. M2-7R 지표 |
| `blocked` | `BOOLEAN` (nullable) | B `run_b.blocked` / A `ControlState.guardrail_blocked` (`agent.py:113`, `control.py:99`) | guardrail 차단 여부(요약). 상세는 M3-7 `guardrail_events` |
| `started_at` | `TIMESTAMP DEFAULT NOW()` | S3 `RAGLogEntry.timestamp` (`rag_logger.py:279`) | 시작 시각 |
| `created_at` | `TIMESTAMP DEFAULT NOW()` | (운영) | row 삽입 시각 |

설계 노트:
- **`total_time_ms`/`clarified`/`blocked`/`status`는 요약 수치**다. 상세(node별 latency, chunk similarity, provider/model, guardrail reason)는 M3-4~7의 자식 테이블 몫. M3-2는 "run이 일어났다 + 결과 요약"만.
- B에서 즉시 못 채우는 컬럼(`chat_type`, `error_message` 등)은 **nullable**로 두어 A/B 비대칭을 스키마가 흡수.
- `model`/`provider`는 **여기 두지 않는다** — A는 LLM을 여러 번 호출할 수 있고(노드별) M3-6 `llm_calls`가 호출 단위로 기록하는 것이 정확. (B의 정적 `"variant-b"` 문자열 문제는 M3-3/M3-6에서 실제 spec 캡처로 해결.)

## 3. 설계 결정

- **D1. `session_id` 하드 FK 미설정.** `conversations.session_id`(`004_conversation_memory.sql:49`)는 memory backend=db일 때만 생성되고, B 경로·게스트·로깅 단독 시나리오에선 없을 수 있다. FK를 걸면 run 저장이 conversation 존재에 종속되어 영속화가 깨질 위험 → **느슨한 컬럼 + 인덱스**로 둔다(분석 join은 SQL에서 가능).
- **D2. `run_id` 타입 = UUID.** S3 request_id가 uuid4 문자열이므로 UUID 컬럼이 자연스럽다. DEFAULT `gen_random_uuid()`를 둬서 식별자 미부여 호출(B 초기)도 저장 가능.
- **D3. 요약 컬럼 최소화.** clarification_rate/guardrail/latency/status만 run 레벨에 둔다. retrieval 품질·token·node timing은 자식 테이블로 미룬다(M3 단계 분리 원칙).
- **D4. JSONB escape hatch 미도입(보류).** 초기엔 정형 컬럼만. 향후 분류 안 된 메타가 필요하면 M3-3 구현 시 `meta JSONB` 추가를 재검토(현 단계 over-engineering 회피).

## 4. Migration 초안 (`005_workflow_runs.sql` — 본 PR은 문서, 적용은 M3-3)

```sql
-- ============================================================
-- 005_workflow_runs.sql
-- Agent/RAG workflow 관측: 요청 단위 run 기록 (M3-2 설계, M3-3에서 적용)
--
-- 작성일: 2026-06-24
-- 설명: /chat 요청 1건 = row 1개. A(MAS)/B(Agentic) 공통.
--       상세(step/retrieval/llm/guardrail)는 후속 마이그레이션에서 FK 참조.
-- ⚠️ 주의: 수동 실행. DB 계정 권한 확인 후 적용.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant         VARCHAR(8)  NOT NULL,
    session_id      VARCHAR(255),
    chat_type       VARCHAR(20),
    query           TEXT        NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'success',
    error_message   TEXT,
    total_time_ms   DOUBLE PRECISION,
    clarified       BOOLEAN,
    blocked         BOOLEAN,
    started_at      TIMESTAMP   DEFAULT NOW(),
    created_at      TIMESTAMP   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_variant     ON workflow_runs(variant);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_session     ON workflow_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started     ON workflow_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status      ON workflow_runs(status);

-- 멱등 CHECK 제약 (004 패턴과 동일)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_workflow_runs_variant') THEN
        ALTER TABLE workflow_runs ADD CONSTRAINT check_workflow_runs_variant
            CHECK (variant IN ('A', 'B'));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_workflow_runs_status') THEN
        ALTER TABLE workflow_runs ADD CONSTRAINT check_workflow_runs_status
            CHECK (status IN ('success', 'no_results', 'error'));
    END IF;
END $$;

COMMENT ON TABLE workflow_runs IS 'Agent/RAG workflow 요청 단위 run 기록 (A/B 공통, M3-2)';
COMMENT ON COLUMN workflow_runs.run_id IS '요청 고유 ID (= RAG 로그 request_id, A/B 공통 키)';
COMMENT ON COLUMN workflow_runs.variant IS '아키텍처 변종 (A=MAS, B=Agentic)';
COMMENT ON COLUMN workflow_runs.session_id IS '프론트엔드 세션 ID (느슨한 참조, FK 아님)';
COMMENT ON COLUMN workflow_runs.chat_type IS '채팅 유형 (dispute, general; B는 NULL 가능)';
COMMENT ON COLUMN workflow_runs.query IS '사용자 쿼리 원문';
COMMENT ON COLUMN workflow_runs.status IS '결과 상태 (success, no_results, error)';
COMMENT ON COLUMN workflow_runs.total_time_ms IS '요청 전체 처리 시간 (밀리초)';
COMMENT ON COLUMN workflow_runs.clarified IS '단발 clarification 발생 여부 (clarification_rate 집계용)';
COMMENT ON COLUMN workflow_runs.blocked IS 'guardrail 차단 여부 요약 (상세는 guardrail_events)';

DO $$ BEGIN
    RAISE NOTICE '✓ 005_workflow_runs.sql: workflow_runs table ready';
END $$;
```

## 5. M3-3 선결과제 (M3-1 §3에서 인계, 저장 구현 전 반드시)

1. **B 영속화 훅**: `chat.py:118`의 `variant=="B"` early return이 `rag_logger`/`workflow_runs` 저장을 우회한다 → run 저장 경로를 추가해야 A/B 둘 다 기록된다.
2. **B `run_id` 부여**: `run_b`가 식별자를 만들지 않으므로 호출 측에서 run_id 생성·전달.
3. **A status 매핑**: A는 `ResponseSummary.status`를 이미 산출 → 그대로 매핑. clarified는 `has_sufficient_evidence`의 부정으로 도출(또는 명시 필드 확정은 M3-3).
4. **접근 계층 스타일**: 저장은 `ConversationDB`(`supervisor/persistence/db.py`) 패턴 재사용 — psycopg2 + `asyncio.to_thread`, 호출마다 연결 생성/종료, `get_config().database`.

## 6. 완료 기준 점검

- [x] `workflow_runs` **하나만** 설계(다른 4 테이블 미포함).
- [x] 각 컬럼이 M3-1 인벤토리 필드에 `파일:라인`으로 근거.
- [x] A/B 통합 키(`run_id`) + `variant` 컬럼 명시.
- [x] 리포 기존 SQL 관례(idempotent, COMMENT, CHECK 가드, gen_random_uuid) 준수.
- [x] B 영속화 등 M3-3 선결과제 인계.
- [x] 코드 diff 0(설계 문서). pod 미사용.

## 7. Next gate → M3-3

`005_workflow_runs.sql`을 실제 migration 파일로 추가 + `/chat` A·B 경로가 run 1건을 `workflow_runs`에 저장. §5 선결과제(B 훅·run_id·status 매핑·접근 계층)를 입력으로 사용. 완료기준: "`/chat` 1회가 `workflow_runs`에 저장"(roadmap L115).
