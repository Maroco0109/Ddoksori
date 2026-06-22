# M0-H Roadmap Integration Decision

- 작성일: 2026-06-22
- 모듈 성격: `M0-H` architecture baseline 통합 결정
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 관련 문서: `docs/architecture/agent-harness.md`, `docs/architecture/agent-contracts.md`, `docs/architecture/capability-registry.md`, `docs/architecture/quality-gates.md`
- 목표: M0-H를 별도 구현 Phase로 둘지, 기존 M1~M4 roadmap의 기준선으로 통합할지 결정한다.
- 이번 문서에서 하지 않는 일: runtime 코드 수정, provider 전환, observability DB 설계, Goldenset/security runner 구현.

## 1. 결론

M0-H는 **별도 구현 Phase로 확장하지 않고 기존 roadmap의 architecture baseline으로 통합**한다.

이유는 M0-H가 이미 runtime 변경 없이 현재 LangGraph/MAS 시스템을 다음 vocabulary로 정리했기 때문이다.

- agent/node contract
- capability registry
- quality gate
- security guardrail
- provider/retrieval/cache/observability boundary

따라서 M0-H는 `M0-H -> M1 -> M2`처럼 새 순서로 끼워 넣는 module이 아니라, **M2/M3/M4가 같은 측정 언어를 공유하게 하는 기준 문서**로 유지한다.

## 2. 사용자 포트폴리오 기준 반영

이번 판단은 사용자가 제공한 포트폴리오 기준을 따른다.

| 기준 | M0-H 통합 판단 |
| --- | --- |
| AI 활용 backend/software 개발 취업 목표 | M0-H는 backend runtime을 agent contract/capability/gate로 설명해 “AI 시스템을 소프트웨어 구조로 다룰 수 있음”을 보여준다. |
| AI Security 관심 기업도 고려 | M0-H의 input/output moderation, legal review, supervisor sanitization gate가 M4 security test 기준으로 재사용된다. |
| 기존 프로젝트 약점 보완 | API 남용, provider 혼재, monitoring 부재, 성능 지표 부재를 “측정 항목”으로 표현하는 기준선이 된다. |
| 메인 포트폴리오 프로젝트화 | 단순 챗봇 기능보다 “측정 가능한 Agent/RAG/LLM 운영 시스템”으로 설명하는 narrative를 강화한다. |

## 3. 통합 방식

### 3.1 Roadmap 본문에 M0-H 기준선 추가

`docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`에는 M0-H를 `1.0` architecture baseline으로 추가한다.

이 섹션은 다음을 명시한다.

- M0-H는 runtime 구현 Phase가 아니다.
- M2는 capability ID와 provider/generation/query/supervisor gate를 기준으로 전환 범위를 잡는다.
- M3는 quality gate와 observability vocabulary를 DB event schema로 이어받는다.
- M4는 guardrail/security gate를 Goldenset/code security 측정 기준으로 이어받는다.

### 3.2 M2에서 재사용할 M0-H 항목

| M0-H 문서 | M2에서 사용하는 내용 |
| --- | --- |
| `docs/architecture/capability-registry.md` | `llm.provider_factory`, `llm.exaone_vllm`, `generation.answer`, `analysis.query_classifier`, `supervisor.routing`, `api.chat_sse` capability 기준 |
| `docs/architecture/agent-contracts.md` | query analysis, generation, review, supervisor node의 입력/출력/의존성 boundary |
| `docs/architecture/quality-gates.md` | `G-query-analysis-valid`, `G-generation-sufficiency`, `G-supervisor-iteration`, `G-sse-complete` 측정 기준 |
| `docs/architecture/agent-harness.md` | M2 변경이 LangGraph/MAS topology를 재작성하지 않고 provider boundary만 바꿔야 한다는 architecture constraint |

### 3.3 M3/M4에서 재사용할 M0-H 항목

| 후속 영역 | 재사용 항목 |
| --- | --- |
| M3 observability | node timing, RAG JSON log, Prometheus metric, gate event schema 후보 |
| M4 chatbot security | input/output moderation, legal review, supervisor sanitization, unsafe/fallback/block metrics |
| M4 code security | PR diff가 guardrail/provider/routing/secret handling을 바꿀 때 review 기준으로 capability/gate vocabulary 사용 |

## 4. 대안 검토

| 대안 | 장점 | 기각 이유 |
| --- | --- | --- |
| M0-H를 별도 M0 Phase로 두고 구현 모듈을 추가 | architecture work가 크게 보임 | 이미 docs-only로 완료된 기준선이며, 지금 구현 module을 추가하면 M2 진입이 늦고 roadmap이 과해진다. |
| M0-H를 roadmap에 통합하지 않음 | roadmap 변경 최소화 | PR #13 문서가 고립되고 M2/M3/M4와 연결성이 약해져 포트폴리오 narrative가 흐려진다. |
| M0-H를 M3 관측 시스템에서만 사용 | observability와 직접 연결됨 | M2 provider 전환과 M4 security도 capability/gate vocabulary를 필요로 하므로 범위가 너무 좁다. |

## 5. 결정

M0-H는 다음 상태로 확정한다.

- 상태: 완료된 architecture baseline
- 위치: `docs/architecture/*` + roadmap `1.0` 섹션
- 후속 작업: 각 M2/M3/M4 모듈에서 필요한 capability/gate ID를 참조
- 금지 사항: M0-H 이름으로 별도 runtime refactor를 시작하지 않음

## 6. Verification

- `docs/architecture/*` 파일이 develop에 병합되어 있음.
- roadmap에 M0-H 통합 섹션이 추가됨.
- 이 문서는 runtime 변경 없이 decision record 역할만 수행함.

## 7. Next gate

다음 문서는 `M2-0-provider-transition-plan.md`와 `M2-1-llm-call-path-inventory-plan.md`이다. M2 구현은 M2-1 inventory 문서가 검토된 뒤 시작한다.
