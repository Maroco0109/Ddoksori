# Variant B canonical 모델 = EXAONE 전환 (결정·결과)

- 작성일: 2026-06-24
- 성격: B 아키텍처 보정(작은 behavior 변경) + 라이브 검증. M3 관측 백본 완성 직후.
- 동기: 라이브 `/chat`의 B가 **canonical 의도와 다르게 gpt-4o-mini(frontier)** 로 돌고 있었음을 발견.

## 문제

A/B 피벗 의도는 **B = 강한 모델 + tools (Agentic RAG)**, canonical EXAONE 4.5-33B였다. 그러나:
- `run_b` 기본 `model_spec="frontier"`, `chat.py`가 model_spec 없이 호출 → 라이브 B = **gpt-4o-mini**.
- `model.py` 주석상 frontier는 "배관 싸게 검증용" 기본값(임시)인데 라이브 경로에 그대로 남아 있었다.
- `llm_calls` 증거: M3 라이브 검증의 B는 전부 gpt-4o-mini였다.
- 결과적으로 측정이 "MAS(A) vs **싼 모델** agentic(B)"였고, 의도한 "vs **강한 모델** agentic"이 아니었다.

## 결정 (사용자, 2026-06-24)

라이브 B canonical 모델을 **EXAONE로 전환**. (M2-7R 오프라인은 이미 A/frontier-B/EXAONE-B 3-way 비교를 했으나 라이브 경로는 frontier 고정이었음.)

## 변경

- `backend/app/api/chat.py`: B 분기에서 `run_b(..., model_spec=os.getenv("VARIANT_B_MODEL_SPEC", "exaone"))`.
  - 기본 **exaone**(canonical). `VARIANT_B_MODEL_SPEC=frontier`로 override 가능(3-way 비교/ pod 미가동 dev용).
- A·M3 저장 로직 무변경. `run_b` 시그니처도 기존 `model_spec` 인자 사용(무변경).

## 라이브 검증 (5432 DB, RunPod EXAONE up)

- B run HTTP 200 (≈33s, 33B).
- `llm_calls`: `component=react, provider=runpod_vllm, model=LGAI-EXAONE/EXAONE-4.5-33B, total_tokens≈13.6k, n_calls=6`.
- `protocol_events`(ReAct 궤적): `search_consumer_disputes(case) → get_law_article(제17조) → get_law_article(제18조) → search(law_guide) → verify_citation → 최종답변`.
  - gpt-4o-mini(이전: 2 tool calls)보다 훨씬 풍부 — 조문 조회·허위인용 검증 도구까지 적극 사용. "강한 모델 agentic"의 의도 실증.
- EXAONE ReAct tool-calling이 현재 pod에서 정상 동작함을 재확인(M2-5R smoke 이후).

## 영향 / 인계

- 이후 라이브 B 측정은 **EXAONE 기준**(latency↑, token↑, tool 사용↑). M3 비교 쿼리는 `llm_calls.model`로 모델을 구분하므로 과거 gpt-4o-mini run과 섞이지 않게 필터 가능.
- 3-way(A / B-frontier / B-EXAONE) 비교가 필요하면 `VARIANT_B_MODEL_SPEC` 토글로 수집.
- 응답 JSON의 정적 `model="variant-b"` 라벨은 표시용이며 실제 모델은 `llm_calls`에 기록(M3-6). 표시 라벨 정합은 후속 선택사항.
