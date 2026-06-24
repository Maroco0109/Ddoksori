# M3-5 retrieval event 저장 (계획서 + migration 초안)

- 작성일: 2026-06-24
- 모듈: `M3-5` retrieval event 저장 (RAG 결과 품질)
- 선행: `M3-1` 인벤토리, `M3-2~M3-4` (`workflow_runs`/`workflow_steps`, `run_id` 표준, category 매핑, B 계측 패턴)
- 상위 계획: §M3 (L117)
- 성격: **설계 문서 + `007_retrieval_events.sql` 초안.** 실제 적용·저장 코드·라이브 검증은 M3-5 구현(후속). A 무변경, B는 per-search 계측만 추가.

## 0. 한 줄 요약

run 1건의 **검색 호출들**을 `retrieval_events` N행으로 저장한다(검색 호출 1회 = 1행). 각 행은 `source`·`query`·`top_k`·`result_count`·`max/avg_similarity` + **top-k의 `(chunk_id, similarity, rank)`를 `top_chunks` JSONB**로 담아 retrieval 품질(nDCG 등)을 SQL로 분석 가능하게 한다. A는 `final_state["retrieval"]` 4섹션을 매핑, **B는 `variant_b`에 per-search 계측을 추가**(gate + 각 tool 검색의 chunk·cosine)해 A와 동등한 retrieval_events를 확보한다.

## 1. 범위

### 목표 (완료 기준 = roadmap L117)
- `007_retrieval_events.sql` 설계(FK→`workflow_runs`).
- A·B 검색 호출별 top-k / result count / similarity 저장 → **조회 가능**.
- `top_chunks` JSONB로 chunk별 similarity·rank 보존(retrieval 품질 분석).

### 비목표
- 실제 적용·저장 코드·라이브 검증 = M3-5 **구현**(후속 PR).
- chunk별 **독립 테이블**(per-chunk row) — JSONB로 충분, 분리는 over-engineering.
- LLM 토큰/provider = M3-6, guardrail 상세 = M3-7, 조회 API = M3-8.
- 스트리밍 `/chat/stream`, A/B 검색 **로직** 변경(B는 계측만, 검색 결과 무변경).

## 2. 컬럼 설계 + 출처 매핑

| 컬럼 | 타입 | 출처 | 비고 |
| --- | --- | --- | --- |
| `event_id` | `UUID PK DEFAULT gen_random_uuid()` | (생성) | |
| `run_id` | `UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE` | M3-3 | run 종속 |
| `seq` | `INTEGER NOT NULL` | 검색 호출 순서 | run 내 retrieval 순번 |
| `source` | `VARCHAR(16) NOT NULL` | A 섹션 / B 단계 | `law/criteria/case/counsel`(A), `gate/tool`(B) |
| `query` | `TEXT` | A=사용자 쿼리 / B=tool arg query | B는 모델 재작성 쿼리 가능 |
| `domain` | `VARCHAR(16)` | B tool arg `domain` (`all/law/criteria/case`) | A는 NULL |
| `top_k` | `INTEGER` | A=body.top_k / B=search top_k | |
| `result_count` | `INTEGER NOT NULL` | A=섹션 길이 / B=docs 수 | |
| `max_similarity` | `DOUBLE PRECISION` | A=섹션 max / B=max_cosine | |
| `avg_similarity` | `DOUBLE PRECISION` | A=섹션 avg / B=docs avg cosine | |
| `top_chunks` | `JSONB` | `[{chunk_id, similarity, rank}]` | top-k만(전체 아님) |
| `created_at` | `TIMESTAMP DEFAULT NOW()` | | |

제약·인덱스:
- `INDEX (run_id)`, `INDEX (source)`.
- `UNIQUE (run_id, seq)` — 중복 방지.
- `source` CHECK: `IN ('law','criteria','case','counsel','gate','tool','dense','other')` (매핑 총함수, 미매핑 `other`).

## 3. source 매핑 (A 섹션 ↔ B 단계)

| source | A (`final_state["retrieval"]` 섹션) | B (`run_b`) |
| --- | --- | --- |
| `law` | `laws` | (tool domain=law은 `tool`로 기록 + domain 컬럼) |
| `criteria` | `criteria` | |
| `case` | `disputes` (merge: case→disputes) | |
| `counsel` | `counsels` | |
| `gate` | — | `gate_retrieval`(결정적 게이트 검색) |
| `tool` | — | `search_consumer_disputes` 각 호출 (domain 컬럼에 law/criteria/case/all) |

