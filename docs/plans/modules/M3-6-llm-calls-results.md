# M3-6 LLM call 저장 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M3-6` LLM call 저장 (provider/model/fallback/error)
- 계획서: `docs/plans/modules/M3-6-llm-calls-plan.md`
- 상위 계획: §M3 (L118)
- 성격: 코드 구현 + 라이브 검증. A 무변경(read-only), B는 model/token 집계 계측만 추가.

## 0. 한 줄 결론

`008_llm_calls.sql`을 적용하고 동기 `/chat`이 LLM 호출을 `llm_calls`로 best-effort 저장하게 했다. **A는 LLM 호출 노드별 1행**(supervisor/query_analysis/generation, read-only), **B는 react 1행 집계**(실제 model + usage_metadata 합산 token). 실제 `/chat`으로 검증했고, 정적 `"variant-b"`/`"gpt-4o-mini"` 라벨이 **실제 호출 단위 provider/model**로 대체됨을 확인했다.

## 1. 구현 내용

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/008_llm_calls.sql` | 신규 (FK→workflow_runs CASCADE, UNIQUE(run_id,seq), status CHECK) |
| `backend/app/observability/llm_calls.py` | 신규 (`LLMCallDB` batch + best-effort + `build_a_llm_calls`/`build_b_llm_call` + `provider_for`) |
| `backend/app/variant_b/agent.py` | react usage_metadata 합산 → `llm_summary` 반환 (B만, 답변 무변경) |
| `backend/app/api/chat.py` | A: `final_state`/`node_timings`로 노드별 행. B: `llm_summary` 1행. |

## 2. 라이브 검증 결과 (5432 DB, RunPod EXAONE up)

### A run — LLM 호출 노드별 1행 (read-only)
```
seq | component      | provider | model       | p_tok | c_tok | n_calls | fallback
 0  | query_analysis | openai   | gpt-4o-mini |  NULL |  NULL |   1     | f
 1  | supervisor     | openai   | gpt-4o      |  NULL |  NULL |   1     | f
 2  | generation     | openai   | gpt-4o      |  NULL |  NULL |   1     | f
```
- `generation`의 model은 **실제 `generation_model_used`**(gpt-4o). supervisor/query_analysis는 config 파생(설정상 호출 모델).
- token은 A가 state로 미표면화 → **NULL**(설계 caveat).

### B run — react 1행 집계 (run_b 계측)
```
seq | component | provider | model       | p_tok | c_tok | t_tok | n_calls
 0  | react     | openai   | gpt-4o-mini |  2171 |  266  | 2437  |   2
```
→ react 루프의 **실제 model + 합산 token + 호출 수(2)** 기록. 정적 라벨 해소.

### A/B model/provider 비교 (모듈 목적)
```
variant | component      | provider | model       | calls | tokens
 A      | generation     | openai   | gpt-4o      |   1   |
 A      | query_analysis | openai   | gpt-4o-mini |   1   |
 A      | supervisor     | openai   | gpt-4o      |   1   |
 B      | react          | openai   | gpt-4o-mini |   2   |  2437
```

| 검증 항목 | 결과 |
| --- | --- |
| migration 008 (FK CASCADE/UNIQUE/CHECK/인덱스) | ✅ `\d llm_calls` |
| A run → LLM 노드별 provider·model (완료기준 L118) | ✅ 3행 |
| B run → react 실제 model + 합산 token | ✅ gpt-4o-mini, 2437 tok |
| provider/model로 A/B 비교 집계 | ✅ |
| best-effort 비차단 (테이블 제거 후 `/chat`) | ✅ HTTP 200 (M3-3~5와 동일 try/except 패턴) |
| A 로직 diff 0 (read-only; B는 집계 계측만) | ✅ |

## 3. caveat / 발견 (backlog)

- **A token 미완전(설계대로)**: A는 어떤 노드도 token을 state로 표면화하지 않아 `prompt/completion_tokens=NULL`. A 토큰 총합은 미집계 → 비용 비교는 B만 정량 가능. 완전 집계는 A 계측 필요(frozen 위반)이라 보류.
- **A query_analysis/supervisor model은 config 파생**: 실제 호출 여부(예: query_analysis가 `META_QUERY_USE_LLM=false`로 rule_based 폴백)와 무관하게 **설정상 모델**을 기록. generation만 실제 `model_used` 사용. 정밀 구분은 A가 `model_used`를 state로 노출해야 가능(후속).
- **fallback/error 캡처**: 현재 generation의 rule_based/safe_fallback만 `fallback` 반영. provider 폴백(Anthropic) 등 세부는 후속.

## 4. Next gate → M3-7

`guardrail_events` 저장(block/pass + reason). A=moderation/legal_review, B=guardrail_input/output(trace에 blocked/flagged 보유).
