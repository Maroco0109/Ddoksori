# M3-3 workflow run 저장 구현 (계획서)

- 작성일: 2026-06-24
- 모듈: `M3-3` workflow run 저장 구현
- 선행: `M3-1` 인벤토리(`M3-1-observability-inventory-results.md`), `M3-2` 테이블 설계(`M3-2-workflow-runs-table-plan.md`, `005_workflow_runs.sql` 초안)
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §M3 (L115)
- 성격: **첫 코드 구현 모듈.** migration 적용 + `/chat` 라이브 저장 + 실제 검증. A/B **동작은 무변경**, 저장 훅만 추가(read-after-write 비침습).

## 0. 한 줄 요약

M3-2의 `005_workflow_runs.sql`을 실제 migration 파일로 추가해 **Ddoksori compose DB(5433)** 에 적용하고, **동기 `POST /chat`** 의 A·B 경로가 요청 1건을 `workflow_runs`에 **best-effort(비차단)** 로 저장하게 한다. RunPod pod를 띄워 **실제 A/B success run**을 한 건씩 발생시켜 row가 들어가는지 `SELECT`로 검증한다.

## 1. 범위

### 목표 (완료 기준 = roadmap L115)
- `005_workflow_runs.sql` migration 파일 추가 + compose DB 적용.
- 동기 `/chat`이 A success/error, B(early-return) 경로에서 `workflow_runs` row 1건 저장.
- 라이브 검증: A run·B run 각각 row 확인(`variant`, `status`, `total_time_ms` 포함).

### 비목표 (scope creep 차단)
- **스트리밍 `/chat/stream`(SSE) 계측** → M3-3-follow로 인계(아래 §6). 동일 패턴이라 후속에서 저비용.
- 자식 테이블(`workflow_steps`/`retrieval_events`/`llm_calls`/`guardrail_events`) = M3-4~M3-7.
- 조회 API = M3-8. 대시보드/시각화 = 범위 밖.
- A/B 파이프라인 **로직 변경**(라우팅·검색·프롬프트). 저장 훅만 추가.
- B의 실제 model/provider 캡처(M2-7R의 정적 `"variant-b"` 문제)는 M3-6 `llm_calls`에서. M3-3은 `variant='B'`만 기록.

## 2. 변경 대상 파일 (구현 시)

| 파일 | 변경 | 근거 |
| --- | --- | --- |
| `backend/app/database/migrations/005_workflow_runs.sql` | **신규** | M3-2 §4 초안을 그대로 파일화. 번호 005(004 다음) |
| `backend/app/observability/workflow_runs.py` | **신규** | `WorkflowRunDB` 접근 계층 + `save_workflow_run(...)` 헬퍼. `ConversationDB`(`supervisor/persistence/db.py`) 패턴 재사용 |
| `backend/app/observability/__init__.py` | **신규** | M3 관측 서브시스템 패키지(이후 step/retrieval/llm/guardrail 확장 지점) |
| `backend/app/api/chat.py` | 수정(저장 훅만) | 동기 `chat()`의 A success(L306 부근)·error(L340 부근), B early-return(L118 부근)에 best-effort 저장 호출 추가 |

> `backend/app/observability/` 신규 패키지를 두는 이유: M3-4~M3-7이 같은 도메인에서 자랄 자리. `persistence/`(대화 메모리)와 책임 분리.

## 3. 접근 계층 설계 (`WorkflowRunDB`)

`ConversationDB`와 동일 관례: `psycopg2`, 호출마다 연결 생성/종료, `asyncio.to_thread`로 async 래핑, `get_config().database`.

```python
# backend/app/observability/workflow_runs.py (구현 스케치 — 본 PR은 계획)
async def save_workflow_run(
    *,
    run_id: str,            # A: log_entry.request_id, B: 신규 uuid4
    variant: str,           # 'A' | 'B'
    query: str,
    status: str,            # 'success' | 'no_results' | 'error'
    session_id: str | None = None,
    chat_type: str | None = None,
    error_message: str | None = None,
    total_time_ms: float | None = None,
    clarified: bool | None = None,
    blocked: bool | None = None,
) -> None:
    """INSERT ... ON CONFLICT (run_id) DO NOTHING. 실패해도 예외를 삼킴(best-effort)."""
```

- **INSERT 멱등**: `ON CONFLICT (run_id) DO NOTHING` — 재시도/중복 호출 안전.
- **비차단(best-effort)**: 저장 실패가 `/chat` 응답을 절대 깨뜨리지 않게 `try/except + logger.warning`으로 격리. 관측이 UX를 저해하면 안 됨.

## 4. `/chat` wiring (동기 경로)

