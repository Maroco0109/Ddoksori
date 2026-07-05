# A(MAS)의 의사결정 메커니즘 — 결정 기록 (LLM 슈퍼바이저 → 결정론적 orchestration)

- 작성일: 2026-07-05
- 성격: **결정 기록(decision record).** "A"가 어떤 종류의 시스템인지, 왜 지금 형태로 동결됐는지를 사실 기반으로 고정한다.
- 관련: [[M7-mainline-decision-framework]](../plans/modules/M7-mainline-decision-framework.md), [MAS Supervisor Architecture](../feature/MAS_SUPERVISOR_ARCHITECTURE.md), [MAS 파이프라인 아키텍처 리뷰](../report/2026-02-01-mas-pipeline-architecture-review.md)

---

## 0. 한 줄 결론

**A는 Hub-Spoke 멀티에이전트 "구조"를 유지하되, 조율(라우팅) 두뇌는 LLM이 아니라 결정론적 규칙으로 동작하는 orchestration(workflow) 시스템이다.** B(ReAct)만이 LLM tool-calling으로 자율 판단하는 agent다. 이 A vs B 대비 = **"orchestrated workflow vs autonomous agent"** 대비이며, 이것이 본 프로젝트 A/B 측정의 실체다.

## 1. 왜 이 문서가 필요한가

`docs/feature/MAS_SUPERVISOR_ARCHITECTURE.md`(2026-01-26)는 A를 *"진정한 Multi-Agent System(MAS) Supervisor Pattern"* / *"Supervisor 중앙 제어 = **LLM + 규칙 기반 의사결정**"* 으로 기술한다. 그러나 **현재 코드에서 라우팅 결정은 100% 규칙 기반이며 LLM은 라우팅에 관여하지 않는다.** 설계 문서의 서술과 실제 구현이 어긋나 있어, A를 "LLM 슈퍼바이저 MAS"로 오해하기 쉽다. 이 갭을 사실로 정정하고, 오해를 유발하던 dead code를 정리하는 근거로 삼는다.

## 2. 원래 의도 (설계 시점 근거)

`MAS_SUPERVISOR_ARCHITECTURE.md`(2026-01-26, Phase 1-7 "운영 전환 완료"):

- 목표: 기존 "규칙 기반 if/else 분기 + ReAct Loop"(중앙 관제자 없음, 동적 재시도 불가)의 한계를 극복하기 위해 **LLM + 규칙 하이브리드 슈퍼바이저**로 전환.
- `SupervisorNode`에 LLM 의사결정 경로(`_try_llm_decision`, `_build_decision_prompt`)를 구현 → 슈퍼바이저가 LLM으로 다음 에이전트를 동적으로 고르게 하려는 의도.

→ **원래 의도는 진짜 LLM 슈퍼바이저 MAS가 맞다.**

## 3. 현재 실제 동작 (코드 근거)

라우팅 결정은 전부 결정론적이며, LLM 라우팅 경로는 **호출되지 않는 dead code**다.

| 구성요소 | 파일 | 실제 동작 |
| --- | --- | --- |
| 슈퍼바이저 결정 | `backend/app/supervisor/nodes/supervisor.py:244` `decide_next_action` | 순수 규칙: `mode`에 따라 `_no_retrieval_decision` / `_full_pipeline_decision` 호출. **`_try_llm_decision`을 내부에서 한 번도 호출하지 않음** |
| LLM 라우팅 코드 | `supervisor.py:321` `_try_llm_decision`, `:450` `_build_decision_prompt` | 정의만 존재. backend 전체에서 참조처는 정의부 + 테스트 파일뿐 (프로덕션 경로 미참조) → **dead code** |
| 그래프 라우팅 | `backend/app/supervisor/graph_mas.py:308` `_route_mas_supervisor` | `state["mode"]` / `next_agent` 값 기반 조건 분기. 값 생산자는 규칙 기반(query_analysis 규칙 + SupervisorNode 규칙). **LLM이 결정하는 edge 0개** |
| 검색 에이전트 | `backend/app/agents/retrieval/base_retrieval_agent.py` | `UnifiedRetriever.search()`(SQL hybrid RRF)를 코드가 무조건 호출. LLM tool-calling 아님 |
| 검토 | `backend/app/agents/legal_review/agent.py` | 전부 정규식/규칙. LLM 미사용 |
| LLM 실사용 노드 | query_analysis(조건부 분류·확장), generation(답변 작성) | **tool 없는 prompt→text** 2곳뿐 |

**A에 LLM function/tool-calling은 존재하지 않는다.** `bind_tools`/`create_react_agent`/`@tool`은 오직 variant B(`backend/app/variant_b/`)에만 있다.

## 4. 결정

1. **A는 "결정론적 orchestration(workflow) 기반 구조화된 멀티에이전트 RAG"로 규정한다.** "LLM 슈퍼바이저가 동적으로 라우팅하는 MAS"라는 서술은 현재 구현과 다르므로 사용하지 않는다.
2. **오해를 유발하는 dead code(`_try_llm_decision`/`_build_decision_prompt` 및 관련 미사용 헬퍼)를 제거 또는 명시적으로 문서화**하여, 코드가 스스로 "A는 규칙 기반 조율"임을 드러내게 한다. (별도 정리 커밋으로 처리)
3. **이 형태를 baseline A로 동결한다.** 이유: 결정론적 흐름은 재현성·가드레일 통과율·지연 면에서 측정 기준선으로서 우수하며(§5), 진짜 자율 에이전트 B와의 A/B 비교 대상으로 적합하다.

## 5. 왜 이게 결함이 아니라 자산인가 (측정 근거)

이 A/B는 단순 모델 비교가 아니라 **아키텍처 패러다임 비교**다 — Anthropic "Building Effective Agents"의 *workflow vs agent* 구분과 정확히 일치(대부분의 프로덕션은 workflow가 낫고, agent는 필요할 때만).

| 축 | A (결정론 orchestration) | B (ReAct agent) | 출처 |
| --- | --- | --- | --- |
| 안전 pass | **1.00** | 0.83 | M5-5 |
| 보안 decided | **100%** | 96% | M4-A5 |
| leak_rate | 0% | 0% | M4-A5 |
| faithfulness | **2.00** | 1.92 | M5-5 |
| latency median | 10.2s | **6.4s** | M5-5 |
| 자율성/유연성 | 낮음(고정 흐름) | **높음**(도구 자율 선택) | 구조 |

→ **"agentic이 항상 정답은 아니다"를 데이터로 보이는 서사.** A는 예측가능·재현·안전에서, B는 유연·속도에서 우위. 실제 mainline 판단 기준은 [[M7-mainline-decision-framework]] 참조.

## 6. 스코프 / caveat

- 본 문서는 **A의 성격을 정정 기록**할 뿐, A의 런타임 동작·기본값을 바꾸지 않는다(기능 변경 없음).
- dead code 정리는 동작에 영향이 없는 순수 정리다(라우팅은 이미 규칙 기반이므로).
- 구버전 `backend/app/orchestrator/graph_mas.py`(v1 노드, counsel 포함 4개 검색 에이전트)는 chat API에 연결되지 않은 레거시다. 현재 A는 `backend/app/supervisor/` 패키지가 실체다.
