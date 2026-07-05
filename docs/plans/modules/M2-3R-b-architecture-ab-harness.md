# M2-3R B 아키텍처 + A/B 하니스 결정 (결정 문서)

- 작성일: 2026-06-23
- 모듈: `M2-3R` B(Agentic RAG) 아키텍처와 A/B 비교 하니스 확정
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §1.2 M2 재정의, `docs/plans/2026-06-23-ab-architecture-simplification-proposal.md`
- 선행 완료: M2-1 호출경로 inventory, M2-2 RunPod health(EXAONE 4.5-33B H100 baseline 467.8ms), M2-3 provider policy plan
- 성격: **결정 문서**. 런타임 코드 변경 없음. **RunPod pod 불필요**(호출 없음). 구현은 M2-4R~ 이후 모듈.

## 0. 한 줄 요약

현재 MAS(A = Advanced RAG)를 baseline으로 동결하고, **LangGraph ReAct 기반 단일 모델 + tools(B = Agentic RAG)**를 신설해, **EXAONE 4.5-33B ↔ frontier 두 모델 비교축**으로 A/B를 측정한다. tool은 retrieval 전용이 아니라 검색·조회·계산·검증·상호작용을 포함하며, 모델이 *어떤 tool을 왜 호출했는지* trace로 남는 것이 전환의 핵심 동기(관측가능성)다.

## 1. 목표 / 비목표

### 목표
- B의 두뇌 모델 정책, tool-calling 하니스, tool 카탈로그, clarification 정책, A/B 격리 방식, 측정 계약을 확정한다.

### 비목표(이번 모듈에서 안 함)
- B 코드 구현(M2-5R~), A/B 검색평가 하니스(M2-4R), tool 구현, RunPod 재기동/측정 런, DB 저장(M3), A(MAS) 변경.
- MCP 도입, 신규 provider 추상화 framework 신설(M2-0 §8 유지).

## 2. B 두뇌 모델 — 두 모델 비교축

- **primary 후보 2종을 비교축으로 둔다**: ① EXAONE 4.5-33B(RunPod 자체호스팅, 비용통제·인프라 역량) ② frontier(Claude/GPT, tool-calling/추론 상한).
- 하니스는 **모델-agnostic**: LangGraph ReAct + 기존 `LLMProviderFactory`(`backend/app/llm/providers/factory.py`)로 두뇌 모델은 config 스왑 한 줄. 따라서 EXAONE-B vs frontier-B는 *동일 하니스에 모델만 교체*해 측정한다.
- **제약**: RunPod은 테스트 등급(간헐 가동)이므로 측정 런은 bounded. EXAONE는 tool-calling을 켜서 재기동해야 한다(§7).
- 포트폴리오 의미: "자체호스팅 모델로 Agentic RAG가 어디까지 가능한가 + frontier 대비 격차"를 숫자로 제시.

## 3. tool-calling 하니스 — LangGraph ReAct

- **결정**: 기존 스택의 LangGraph `create_react_agent` + 네이티브 function calling을 사용한다(신규 framework 없이 재사용).
- 근거: LangGraph는 이미 A에서 사용 중. ReAct 루프의 각 step(tool 호출·입력·출력)이 trace로 남아 디버깅 가시성이 높다(= 전환 동기).
- **MCP는 백로그**: tool을 MCP 서버로 노출하는 것은 표준화/재사용 이점이 있으나 초기 셋업 복잡도 때문에 후속.

## 4. Tool 카탈로그

tool = "모델이 필요 시 호출하는 함수(이름 + 설명 + 입력 스키마 + 출력)". retrieval 전용이 아니다.

### 4.1 초기 B 범위 (v1 카탈로그)

| tool | 분류 | 설명 | 입력(초안) | 출력(초안) |
|---|---|---|---|---|
| `search_law` | 검색 | 법령/시행령 hybrid 검색 | query, top_k | chunks[] + cosine/rrf score |
| `search_criteria` | 검색 | 행정규칙/별표 기준 검색 | query, top_k | chunks[] + score |
| `search_case` | 검색 | 분쟁 조정/상담 사례 검색 | query, top_k | chunks[] + score |
| `request_clarification` | 상호작용 | 게이트형 단발 되묻기(§5) | reason | 사용자에게 1회 질문 |
| `verify_citation` | 검증 | 인용한 법령/사례가 코퍼스에 실존하는지 확인 | citation_ref | exists: bool + 원문 ref |
| `get_law_article` | 조회 | 법령 ID로 원문 정확 조회 | law_article_id | 조문 원문 |
| `get_case_detail` | 조회 | case_uid로 사례 상세 조회 | case_uid | 사례 상세 |
| `calculate_deadline` | 계산 | 청약철회/분쟁조정 기한 날짜계산 | 기준일, 유형 | 마감일/잔여일 |

