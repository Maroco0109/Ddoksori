# M3-3 workflow run 저장 구현 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M3-3` workflow run 저장 구현
- 계획서: `docs/plans/modules/M3-3-workflow-run-store-plan.md`
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §M3 (L115)
- 성격: 첫 코드 구현 + 라이브 검증. A/B 동작 무변경(저장 훅만 추가).

## 0. 한 줄 결론

`005_workflow_runs.sql`을 적용하고 동기 `POST /chat`의 A·B 경로에 best-effort 저장 훅을 추가했다. **실제 `/chat`을 통해 A success / B success / B clarify / A error 행이 `workflow_runs`에 저장됨을 라이브로 검증**했고, 저장 실패가 응답을 깨지 않음(non-blocking)도 확인했다. M3-1이 지목한 **B 미영속 갭이 해소**됐다.

## 1. 구현 내용

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/005_workflow_runs.sql` | 신규 (M3-2 §4 초안 파일화) |
| `backend/app/observability/__init__.py` | 신규 (관측 서브시스템 패키지) |
| `backend/app/observability/workflow_runs.py` | 신규 (`WorkflowRunDB` + best-effort `save_workflow_run`) |
| `backend/app/api/chat.py` | 동기 `/chat` A success/error + B early-return에 저장 훅 (3곳) |

- `save_workflow_run`: `INSERT ... ON CONFLICT (run_id) DO NOTHING`, 실패 시 예외 삼킴(`try/except`→warning).
- A: `run_id = log_entry.request_id`(S3 로그와 공유). B: `run_id = uuid4()`, latency는 호출측에서 측정.
- B의 blocked/clarify는 정책상 정상 완료 → `status='success'` + 별도 플래그.

## 2. 라이브 검증 환경 (사용자 결정 반영)

| 항목 | 값 | 비고 |
| --- | --- | --- |
| 검증 DB | **5432 소스 DB** (`data_collection_snippets`, role=postgres, db=ddoksori, `vector_chunks` 40,285행) | compose 5433 볼륨은 superuser role이 깨져 접속 불가 → 사용자 결정으로 5432 사용. 5433 복구는 M3-3 범위 밖 |
| LLM | RunPod EXAONE-4.5-33B, SSH 터널 `localhost:19080` → 컨테이너 `host.docker.internal:19080` | A success/B success 생성에 사용 |
| backend | `ddoksori_backend` 컨테이너(worktree 코드 마운트), `/health` database=connected | |
| 임베딩 | OpenAI text-embedding-3-large | B 게이트 검색 |

### 환경 워크어라운드 (코드 아님, 로컬 `.env` 문제)
- 로컬 `.env` 9–14행이 shell `export` 잔재(트레일링 ` \`)로 깨져 `ENABLE_EMBEDDING_CACHE='false \'` → RedisConfig bool 검증 실패. compose override에서 클린 값으로 교정.
- `variant_b/tools.py`는 `EVAL_DB_*`(기본 localhost)로 연결 → 컨테이너용 `EVAL_DB_HOST=host.docker.internal`로 지정.
- 위 두 가지는 M3-3 코드와 무관한 로컬 환경 설정 이슈(보고용).

## 3. 검증 결과 (실제 `workflow_runs` 행)

```
 variant | status  | clarified | blocked |  ms   |             query(요약)
---------+---------+-----------+---------+-------+---------------------------------
 B       | success | f         | f       | 10547 | 인터넷으로 구매한 운동화 ... 환불   (ReAct)
 A       | success | f         | f       | 14469 | 온라인으로 산 신발 ... 환불 요청    (MAS)
 B       | success | t         | f       |  3067 | 도와주세요                         (clarify, pod 불필요)
 A       | error   |           |         |  2062 | 도와주세요                         (변종 DB 오류 경로)
 A       | error   |           |         |  6495 | 안녕 그냥 물어보고 ...
```

| 검증 항목 | 결과 |
| --- | --- |
| migration 005 적용 (테이블/인덱스/CHECK) | ✅ `\d workflow_runs` 확인 |
| `/chat` A success → `variant='A', status='success'` | ✅ ms=14469, 전자상거래법 제17조 근거 답변 |
| `/chat` B success(ReAct) → `variant='B', status='success'` | ✅ ms=10547, model=variant-b |
| `/chat` B clarify(pod 불필요) → `clarified=true` | ✅ ms=3067 |
| best-effort 비차단 (테이블 제거 후 `/chat`) | ✅ HTTP 200 유지, 로그 `save failed (non-blocking)` 경고만 |
| A/B를 `variant`로 분리 집계 가능 (모듈 목적) | ✅ 한 테이블에서 A/B 비교 |

**완료기준 "/chat 1회가 workflow_runs에 저장"(roadmap L115) 충족.**

## 4. 발견 / 후속 (backlog)

1. **B 예외 시 variant 오라벨**: B가 게이트 단계에서 예외를 던지면 동기 `/chat`의 외부 `except`로 떨어져 **`variant='A', status='error'`로 기록**된다(위 A/error 2건이 그 사례 — `variant_b`가 EVAL_DB localhost를 봐서 발생). 행은 남지만 라벨이 틀림. → **M3-3-follow**: B 호출을 자체 `try`로 감싸 에러도 `variant='B'`로 라벨링.
2. **M3-3-follow**: 스트리밍 `/chat/stream` 3개 save 지점에 동일 훅 적용(프론트 실사용 경로).
3. **M3-6 인계**: B 실제 model/provider 캡처(정적 `"variant-b"`/`model` 라벨 대체)는 `llm_calls`에서.

## 5. Next gate → M3-4

`workflow_steps` 저장(node sequence + latency). 본 모듈의 `run_id`를 FK로 참조. A=S3 `node_timings`/S4 trace, B=`run_b` trace step.