> A는 **섹션=source**(검색 대상별 1행), B는 **gate 1행 + tool 호출 N행**. B의 검색 대상(domain)은 `tool` source + `domain` 컬럼으로 구분 → A의 source와 교차 비교는 `domain`/`source` 조합으로.

## 4. B per-search 계측 (결정 ②, variant_b만 수정)

현재 `search()`는 `(docs, max_cosine)` 반환하고 `run_b`는 gate에선 `max_cosine`만, tool에선 chunk_id만 보존(`tools.py` recorder는 chunk_id-only). 변경:
- **recorder 확장**: `search()`가 호출될 때 `{source, query, domain, top_k, docs:[{chunk_id, cosine}]}`를 per-search로 기록(현 chunk_id-only recorder를 상위호환 확장; 비활성 시 무효과 원칙 유지).
- **gate event**: `run_b`가 직접 호출하는 gate `search()`의 반환 docs로 event 구성(recorder 불요).
- **tool events**: ReAct 내부 tool이 부르는 `search()`는 recorder로 per-search 수집 → `run_b`가 getter로 모아 events 구성.
- 반환 dict에 `retrieval_events`(또는 trace 확장) 추가 → `chat.py`가 저장. **검색 결과·답변은 무변경**(계측만).

## 5. Migration 초안 (`007_retrieval_events.sql` — 본 PR은 문서)

```sql
-- ============================================================
-- 007_retrieval_events.sql
-- Agent/RAG workflow 관측: 검색 호출별 결과 품질 (M3-5)
-- ⚠️ 수동 실행. workflow_runs(005) 선행 필요.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS retrieval_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    seq             INTEGER      NOT NULL,
    source          VARCHAR(16)  NOT NULL,
    query           TEXT,
    domain          VARCHAR(16),
    top_k           INTEGER,
    result_count    INTEGER      NOT NULL,
    max_similarity  DOUBLE PRECISION,
    avg_similarity  DOUBLE PRECISION,
    top_chunks      JSONB,
    created_at      TIMESTAMP    DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_retrieval_events_run    ON retrieval_events(run_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_events_source ON retrieval_events(source);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_retrieval_events_source') THEN
        ALTER TABLE retrieval_events ADD CONSTRAINT check_retrieval_events_source
            CHECK (source IN ('law','criteria','case','counsel','gate','tool','dense','other'));
    END IF;
END $$;

COMMENT ON TABLE retrieval_events IS '검색 호출별 결과 품질 (A/B 공통, M3-5)';
COMMENT ON COLUMN retrieval_events.source IS 'A 섹션(law/criteria/case/counsel) / B 단계(gate/tool)';
COMMENT ON COLUMN retrieval_events.top_chunks IS 'top-k [{chunk_id, similarity, rank}] (JSONB)';

DO $$ BEGIN RAISE NOTICE '✓ 007_retrieval_events.sql: retrieval_events table ready'; END $$;
```

## 6. 구현 시 변경 대상 (M3-5 구현 PR)

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/007_retrieval_events.sql` | 신규(force-add) |
| `backend/app/observability/retrieval_events.py` | 신규 `save_retrieval_events` + `build_a_retrieval_events`/`build_b_retrieval_events` (batch best-effort) |
| `backend/app/variant_b/tools.py` | recorder per-search 확장(chunk+cosine+query+domain) |
| `backend/app/variant_b/agent.py` | gate/tool events 수집 후 반환 |
| `backend/app/api/chat.py` | A: `final_state["retrieval"]`로 events 저장. B: `run_b` events 저장. |

## 7. 완료 기준 점검 (구현 시 검증)

- [ ] `007` 적용 + `\d retrieval_events`(FK/UNIQUE/CHECK/인덱스).
- [ ] A run → 섹션별 event(law/criteria/case/counsel), `top_k/result_count/max/avg_similarity` 조회.
- [ ] B run → gate event + tool event(N), **similarity·top_chunks 채워짐**(per-search 계측).
- [ ] `top_chunks` JSONB에서 chunk별 similarity·rank 조회(예: `jsonb_array_elements`).
- [ ] A/B retrieval 품질 비교 쿼리(예: source/domain별 avg max_similarity A vs B).
- [ ] best-effort: events 저장 실패해도 `/chat` 200.
- [ ] A 로직 diff 0(B는 계측만).

## 8. Next gate → M3-6

`llm_calls` 저장(provider/model/fallback/error/token). B의 정적 `"variant-b"`/A의 `"gpt-4o-mini"` 라벨을 실제 호출 단위 provider/model로 대체. A=S3 LLMLog+토큰, B=react 모델 호출.
