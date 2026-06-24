# M3-6 LLM call 저장 (계획서 + migration 초안)

- 작성일: 2026-06-24
- 모듈: `M3-6` LLM call 저장 (provider/model/fallback/error)
- 선행: `M3-1`~`M3-5` (`workflow_runs`/`workflow_steps`/`retrieval_events`, `run_id` 표준, A frozen·B 계측 패턴)
- 상위 계획: §M3 (L118)
- 성격: **설계 문서 + `008_llm_calls.sql` 초안.** 실제 적용·저장 코드·라이브 검증은 M3-6 구현(후속). A 무변경(read-only), B는 model/token 집계 계측만 추가.

## 0. 한 줄 요약

run의 **LLM 호출**을 `llm_calls` N행으로 저장한다. **A는 LLM 호출 노드(supervisor/query_analysis/generation)마다 1행**을 `final_state`에서 **read-only**로 구성(model은 config/`model_used` 파생, provider 표기, token은 표면화된 generation만 채움). **B는 run당 1행 집계**(react model + 합산 token + n_calls; `run_b`에 집계 계측 추가). `provider`/`model`로 A/B 모델·비용·fallback을 SQL 비교한다.

## 1. 범위

### 목표 (완료 기준 = roadmap L118)
- `008_llm_calls.sql` 설계(FK→`workflow_runs`).
- A·B의 호출 provider·model 저장 → **확인 가능**. token/fallback/error도 가능 범위에서.

### 비목표
- 실제 적용·저장 코드·라이브 검증 = M3-6 **구현**(후속 PR).
- A 노드 **계측/수정**(frozen): supervisor/query_analysis의 **token까지** 잡으려고 A를 건드리지 않는다(없으면 NULL).
- 비용(원가) 계산·요율표 = 범위 밖(token만 저장, 비용은 후속 뷰).
- guardrail 상세 = M3-7, 조회 API = M3-8, 스트리밍 `/chat/stream`.

## 2. 컬럼 설계 + 출처 매핑

| 컬럼 | 타입 | 출처 | 비고 |
| --- | --- | --- | --- |
| `call_id` | `UUID PK DEFAULT gen_random_uuid()` | (생성) | |
| `run_id` | `UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE` | M3-3 | run 종속 |
| `seq` | `INTEGER NOT NULL` | 호출 순서 | run 내 LLM 호출 순번 |
| `component` | `VARCHAR(24) NOT NULL` | A 노드명 / B 'react' | supervisor/query_analysis/generation/react |
| `provider` | `VARCHAR(16)` | model/base_url 파생 | openai/runpod_vllm/anthropic/rule_based/other |
| `model` | `VARCHAR(64)` | A=config/`model_used` / B=spec 모델 | 예: gpt-4o, gpt-4o-mini, LGAI-EXAONE/EXAONE-4.5-33B |
| `prompt_tokens` | `INTEGER` | A=generation usage / B=합산 | 미표면화 시 NULL |
| `completion_tokens` | `INTEGER` | A=generation usage / B=합산 | |
| `total_tokens` | `INTEGER` | prompt+completion | |
| `n_calls` | `INTEGER NOT NULL DEFAULT 1` | A=1 / B=react 호출 수 | B 집계행은 >1 가능 |
| `fallback` | `BOOLEAN` | A=rule_based/Anthropic 폴백, generation fallback / B=spec 폴백 | 가능 범위 |
| `status` | `VARCHAR(12) NOT NULL DEFAULT 'ok'` | ok/error | |
| `error_message` | `TEXT` | 호출 실패 시 | |
| `created_at` | `TIMESTAMP DEFAULT NOW()` | | |

제약·인덱스: `INDEX(run_id)`, `INDEX(provider)`, `INDEX(model)`, `UNIQUE(run_id, seq)`, `status` CHECK(`ok/error`).

## 3. A 매핑 (LLM 호출 노드별 1행, read-only)

현재 config에서 LLM을 호출하는 A 노드 + 모델 파생:

| component | 모델 출처 | provider | token |
| --- | --- | --- | --- |
| `supervisor` | `config.models.supervisor`(gpt-4o), 폴백 시 Anthropic | openai/anthropic | NULL(미표면화) |
| `query_analysis` | IntentClassifier `model_used`(gpt-4o-mini 또는 `rule_based`) | openai/rule_based | NULL |
| `generation` | `config.models.draft_agent`(gpt-4o) | openai | **prompt/completion** (generator usage) |
| `review` | `ENABLE_LLM_REVIEW=false` → **행 없음**(LLM 미호출). 켜지면 `review_agent` | openai | NULL |