### A 경로 (MAS)
- run_id = `log_entry.request_id`(이미 `create_entry`로 생성, `chat.py:91`) → S3와 **동일 키 공유**(M3-1 표준).
- 필드 매핑(M3-1 §2 / M3-2 §2 출처):
  - `status`: 기존 `rag_logger.log_response(status=...)` 값 재사용(success/no_results/error).
  - `total_time_ms`: `rag_logger.finalize`가 쓰는 `log_entry.total_time_ms` 재사용.
  - `clarified`: `final_state` 또는 `LLMLog.has_sufficient_evidence`의 부정(명시 도출 규칙은 구현 시 확정).
  - `blocked`: `final_state.get("guardrail_blocked")`.
  - `session_id`, `chat_type`: `body`에서.
- 저장 시점: 기존 `rag_logger.save(log_entry)` **직후**(success L309 / error L344) 한 줄 추가 → S3 파일과 DB row가 같은 run_id로 짝.

### B 경로 (Agentic, early-return)
- 현재 `variant=="B"`는 L118에서 즉시 return → **저장 우회**가 M3-1이 지목한 최대 갭.
- 변경: `run_b` 호출을 **타이머로 감싸**(run_b 내부 타이밍 없음, 확인됨) `total_time_ms` 측정, `run_id = uuid4()` 생성 후 return **전에** `save_workflow_run(variant='B', ...)` 호출.
  - `status`: B는 `no_results` 개념이 옅음 → `blocked`면 'error' 성격이 아니라 정책 차단이므로 **'success'로 기록하되 `blocked=True`** (정책상 정상 완료). clarify도 `status='success', clarified=True`. 예외 발생 시에만 'error'. (최종 매핑 규칙은 구현 시 표로 고정.)
  - `clarified` = `b_result["clarified"]`, `blocked` = `b_result["blocked"]`.
  - `chat_type` = body.chat_type(있으면), 없으면 NULL.

> A/B 모두 **동일 `save_workflow_run` 인터페이스**를 통과 → 한 테이블에서 `variant`로 비교(모듈 목적).

## 5. 검증 절차 (라이브, 사용자 승인됨: pod + compose DB)

1. **DB 기동**: `docker compose up -d postgres` → `ddoksori_postgres`(호스트 5433) 헬스 확인.
2. **migration 적용**: `005_workflow_runs.sql`을 compose DB에 수동 실행(004 관례: 수동·멱등). `\d workflow_runs`로 테이블·인덱스·CHECK 확인.
3. **backend 기동**: M1-8 관례대로 compose 네트워크 DB 바인딩(`DB_HOST=postgres DB_PORT=5432` 컨테이너, 또는 호스트 `127.0.0.1:5433`). `/health`가 `database=connected`인지 확인.
4. **pod 기동**: RunPod EXAONE 4.5-33B(M2-2 baseline) 띄우고 backend provider 연결 확인.
5. **A run**: `POST /chat`(variant 미지정) 실제 질의 1건 → 200 + 답변.
6. **B run**: `POST /chat?variant=B`(또는 body.variant=B) 동일/유사 질의 1건 → 200.
7. **검증 쿼리**:
   ```sql
   SELECT run_id, variant, status, clarified, blocked,
          round(total_time_ms) AS ms, left(query, 30) AS q, started_at
   FROM workflow_runs ORDER BY started_at DESC LIMIT 10;
   ```
   기대: **variant='A' 1행 + variant='B' 1행**, 둘 다 `total_time_ms` 채워짐, A는 `status='success'`.
8. **비차단 확인**: (선택) DB를 잠깐 내린 상태로 `/chat` 1건 → 응답은 정상(200), 로그에 저장 실패 warning만. 관측이 UX를 안 깬다는 증거.

### 완료 기준 체크
- [ ] `005_workflow_runs.sql` 파일 존재 + compose DB 적용 로그.
- [ ] `/chat` A run → `workflow_runs`에 variant='A' row.
- [ ] `/chat` B run → variant='B' row.
- [ ] 저장 실패가 `/chat` 200 응답을 깨지 않음(best-effort) 증거.
- [ ] A/B 파이프라인 로직 diff 0(저장 훅·migration·신규 모듈만).

## 6. 후속 인계 (backlog, 구현 금지)
- **M3-3-follow**: 스트리밍 `/chat/stream` 3개 save 지점(success L697 / cancelled L722 / error L739)에 동일 `save_workflow_run` 적용. 프론트가 실제 쓰는 경로라 데이터 모수 확보용.
- **M3-6 인계**: B 실제 model/provider 캡처(정적 `"variant-b"` 대체)는 `llm_calls`에서.

## 7. Next gate → M3-4
`workflow_steps` 저장(node sequence + latency). 본 모듈의 `run_id`를 FK로 참조. A=S3 `node_timings`/S4 trace, B=`run_b` trace step.
