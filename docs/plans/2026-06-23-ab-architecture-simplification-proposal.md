# A/B 아키텍처 간소화 + M2 재편 제안

- 작성일: 2026-06-23
- 성격: **제안(proposal)**. 캐노니컬 로드맵(`docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`)을 아직 바꾸지 않는다. 본 문서는 검토 결과 + 재편안이며, 사용자 수용 후 로드맵에 반영한다.
- 사용자 확정 방향(2026-06-23):
  1. 현재 MAS(A)는 baseline으로 **동결·보존**, "강한 단일 모델 + tools/MCP"(B)를 신설해 **A/B 측정·비교**.
  2. M2를 "provider 전환"에서 **"B 아키텍처 구축 + A/B 측정"**으로 재정의.
  3. ambiguity는 **게이트형 단발(gated single-shot) clarification**으로.
- read-only 검토로 작성. 코드 변경 없음.

## 1. Context (왜 바꾸는가)

당초 목표는 답변 품질 최적화가 아니라 **"현재 시스템 vs 개선 시스템"을 측정·비교하는 모니터링 시스템**이다(포트폴리오 가치 = 측정 가능한 숫자). 사용자의 관점이 "역할을 에이전트로 소분(MAS)" → "강한 모델 1개 + tools/MCP"로 이동했고, 핵심 동기는 **관측가능성/디버깅**이다: MAS는 "왜 이 결정을 내렸는가" 추적이 어렵고, tools/MCP는 "어떤 도구로 어떤 context를 받아 어떤 결과를 냈는가"가 추적하기 쉽다.

검토 결과 이 전환은 생각보다 저렴하다 — 아래 증거대로 현재 MAS의 "지능"은 이미 부재하기 때문이다.

## 2. 코드 증거 기반 컴포넌트 검토

### 2.1 supervisor 에이전트 — 이미 규칙 기반, LLM 결정은 dead code
- `SupervisorNode.decide_next_action`(`backend/app/supervisor/nodes/supervisor.py:244`)은 `_no_retrieval_decision`/`_full_pipeline_decision`만 호출하는 **결정형 상태머신**이다.
- LLM 결정 코드 `_try_llm_decision`(:321)·`_build_decision_prompt`(:450)는 **어디서도 호출되지 않는 dead code**(grep 확인). `SUPERVISOR_LLM_ENABLED`도 기본 `false`(`graph_mas.py:46`).
- **결론**: 현재 supervisor는 지능형 라우터가 아니라 고정 파이프라인 오케스트레이터. 디버깅할 LLM 결정 자체가 없고 MAS 허브 재진입/메시지 패싱이라는 간접층만 남는다. → B에서 제거, 라우팅은 모델 tool-calling으로, 결정형 요소(cache/guardrail)는 얇은 그래프 엣지로.

### 2.2 answer generator — 일(생성)은 필요, 별도 중량 에이전트는 잉여
- 생성(검색 컨텍스트→답변 합성)은 진짜 필요한 핵심 경로(`answer_generation/tools/generator.py`). 다만 별도 오케스트레이션 노드로서는 B에서 잉여 — 단일모델+tools에서는 tool 호출 후 **모델의 마지막 턴이 곧 답변**. citation/grounding은 tool/후처리로 유지. **품질 핵심이라 가장 마지막에 전환하고 A와 수치 비교.**

### 2.3 ambiguity detector — 현재 구현은 안티패턴, 단 "제거"가 아니라 "게이트형 단발"로
- 현재 `check_ambiguity_with_llm`(`agents/query_analysis/detectors.py:41`)은 "구체적/모호함" 이진을 LLM에 직접 묻는 **명시적 이진 분류기**. EXAONE(dormant) → gpt-4o-mini → 실패 시 False.
- 근거 기반 판정(§3)에 따라: 이 명시적 이진 분류기는 폐기하되, clarification 자체는 유지하여 **고불확실성일 때만 1회** 되묻는 게이트형으로 재설계.

## 3. ambiguity 설계 결정의 근거 (문헌)

사용자 우려를 셋으로 분해해 문헌으로 검증:

| 주장 | 판정 | 근거 |
| --- | --- | --- |
| (a) LLM이 ambiguity 판단이 어렵다 | 부분 오류 | 명시 판단 시 60–80% 인식, 단 **과대예측 편향** ([2605.25284](https://arxiv.org/html/2605.25284)) |
| (b) 넣으면 계속 되물을 것이다 | 대체로 오류 | 실측 기본값은 **답변율 95%↑, clarify 5%↓**(과소질문). RLHF 과신 때문 ([2605.25284](https://arxiv.org/html/2605.25284), [2410.13788](https://arxiv.org/pdf/2410.13788)) |
| (b′) *명시적 이진 분류기*는 과잉 플래그 | 정확 | 현재 `check_ambiguity_with_llm`이 그 안티패턴 |
| (c) rule-base여도 병목이다 | 조건부 | 무차별/저품질일 때만. 좋은 질문 1개가 **검색 P@5 +170%** ([ACM CSUR 3534965](https://dl.acm.org/doi/full/10.1145/3534965)). 작은 모델은 해소 약함(scaling, [2502.01523](https://arxiv.org/abs/2502.01523)) → 자유판단 대신 선택적 게이트가 정답([CLAM 2212.07769](https://arxiv.org/pdf/2212.07769)) |

**결론**: "ambiguity = 병목이니 제거"는 과한 결론. 정확한 결론은 **"명시적 LLM 이진 감지기를 폐기하고, 값싼 신호로 게이트된 *선택적 단발* clarification으로 바꿔라"**. 자유형 "계속 묻기" 루프만 금지하면 (b) 시나리오는 거의 발생하지 않는다.

## 4. retrieval 신뢰도 신호 문제 (게이트의 전제조건)

게이트형 clarification에는 "지금 검색이 불확실한가?"를 알려줄 **calibrated 신호**가 필요하다. 그런데 현재 코드에는 그 신호가 없다.

### 4.1 증거
- **RRF가 cosine을 덮어쓴다**: `hybrid_retriever.py:_reciprocal_rank_fusion`(:416)는 `score(d)=Σ 1/(k+rank)`, k=60. 그리고 `:462-463`에서 `result.similarity = rrf_scores[chunk_id]` — **raw cosine similarity를 RRF 점수로 덮어쓴다.**
- k=60이면 점수 범위가 대략 **0.014~0.033**으로 압축(rank1 양쪽=1/61+1/61≈0.033, rank10 한쪽=1/70≈0.014). 절대 크기가 관련도/신뢰도를 반영하지 못하고 편차가 작다(사용자 지적과 일치).
- **그 결과 sufficiency 게이트가 이미 무력화**: `sufficiency.py:44`는 "RRF top-k 방식에서는 임계치 없이 결과가 있으면 항상 sufficient"로 처리하고 `evaluate()`는 결과 건수>0이면 sufficient를 반환. 문서 상단의 confidence 공식(`0.4*sim+...`)과 `_generate_reason`은 **dead code**다(RRF 덮어쓰기로 임계치가 의미를 잃자 우회한 흔적).

### 4.2 정확한 진단
RRF는 **순위 융합(ordering)에는 robust해서 그대로 둬도 된다.** 문제는 **RRF 점수를 similarity/confidence 대용으로 덮어써서 calibrated 신호를 파괴**한 것. 이로 인해 게이트형 clarification, sufficiency/early-stop, 답변 grounding 신뢰도, **A/B retrieval 품질 측정**이 모두 신호 없이 돌아간다.

### 4.3 수정안 (doc에서 결정할 범위)
| 옵션 | 내용 | 노력 | 비고 |
| --- | --- | --- | --- |
| (1) cosine 보존 (추천 baseline) | RRF는 정렬용으로 두고 `similarity` 덮어쓰기 중단. `rrf_score`와 `cosine_similarity`(dense)를 **별도 필드로 보존**. 게이트는 raw cosine max 사용 | 소 | 게이트/sufficiency/측정 신호 즉시 복구 |
| (2) 정규화 융합 | 쿼리별 dense/lexical 점수 min-max(또는 z-score) 정규화 후 가중합 → calibrated [0,1] 융합 점수 | 중 | hybrid 이점 + 편차 회복. B 후보 |
| (3) cross-encoder reranker | top-N를 cross-encoder로 reranking → calibrated relevance | 대 | 최고 신호 + B의 측정 가능한 "개선" 축. 지연/모델 추가 |

**권고**: 게이트 신호 복구는 **(1)로 충분**. (2)/(3)은 B의 검색 품질 개선 후보로 **A/B 측정 대상**에 올린다(제거 대상 아님). RRF 자체는 정렬용으로 유지.

## 5. B 아키텍처 정의 (요약)

- **B = 강한 모델 1개 + tools**: retrieval tools(law/criteria/case) + guardrail pre/post(기존 moderation 분리 유지) + 게이트형 단발 clarification.
- **clarification 정책**: §4의 calibrated 신호(우선 raw cosine max)가 임계 미만일 때만 **딱 1회** 되묻기. 다회/루프 금지. 발화 시 `clarification_rate`와 `clarify 후 retrieval P@k 변화`를 기록.
- **A는 동결**: 현재 MAS를 baseline으로 보존(비교 기준). B는 flag/별도 엔드포인트(`variant=B`)로 격리 도입.
- **측정 계약**: M0-H capability/gate vocabulary + M2-1 §4 측정 필드 재사용(provider/model/status/fallback/duration_ms/tokens) + trace 완전성(디버깅 용이성의 정량 지표).

## 6. 로드맵 재편 제안 (M2 재정의)

기존 M2(M2-3/4/5 = MAS 노드별 provider 정책)는 B로 가면 의미가 일부 사라진다. 재정의안:

**M2 (재정의) = "비교 변형 B 구축 + A/B 측정"**

| 모듈 | 목표 | 완료 기준 |
| --- | --- | --- |
| M2-3R (재정의) | **B 아키텍처 + A/B 하니스 결정 doc** (본 제안을 확정 문서화). 기존 M2-3 provider-policy는 "B 모델 + 각 tool provider 체인"으로 흡수 | B 구성·clarification 정책·측정 계약 확정 |
| M2-4R | **retrieval 신뢰도 신호 복구**(§4.3 옵션1): cosine 보존, calibrated 신호 노출. A의 검색에 적용(B와 공유) | 게이트/sufficiency 신호가 살아나고, 점수 분포 before/after 측정 |
| M2-5R | **B 최소 골격**: 강한 모델 + retrieval tool 1개 + 게이트형 단발 clarification(M2-4R 신호 사용). A 무변경 | `variant=B`로 단발 응답 생성, trace 기록 |
| M2-6R | B 나머지 tool(criteria/case) + guardrail pre/post + citation | B 풀 파이프라인 smoke 통과 |
| M2-7R | **A/B 비교 런** | latency·retrieval 품질·clarification_rate·fallback·token·trace 완전성 수치 산출 |
| M2-8R | embedding provider 분리(기존 M2-6 승계) | 1536d DB 호환 명확화 |

재활용: **M2-1 인벤토리**(capability→tool 매핑), **M2-2 health**(B도 `runpod_vllm` 사용), **M2-3 plan**(provider 체인 부분).

## 7. 정리 백로그 (현 모듈 비포함)
- `backend/app/orchestrator/graph_mas.py` — M2-1에서 미사용 legacy 중복본.
- supervisor LLM dead code(`_try_llm_decision`/`_build_decision_prompt`).
- sufficiency confidence 공식 dead code(`sufficiency.py:96` `_generate_reason` 등).

## 8. 불확실성 (정직 고지)
- B의 답변 품질이 A보다 나을지는 **측정 전엔 모른다** — 그게 이 시스템의 존재 이유.
- 본 검토는 read-only. 코드 미변경.

## 9. Next gate
사용자가 본 제안을 수용하면 → 캐노니컬 로드맵을 M2-3R~M2-8R로 갱신하고 **M2-3R(B 아키텍처 결정 doc)**부터 모듈 단위로 진행. pod는 **M2-5R(B 골격 smoke)부터 필요** — 그 시점에 가동 요청한다(그 전엔 Stop 유지).

## Sources
- [Knowing but Not Showing: LLMs Recognize Ambiguity but Rarely Ask Clarifying Questions (arxiv 2605.25284)](https://arxiv.org/html/2605.25284)
- [Modeling Future Conversation Turns to Teach LLMs to Ask Clarifying Questions (arxiv 2410.13788)](https://arxiv.org/pdf/2410.13788)
- [How to Approach Ambiguous Queries in Conversational Search: A Survey (ACM Computing Surveys 10.1145/3534965)](https://dl.acm.org/doi/full/10.1145/3534965)
- [CondAmbigQA (arxiv 2502.01523)](https://arxiv.org/abs/2502.01523)
- [CLAM: Selective Clarification for Ambiguous Questions (arxiv 2212.07769)](https://arxiv.org/pdf/2212.07769)
- [Clarifying the Path to User Satisfaction (arxiv 2402.01934)](https://arxiv.org/pdf/2402.01934)
- [Asking Clarifying Questions: To benefit or to disturb users in Web search? (IPM 2023)](https://www.sciencedirect.com/science/article/abs/pii/S0306457322002771)