- **노드 존재 판정**: 해당 노드가 그 run에서 실제 실행됐는지는 **M3-4 node sequence(`workflow_steps`/`_node_timings` 키)** 로 안다 → 실행된 LLM 노드만 행 생성.
- **read-only 원칙**: 모델/usage는 `final_state` 및 `_node_timings[node].output_snapshot`(M3-4가 이미 수집)에서 읽는다. A 코드 변경·신규 계측 없음. token이 없으면 NULL(§3 caveat).
- **rule_based 처리**: query_analysis가 `model_used='rule_based'`면 `provider='rule_based'`, model=`rule_based`(또는 행 생략은 구현 시 결정).

## 4. B 매핑 (run당 1행 집계, run_b 계측 — 결정)

- `run_b`에 **model + token 집계 계측 추가**(B만, 답변/검색 무변경): react 결과 메시지들의 `usage_metadata`를 합산(prompt/completion/total), 호출 수 `n_calls`, 모델 id(`get_chat_model` spec→ gpt-4o-mini 또는 EXAONE), provider(base_url/모델 파생).
- 반환 dict에 `llm_summary`(component='react', model, provider, prompt/completion/total_tokens, n_calls, status) 추가 → `chat.py`가 1행 저장.
- 정적 `"variant-b"`/`"gpt-4o-mini"` 라벨 문제 해소(실제 model 기록).

## 5. Migration 초안 (`008_llm_calls.sql` — 본 PR은 문서)

```sql
-- ============================================================
-- 008_llm_calls.sql
-- Agent/RAG workflow 관측: LLM 호출 provider/model/token/fallback (M3-6)
-- ⚠️ 수동 실행. workflow_runs(005) 선행 필요.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    seq               INTEGER      NOT NULL,
    component         VARCHAR(24)  NOT NULL,
    provider          VARCHAR(16),
    model             VARCHAR(64),
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    n_calls           INTEGER      NOT NULL DEFAULT 1,
    fallback          BOOLEAN,
    status            VARCHAR(12)  NOT NULL DEFAULT 'ok',
    error_message     TEXT,
    created_at        TIMESTAMP    DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_run      ON llm_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_provider ON llm_calls(provider);
CREATE INDEX IF NOT EXISTS idx_llm_calls_model    ON llm_calls(model);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_llm_calls_status') THEN
        ALTER TABLE llm_calls ADD CONSTRAINT check_llm_calls_status
            CHECK (status IN ('ok','error'));
    END IF;
END $$;

COMMENT ON TABLE llm_calls IS 'LLM 호출 provider/model/token/fallback (A/B 공통, M3-6)';
COMMENT ON COLUMN llm_calls.component IS 'A 노드(supervisor/query_analysis/generation) / B react';
COMMENT ON COLUMN llm_calls.provider IS 'openai/runpod_vllm/anthropic/rule_based/other (파생)';
COMMENT ON COLUMN llm_calls.n_calls IS 'A=1, B=react 모델 호출 수(집계행)';

DO $$ BEGIN RAISE NOTICE '✓ 008_llm_calls.sql: llm_calls table ready'; END $$;
```

## 6. 구현 시 변경 대상 (M3-6 구현 PR)

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/008_llm_calls.sql` | 신규(force-add) |
| `backend/app/observability/llm_calls.py` | 신규 `save_llm_calls` + `build_a_llm_calls(final_state/node_timings)` + `build_b_llm_call(b_result)` + provider 파생 |
| `backend/app/variant_b/agent.py` | react usage_metadata 합산 → `llm_summary` 반환 (B만) |
| `backend/app/api/chat.py` | A: node 출력에서 LLM 행 구성·저장. B: `llm_summary` 저장. |

## 7. 완료 기준 점검 (구현 시 검증)

- [ ] `008` 적용 + `\d llm_calls`(FK/UNIQUE/CHECK/인덱스).
- [ ] A run → 실행된 LLM 노드별 행(generation은 token 채움; supervisor/query_analysis는 model/provider, token NULL).
- [ ] B run → react 1행(실제 model + 합산 token + n_calls).
- [ ] provider/model로 A/B 비교 쿼리(예: provider별 호출 수, model별 token 합).
- [ ] best-effort: llm_calls 저장 실패해도 `/chat` 200.
- [ ] A 로직 diff 0(read-only; B는 집계 계측만).

## 8. caveat / 인계

- **A token 미완전**: supervisor/query_analysis는 token 미표면화 → NULL. A의 토큰 총합은 generation 기준 하한(과소). 완전 집계는 A 계측 필요(frozen 위반)이라 보류.
- **provider 파생 규칙**: gpt-*→openai, EXAONE/base_url→runpod_vllm, claude-*→anthropic, rule_based→rule_based.

## 9. Next gate → M3-7

`guardrail_events` 저장(block/pass + reason). A=moderation/legal_review, B=guardrail_input/output.