각 tool은 호출마다 trace 필드를 emit한다: `tool_name`, `args_summary`, `result_summary`, `duration_ms`, `status`, (검색 tool은) `result_count`/`max_cosine`.

### 4.2 백로그 (초기 범위 외)
웹검색, GraphRAG 그래프 질의, `mask_pii`/moderation tool, escalate-to-human, `detect_product`/`classify_dispute_category`, action 계열(민원 초안 생성·저장 등).

### 4.3 규율
4.1은 **B v1이 *지향*하는 카탈로그**이며 동시 구현이 아니다. 실제 코드는 M2-5R에서 tool 1개부터 점진 적용한다(과구현 방지).

## 5. clarification 정책 — 게이트형 단발

- **B 내부 retrieval 신뢰 신호**(B의 retrieval tool이 반환하는 cosine/reranker 점수; **A 의존 없음**)가 임계 미만일 때만 `request_clarification`을 **1회** 호출. (M2-4R 재정의로 A에는 cosine 계측을 추가하지 않음 — B 내부에서 자체 계산)
- 다회/루프 금지. 신호가 충분하면 곧장 답변.
- 근거: LLM 기본 실패모드는 과소질문(answer ~95%/clarify <5%), 명시적 이진 분류기는 과대플래그 → 값싼 게이트 신호로 선택적 단발이 정답(제안 문서 §3 참조).

## 6. A/B 격리 + 측정 계약

### 6.1 격리
- `/chat?variant=B`(또는 동등 플래그)로 B를 격리 도입. **A(MAS) 코드는 무변경.** 동일 입력으로 A/B를 같은 조건에서 비교.

### 6.2 측정 계약 (emit, 저장은 M3)
- 재사용: M0-H capability/gate vocabulary + M2-1 §4 LLM 호출 필드(provider/model/status/fallback/duration_ms/tokens).
- 추가 지표:
  - **trace 완전성** — 각 run에서 tool 호출 체인이 빠짐없이 기록되는 비율(디버깅 용이성의 정량화).
  - `clarification_rate` + clarify 후 retrieval 품질 변화.
  - **허위인용 차단율** — `verify_citation`이 존재하지 않는 인용을 잡아낸 비율(보안 Goldenset의 citation 조작 항목과 직결).
  - A vs B: latency, retrieval 품질(**M2-4R 외부 RAGAS/eval 하니스 기반**, A·B 동일 eval셋), token, fallback.

## 7. 구현 순서 (참고 — 실제 구현은 후속 모듈, 한 번에 하나)

1. **M2-4R**: A/B 검색평가 하니스 + A baseline(외부 RAGAS/eval, **A 무변경**). B 게이트 신호는 A가 아니라 B 내부에서 계산(M2-5R).
2. **M2-5R**: B 최소 골격 — ReAct + retrieval tool 1개 + `request_clarification`. **여기서 EXAONE를 tool-calling 플래그로 재기동**: `--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser deepseek_r1`(EXAONE 4.x 공식 권장). **pod는 이 시점부터 필요.**
3. **M2-6R**: retrieval 2개 추가 + `verify_citation` + `get_law_article`/`get_case_detail` + citation 후처리 + guardrail pre/post.
4. 이후: `calculate_deadline` 등 잔여 v1 tool 배치 → M2-7R A/B 비교 런 → M2-8R multi-RAG 실험 → M2-9R embedding 분리.

## 8. 완료 기준 / 검증
- 본 doc이 §2~§6의 결정(두뇌 비교축 / ReAct 하니스 / v1 tool 카탈로그 / 단발 clarification / A/B 격리 / 측정 계약)을 모두 명시하고, 로드맵 §1.2 M2 재정의·제안 문서와 모순 없으면 M2-3R 완료.
- 검증: read-only 대조. 코드/런타임 변경 0건.
- M2-3R 수용 후에만 M2-4R로 진행.

## 9. pod 안내
M2-3R은 pod 불필요. **pod는 M2-5R(B 골격 smoke)부터 필요** — 그 시점에 사용자에게 가동(Stop→Resume) 요청한다. 그 전까지 H100은 Stop 유지.

## Sources
- [EXAONE 4.0 official repo (agentic tool use, vLLM tool-calling flags)](https://github.com/LG-AI-EXAONE/EXAONE-4.0)
- [LGAI-EXAONE/EXAONE-4.5-33B](https://huggingface.co/LGAI-EXAONE/EXAONE-4.5-33B)
